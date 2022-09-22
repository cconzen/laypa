
from tqdm import tqdm
import argparse
import glob
import os
import pathlib
import pickle
import sys
from pathlib import Path
from typing import Optional
import cv2

import matplotlib
import numpy as np
from natsort import os_sorted
from multiprocessing import Pool

sys.path.append(str(Path(__file__).resolve().parent.joinpath("..")))
from page_xml.xmlPAGE import PageData


def get_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocessing an annotated dataset of documents with pageXML")
    parser.add_argument("-i", "--input", help="Input folder",
                        required=True, type=str)
    parser.add_argument(
        "-o", "--output", help="Output folder", required=True, type=str)
    parser.add_argument("-m", "--mode", help="Output mode",
                        choices=["baseline", "region", "both"], default="baseline", type=str)
    parser.add_argument("-r", "--resize", action="store_true",
                        help="Resize input images")
    parser.add_argument("-w", "--line_width",
                        help="Used line width", type=int, default=5)
    parser.add_argument("-c", "--line_color", help="Used line color",
                        choices=list(range(256)), type=int, metavar="{0-255}", default=1)

    args = parser.parse_args()
    return args


class Preprocess:
    def __init__(self, input_dir=None, output_dir=None, mode="baseline", auto_resize=False, line_width=5, line_color=1) -> None:
        self.input_dir: Optional[Path] = None
        self.output_dir: Optional[Path] = None
        self.line_width = line_width
        self.line_color = line_color
        self.total_size = 2048*2048
        self.mode = mode
        # Formats found here: https://docs.opencv.org/4.x/d4/da8/group__imgcodecs.html#imread
        self.image_formats = [".bmp", ".dib",
                              ".jpeg", ".jpg", ".jpe",
                              ".jp2",
                              ".png",
                              ".webp",
                              ".pbm", ".pgm", ".ppm", ".pxm", ".pnm",
                              ".pfm",
                              ".sr", ".ras",
                              ".tiff", ".tif",
                              ".exr",
                              ".hdr", ".pic"]
        self.auto_resize = auto_resize

        if input_dir is not None:
            self.set_input_dir(input_dir)
        if output_dir is not None:
            self.set_output_dir(output_dir)

    def set_input_dir(self, input_dir: str | Path) -> None:
        if isinstance(input_dir, str):
            input_dir = Path(input_dir)

        if not input_dir.exists():
            raise FileNotFoundError(f"Input dir ({input_dir}) is not found")

        if not input_dir.is_dir():
            raise NotADirectoryError(
                f"Input path ({input_dir}) is not a directory")

        if not os.access(path=input_dir, mode=os.R_OK):
            raise PermissionError(
                f"No access to {input_dir} for read operations")

        page_dir = input_dir.joinpath("page")
        if not input_dir.joinpath("page").exists():
            raise FileNotFoundError(f"Sub page dir ({page_dir}) is not found")

        if not os.access(path=page_dir, mode=os.R_OK):
            raise PermissionError(
                f"No access to {page_dir} for read operations")

        self.input_dir = input_dir.resolve()

    def get_input_dir(self) -> Optional[Path]:
        return self.input_dir

    def set_output_dir(self, output_dir: str | Path) -> None:
        if isinstance(output_dir, str):
            output_dir = Path(output_dir)

        if not output_dir.is_dir():
            print(
                f"Could not find output dir ({output_dir}), creating one at specified location")
            output_dir.mkdir(parents=True)

        self.output_dir = output_dir.resolve()

    def get_output_dir(self) -> Optional[Path]:
        return self.output_dir

    @staticmethod
    def check_pageXML_exists(image_paths: list[Path]) -> None:
        xml_paths = [image_path.parent.joinpath("page", image_path.stem).with_suffix(
            '.xml') for image_path in image_paths]

        for xml_path, image_path in zip(xml_paths, image_paths):
            if not xml_path.is_file():
                raise FileNotFoundError(
                    f"Input image path ({image_path}), has no corresponding pageXML file ({xml_path})")
            if not os.access(path=xml_path, mode=os.R_OK):
                raise PermissionError(
                    f"No access to {xml_path} for read operations")

    @staticmethod
    def resize_image(image, total_size=0) -> np.ndarray:
        origheight, origwidth, channels = image.shape
        counter = 1
        height = np.ceil(origheight / (256 * counter)) * 256
        width = np.ceil(origwidth / (256 * counter)) * 256
        while height*width > total_size:
            height = np.ceil(origheight / (256 * counter)) * 256
            width = np.ceil(origwidth / (256 * counter)) * 256
            counter += 1

        res_image = cv2.resize(image, np.asarray([width, height]).astype(np.int32),
                               interpolation=cv2.INTER_CUBIC)

        return res_image

    def process_single_file(self, image_path: Path) -> tuple[str, str, np.ndarray]:
        if self.input_dir is None:
            raise ValueError("Cannot run when the input dir is not set")
        if self.output_dir is None:
            raise ValueError("Cannot run when the output dir is not set")

        image_stem = Path(image_path.stem)
        xml_path = self.input_dir.joinpath(
            "page", image_stem.with_suffix('.xml'))

        image = cv2.imread(str(image_path))

        if self.auto_resize:
            image = self.resize_image(image, self.total_size)

        image_shape = np.asarray(image.shape[:2])

        out_image_path = str(self.output_dir.joinpath(
            "original", image_stem)) + ".png"

        cv2.imwrite(out_image_path, image)

        gt_data = PageData(xml_path)
        gt_data.parse()

        if self.mode == "baseline":
            baseline_mask = gt_data.build_baseline_mask(
                image_shape, color=self.line_color, line_width=self.line_width)
            mask = baseline_mask
        elif self.mode == "region":
            region_mask = gt_data.build_mask(image_shape, node_types, classes)
            mask = region_mask
        else:
            raise NotImplementedError

        out_mask_path = str(self.output_dir.joinpath(
            "ground_truth", image_stem)) + ".png"

        cv2.imwrite(out_mask_path, mask)

        return out_image_path, out_mask_path, image_shape

    def run(self) -> None:
        if self.input_dir is None:
            raise ValueError("Cannot run when the input dir is not set")
        if self.output_dir is None:
            raise ValueError("Cannot run when the output dir is not set")

        image_paths = os_sorted([image_path.resolve() for image_path in self.input_dir.glob("*")
                                 if image_path.suffix in self.image_formats])

        if len(image_paths) == 0:
            raise ValueError(
                f"No images found when searching input dir ({self.input_dir})")

        self.check_pageXML_exists(image_paths)

        self.output_dir.joinpath("original").mkdir(parents=True, exist_ok=True)
        self.output_dir.joinpath("ground_truth").mkdir(
            parents=True, exist_ok=True)

        # Single thread
        # for image_path in tqdm(image_paths):
        #     self.process_single_file(image_path)

        # Multithread
        with Pool(os.cpu_count()) as pool:
            results = list(tqdm(pool.imap_unordered(
                self.process_single_file, image_paths), total=len(image_paths)))

        image_list, mask_list, output_sizes = zip(*results)

        with open(self.output_dir.joinpath("image_list.txt"), mode='w') as f:
            for new_image_path in image_list:
                f.write(f"{new_image_path}\n")

        with open(self.output_dir.joinpath("mask_list.txt"), mode='w') as f:
            for new_mask_path in mask_list:
                f.write(f"{new_mask_path}\n")

        with open(self.output_dir.joinpath("output_sizes.txt"), mode='w') as f:
            for output_size in output_sizes:
                f.write(f"{output_size[0]}, {output_size[1]}\n")


def main(args):
    process = Preprocess(input_dir=args.input,
                         output_dir=args.output,
                         mode=args.mode,
                         auto_resize=args.resize,
                         line_width=args.line_width,
                         line_color=args.line_color)
    process.run()


if __name__ == "__main__":
    args = get_arguments()
    main(args)
