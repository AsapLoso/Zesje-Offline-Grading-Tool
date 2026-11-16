import os
import json
import sys
import argparse

# --- CONFIG & PATH RESOLUTION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(SCRIPT_DIR) in ["1_scrape", "2_processing", "3_grading", "4_upload"]:
    REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
else:
    REPO_ROOT = SCRIPT_DIR

DATA_DIR = os.path.join(REPO_ROOT, "data")
sys.path.insert(0, REPO_ROOT)
from exam_config import add_exam_argument, load_exam_config_from_args

def load_config(argv=None):
    parser = argparse.ArgumentParser(description="Merge the selected exam's local images.")
    add_exam_argument(parser)
    return load_exam_config_from_args(parser.parse_args(argv))

from PIL import Image

def merge_images(config=None):
    if config is None:
        config = load_config()
    exam_images = os.path.join(config["exam_dir"], "zesje_images")
    base_dir = exam_images if os.path.exists(exam_images) else os.path.join(DATA_DIR, "zesje_images")
    dir_1b = os.path.join(base_dir, "1b")
    dir_1b_ext = os.path.join(base_dir, "1b_ext")
    output_dir = os.path.join(base_dir, "1b_combined")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if not os.path.exists(dir_1b):
        print(f"Directory {dir_1b} does not exist. Please check your scraped data.")
        return
    if not os.path.exists(dir_1b_ext):
        print(f"Directory {dir_1b_ext} does not exist. Please check your scraped data.")
        return

    files_1b = [f for f in os.listdir(dir_1b) if f.endswith('.png')]
    files_1b.sort(key=lambda x: int(x.split('_')[1].split('.')[0]) if '_' in x and '.' in x else 0)

    print(f"Found {len(files_1b)} images in {dir_1b} to process.")

    for filename in files_1b:
        path1 = os.path.join(dir_1b, filename)
        path2 = os.path.join(dir_1b_ext, filename)

        if not os.path.exists(path2):
            print(f"Warning: Skipping {filename} because it was not found in {dir_1b_ext}")
            continue

        try:
            with Image.open(path1) as img1, Image.open(path2) as img2:
                total_width = max(img1.width, img2.width)
                total_height = img1.height + img2.height

                new_img = Image.new('RGB', (total_width, total_height), (255, 255, 255))
                new_img.paste(img1, (0, 0))
                new_img.paste(img2, (0, img1.height))

                output_path = os.path.join(output_dir, filename)
                new_img.save(output_path)
                print(f"Merged: {filename}")
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            
    print(f"\nDone! Combined images are in: {output_dir}")

if __name__ == "__main__":
    cfg = load_config()
    merge_images(cfg)
