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
from detectron2.data.transforms import ResizeShortestEdge

import matplotlib
import numpy as np
from natsort import os_sorted
from multiprocessing import Pool

sys.path.append(str(Path(__file__).resolve().parent.joinpath("..")))
from page_xml.xmlPAGE import PageData
from page_xml.xml_to_image import XMLImage

def get_arguments() -> argparse.Namespace:
    # HACK hardcoded regions if none are given
    republic_regions = ["marginalia", "page-number", "resolution", "date",
                        "index", "attendance", "Resumption", "resumption", "Insertion", "insertion"]
    republic_merge_regions = [
        "resolution:Resumption,resumption,Insertion,insertion"]
    
    parser = argparse.ArgumentParser(
        description="Preprocessing an annotated dataset of documents with pageXML")
    parser.add_argument("-i", "--input", help="Input folder",
                        required=True, type=str)
    parser.add_argument(
        "-o", "--output", help="Output folder", required=True, type=str)
    parser.add_argument("-m", "--mode", help="Output mode",
                        choices=["baseline", "region", "both"], default="baseline", type=str)

    parser.add_argument(
        "-r", "--resize", help="Resize input images", action="store_true")
    parser.add_argument("--resize_mode", help="How to select the size when resizing",
                        type=str, choices=["range", "choice"], default="choice")
    parser.add_argument("--min_size", help="Min resize shape",
                        nargs="*", type=int, default=[1024])
    parser.add_argument(
        "--max_size", help="Max resize shape", type=int, default=2048)

    parser.add_argument("-w", "--line_width",
                        help="Used line width", type=int, default=5)
    parser.add_argument("-c", "--line_color", help="Used line color",
                        choices=list(range(256)), type=int, metavar="{0-255}", default=1)
    
    parser.add_argument(
        "--regions",
        default=republic_regions,
        nargs="+",
        type=str,
        help="""List of regions to be extracted. 
                            Format: --regions r1 r2 r3 ...""",
    )
    parser.add_argument(
        "--merge_regions",
        default=republic_merge_regions,
        nargs="+",
        type=str,
        help="""Merge regions on PAGE file into a single one.
                            Format --merge_regions r1:r2,r3 r4:r5, then r2 and r3
                            will be merged into r1 and r5 into r4""",
    )
    parser.add_argument(
        "--region_type",
        default=None,
        nargs="+",
        type=str,
        help="""Type of region on PAGE file.
                            Format --region_type t1:r1,r3 t2:r5, then type t1
                            will assigned to regions r1 and r3 and type t2 to
                            r5 and so on...""",
    )

    args = parser.parse_args()
    return args


class Preprocess:
    def __init__(self, input_dir=None,
                 output_dir=None,
                 mode="baseline",
                 resize=False,
                 resize_mode="choice",
                 min_size=[800],
                 max_size=1333,
                 line_width=None,
                 line_color=None,
                 regions=None,
                 merge_regions=None,
                 region_type=None
                 ) -> None:

        self.input_dir: Optional[Path] = None
        if input_dir is not None:
            self.set_input_dir(input_dir)

        self.output_dir: Optional[Path] = None
        if output_dir is not None:
            self.set_output_dir(output_dir)

        self.mode = mode

        self.xml_to_image = XMLImage(
                                mode=self.mode,
                                line_width=line_width,
                                line_color=line_color,
                                regions=regions,
                                merge_regions=merge_regions,
                                region_type=region_type
                            )

        # self.total_size = 2048*2048
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

        self.resize = resize
        self.resize_mode = resize_mode
        self.min_size = min_size
        self.max_size = max_size

        if self.resize_mode == "choice":
            if len(self.min_size) < 1:
                raise ValueError(
                    "Must specify at least one choice when using the choice option.")
        elif self.resize_mode == "range":
            if len(self.min_size) != 2:
                raise ValueError("Must have two int to set the range")
        else:
            raise NotImplementedError(
                "Only \"choice\" and \"range\" are accepted values")

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
        xml_paths = [image_path.resolve().parent.joinpath("page", image_path.stem + ".xml") for image_path in image_paths]

        for xml_path, image_path in zip(xml_paths, image_paths):
            if not xml_path.is_file():
                raise FileNotFoundError(
                    f"Input image path ({image_path}), has no corresponding pageXML file ({xml_path})")
            if not os.access(path=xml_path, mode=os.R_OK):
                raise PermissionError(
                    f"No access to {xml_path} for read operations")

    def resize_image_old(self, image: np.ndarray) -> np.ndarray:
        old_height, old_width, channels = image.shape
        counter = 1
        height = np.ceil(old_height / (256 * counter)) * 256
        width = np.ceil(old_width / (256 * counter)) * 256
        while height*width > self.min_size[-1] * self.max_size:
            height = np.ceil(old_height / (256 * counter)) * 256
            width = np.ceil(old_width / (256 * counter)) * 256
            counter += 1

        res_image = cv2.resize(image, np.asarray([width, height]).astype(np.int32),
                               interpolation=cv2.INTER_CUBIC)

        return res_image

    def resize_image(self, image: np.ndarray) -> np.ndarray:
        old_height, old_width, channels = image.shape
        if self.resize_mode == "range":
            short_edge_length = np.random.randint(
                self.min_size[0], self.min_size[1] + 1)
        elif self.resize_mode == "choice":
            short_edge_length = np.random.choice(self.min_size)
        else:
            raise NotImplementedError(
                "Only \"choice\" and \"range\" are accepted values")

        if short_edge_length == 0:
            return image

        height, width = self.get_output_shape(
            old_height, old_width, short_edge_length, self.max_size)

        res_image = cv2.resize(image, np.asarray([width, height]).astype(
            np.int32), interpolation=cv2.INTER_CUBIC)

        return res_image

    @staticmethod
    def get_output_shape(old_height: int, old_width: int, short_edge_length: int, max_size: int) -> tuple[int, int]:
        """
        Compute the output size given input size and target short edge length.
        """
        scale = float(short_edge_length) / min(old_height, old_width)
        if old_height < old_width:
            height, width = short_edge_length, scale * old_width
        else:
            height, width = scale * old_height, short_edge_length
        if max(height, width) > max_size:
            scale = max_size * 1.0 / max(height, width)
            height = height * scale
            width = width * scale

        height = int(height + 0.5)
        width = int(width + 0.5)
        return (height, width)

    def process_single_file(self, image_path: Path) -> tuple[Path, Path, np.ndarray]:
        if self.input_dir is None:
            raise ValueError("Cannot run when the input dir is not set")
        if self.output_dir is None:
            raise ValueError("Cannot run when the output dir is not set")

        image_stem = image_path.stem
        xml_path = self.input_dir.joinpath("page", image_stem + '.xml')

        image = cv2.imread(str(image_path))

        if self.resize:
            image = self.resize_image(image)

        image_shape = np.asarray(image.shape[:2])

        out_image_path = self.output_dir.joinpath(
            "original", image_stem + ".png")

        cv2.imwrite(str(out_image_path), image)

        mask = self.xml_to_image.run(xml_path, image_shape=image_shape)

        out_mask_path = self.output_dir.joinpath(
            "ground_truth", image_stem + ".png")

        cv2.imwrite(str(out_mask_path), mask)

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

        zipped_results: tuple[list[Path], list[Path], list[np.ndarray]] = tuple(zip(*results))
         
        image_list, mask_list, output_sizes = zipped_results

        with open(self.output_dir.joinpath("image_list.txt"), mode='w') as f:
            for new_image_path in image_list:
                relative_new_image_path = new_image_path.relative_to(self.output_dir)
                f.write(f"{relative_new_image_path}\n")

        with open(self.output_dir.joinpath("mask_list.txt"), mode='w') as f:
            for new_mask_path in mask_list:
                relative_new_mask_path = new_mask_path.relative_to(self.output_dir)
                f.write(f"{relative_new_mask_path}\n")

        with open(self.output_dir.joinpath("output_sizes.txt"), mode='w') as f:
            for output_size in output_sizes:
                f.write(f"{output_size[0]}, {output_size[1]}\n")


def main(args) -> None:
    process = Preprocess(
        input_dir=args.input,
        output_dir=args.output,
        mode=args.mode,
        resize=args.resize,
        resize_mode=args.resize_mode,
        min_size=args.min_size,
        max_size=args.max_size,
        line_width=args.line_width,
        line_color=args.line_color,
        regions=args.regions,
        merge_regions=args.merge_regions,
        region_type=args.region_type
    )
    process.run()


if __name__ == "__main__":
    args = get_arguments()
    main(args)
