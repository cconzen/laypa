import argparse
from multiprocessing import Pool
import os
import sys

from tqdm import tqdm
from input_utils import get_file_paths
from collections import Counter
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parent.joinpath("..")))
from xml_comparison import pretty_print
from page_xml.xmlPAGE import PageData
from utils.path_utils import image_path_to_xml_path
    
def get_arguments() -> argparse.Namespace:    
    parser = argparse.ArgumentParser(
        description="Count regions from a dataset")
    
    io_args = parser.add_argument_group("IO")
    io_args.add_argument("-i", "--input", help="Input folder/file",
                            nargs="+", action="extend", type=str)
    args = parser.parse_args()
    return args

def count_regions_single_page(xml_path: Path) -> Counter:
    page_data = PageData(xml_path)
    
    region_names = ["TextRegion"] #Assuming this is all there is
    zones = page_data.get_zones(region_names)
    
    if zones is None:
        return Counter()
    
    counter = Counter(item["type"] for item in zones.values())
    return counter

def main(args):
    # Formats found here: https://docs.opencv.org/4.x/d4/da8/group__imgcodecs.html#imread
    image_formats = [".bmp", ".dib",
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

    image_paths = get_file_paths(args.input, image_formats)
    xml_paths = [image_path_to_xml_path(image_path) for image_path in image_paths]
    
    # Single thread
    # regions_per_page = []
    # for xml_path_i in tqdm(xml_paths):
    #     regions_per_page.extend(count_regions_single_page(xml_path_i))
        
    # Multithread
    with Pool(os.cpu_count()) as pool:
        regions_per_page = list(tqdm(pool.imap_unordered(
            count_regions_single_page, xml_paths), total=len(xml_paths)))
    
    total_regions = sum(regions_per_page, Counter())
    
    pretty_print(dict(total_regions), n_decimals=0)
    
if __name__ == "__main__":
    args = get_arguments()
    main(args)