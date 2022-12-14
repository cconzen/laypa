from tqdm import tqdm
import argparse
import os
import sys
from pathlib import Path
from typing import Optional
import cv2

import imagesize

import numpy as np
from multiprocessing import Pool

sys.path.append(str(Path(__file__).resolve().parent.joinpath("..")))
from page_xml.xml_to_image import XMLImage
from utils.path_utils import image_path_to_xml_path, check_path_accessible

def get_arguments() -> argparse.Namespace:    
    parser = argparse.ArgumentParser(parents=[Preprocess.get_parser(), XMLImage.get_parser()],
        description="Preprocessing an annotated dataset of documents with pageXML")
    
    io_args = parser.add_argument_group("IO")
    io_args.add_argument("-i", "--input", help="Input folder/file",
                        required=True, type=str)
    io_args.add_argument("-o", "--output", help="Output folder",
                        required=True, type=str)
    args = parser.parse_args()
    return args

class Preprocess:
    def __init__(self, input_path=None,
                 output_dir=None,
                 resize=False,
                 resize_mode="choice",
                 min_size=[800],
                 max_size=1333,
                 xml_to_image=None,
                 disable_check=False,
                 overwrite=False
                 ) -> None:

        self.input_path: Optional[Path] = None
        if input_path is not None:
            self.set_input_path(input_path)

        self.output_dir: Optional[Path] = None
        if output_dir is not None:
            self.set_output_dir(output_dir)
            
        if not isinstance(xml_to_image, XMLImage):
            raise ValueError(f"Must provide convertion from xml to image. Current type is {type(xml_to_image)}, not XMLImage")

        self.xml_to_image = xml_to_image
        
        self.disable_check = disable_check
        self.overwrite = overwrite

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
    
    @classmethod
    def get_parser(cls) -> argparse.ArgumentParser:
        
        parser = argparse.ArgumentParser(add_help=False)
        pre_process_args = parser.add_argument_group("preprocessing")
        
        pre_process_args.add_argument(
            "--resize", 
            action="store_true",
            help="Resize input images"
        )
        pre_process_args.add_argument(
            "--resize_mode", 
            default="choice",
            choices=["range", "choice"],
            type=str, 
            help="How to select the size when resizing"
        )
        
        pre_process_args.add_argument(
            "--min_size", 
            default=[1024],
            nargs="*",
            type=int, 
            help="Min resize shape"
        )
        pre_process_args.add_argument(
            "--max_size", 
            default=2048,
            type=int,
            help="Max resize shape"
        )
        
        pre_process_args.add_argument(
            "--disable_check", 
            action="store_true", 
            help="Don't check if all images exist"
        )
        
        pre_process_args.add_argument(
            "--overwrite", 
            action="store_true",
            help="Overwrite the images and label masks"
        )
        
        return parser

    def get_file_paths(self, input_path: str | Path):
        if isinstance(input_path, str):
            input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input dir ({input}) is not found")
        
        if not os.access(path=input_path, mode=os.R_OK):
            raise PermissionError(
                f"No access to {input_path} for read operations")
              
        if input_path.is_dir():
            image_paths = [image_path for image_path in input_path.glob("*") if image_path.suffix in self.image_formats]
        elif input_path.is_file() and input_path.suffix == ".txt":
            with input_path.open(mode="r") as f:
                image_paths = [Path(line) for line in f.read().splitlines()]
        else:
            raise ValueError(f"Invalid file type: {input_path.suffix}")
            
        xml_paths = [image_path_to_xml_path(image_path, self.disable_check) for image_path in image_paths]
        
        return image_paths, xml_paths
    
    def set_input_path(self, input_path: str | Path) -> None:
        if isinstance(input_path, str):
            input_path = Path(input_path)

        if not input_path.exists():
            raise FileNotFoundError(f"Input ({input_path}) is not found")

        # Old check replace with get_file_paths
        # if not input_path.is_dir():
        #     raise NotADirectoryError(
        #         f"Input path ({input_path}) is not a directory")

        if not os.access(path=input_path, mode=os.R_OK):
            raise PermissionError(
                f"No access to {input_path} for read operations")

        # Old check replace with get_file_paths
        # page_dir = input_path.joinpath("page")
        # if not page_dir.exists():
        #     raise FileNotFoundError(f"Sub page dir ({page_dir}) is not found")

        # if not os.access(path=page_dir, mode=os.R_OK):
        #     raise PermissionError(
        #         f"No access to {page_dir} for read operations")

        self.input_path = input_path.resolve()

    def get_input_path(self) -> Optional[Path]:
        return self.input_path

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

    # @staticmethod
    # def check_pageXML_exists(image_paths: list[Path]) -> None:
    #     _ = [image_path_to_xml_path(image_path) for image_path in image_paths]
    
    @staticmethod
    def check_paths_exists(paths: list[Path]) -> None:
        _ = [check_path_accessible(path) for path in paths]

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

    def sample_short_edge_length(self):
        if self.resize_mode == "range":
            short_edge_length = np.random.randint(
                self.min_size[0], self.min_size[1] + 1)
        elif self.resize_mode == "choice":
            short_edge_length = np.random.choice(self.min_size)
        else:
            raise NotImplementedError(
                "Only \"choice\" and \"range\" are accepted values")
        
        return short_edge_length
    
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
    
    def resize_image(self, image: np.ndarray, image_shape: Optional[tuple[int, int]] = None) -> np.ndarray:
        old_height, old_width, channels = image.shape

        if image_shape is not None:
            height, width = image_shape
        else:
            short_edge_length = self.sample_short_edge_length()
            if short_edge_length == 0:
                return image
            height, width = self.get_output_shape(
                old_height, old_width, short_edge_length, self.max_size)

        res_image = cv2.resize(image, np.asarray([width, height]).astype(
            np.int32), interpolation=cv2.INTER_CUBIC)

        return res_image

    def process_single_file(self, image_path: Path) -> tuple[Path, Path, np.ndarray]:
        if self.output_dir is None:
            raise ValueError("Cannot run when the output dir is not set")
        
        image_stem = image_path.stem
        xml_path = image_path_to_xml_path(image_path, self.disable_check)
        # xml_path = self.input_dir.joinpath("page", image_stem + '.xml')
        
        image_shape = tuple(int(value) for value in imagesize.get(image_path)[::-1])
        if self.resize:
            short_edge_length = self.sample_short_edge_length()
            image_shape = self.get_output_shape(old_height=image_shape[0],
                                                old_width=image_shape[1],
                                                short_edge_length=short_edge_length,
                                                max_size=self.max_size
                                                )
            
        out_image_path = self.output_dir.joinpath(
            "original", image_stem + ".png")
        
        def save_image(image_path: Path, out_image_path: Path, image_shape: tuple[int,int]):
            image = cv2.imread(str(image_path))

            if self.resize:
                image = self.resize_image(image, image_shape=image_shape)
            #REVIEW This can maybe also be replaced with copying/linking the original image, if no resize
            cv2.imwrite(str(out_image_path), image)
        
        if self.overwrite or not out_image_path.exists():
            save_image(image_path, out_image_path, image_shape)
        else:
            out_image_shape = imagesize.get(out_image_path)[::-1]
            if out_image_shape != image_shape:
                save_image(image_path, out_image_path, image_shape)
            else:
                #TODO Skipped
                pass

        out_mask_path = self.output_dir.joinpath(
            "ground_truth", image_stem + ".png")
        
        def save_mask(xml_path: Path, out_mask_path: Path, image_shape: tuple[int,int]):
            mask = self.xml_to_image.run(xml_path, image_shape=image_shape)
            
            cv2.imwrite(str(out_mask_path), mask)

        if self.overwrite or not out_mask_path.exists():
            save_mask(xml_path, out_mask_path, image_shape)
        else:
            out_mask_shape = tuple(int(value) for value in imagesize.get(out_mask_path)[::-1])
            if out_mask_shape != image_shape:
                save_mask(xml_path, out_mask_path, image_shape)
            else:
                # TODO Skipped
                pass
        
        image_shape = np.asarray(image_shape)

        return out_image_path, out_mask_path, image_shape

    def run(self) -> None:
        if self.input_path is None:
            raise ValueError("Cannot run when the input path is not set")
        if self.output_dir is None:
            raise ValueError("Cannot run when the output dir is not set")

        image_paths, xml_paths = self.get_file_paths(self.input_path)

        if len(image_paths) == 0:
            raise ValueError(
                f"No images found when checking input ({self.input_path})")
            
        if len(xml_paths) == 0:
            raise ValueError(
                f"No pagexml found when checking input  ({self.input_path})")

        if not self.disable_check:
            self.check_paths_exists(image_paths)
            self.check_paths_exists(xml_paths)

        self.output_dir.joinpath("original").mkdir(parents=True, exist_ok=True)
        self.output_dir.joinpath("ground_truth").mkdir(parents=True, exist_ok=True)

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
    xml_to_image = XMLImage(
        mode=args.mode,
        line_width=args.line_width,
        line_color=args.line_color,
        regions=args.regions,
        merge_regions=args.merge_regions,
        region_type=args.region_type
    )
    process = Preprocess(
        input_path=args.input,
        output_dir=args.output,
        resize=args.resize,
        resize_mode=args.resize_mode,
        min_size=args.min_size,
        max_size=args.max_size,
        xml_to_image=xml_to_image,
        disable_check=args.disable_check,
        overwrite=args.overwrite
    )
    process.run()


if __name__ == "__main__":
    args = get_arguments()
    main(args)
