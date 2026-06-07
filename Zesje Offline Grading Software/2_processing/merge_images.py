import os
import json
import sys

# --- CONFIG & PATH RESOLUTION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(SCRIPT_DIR) in ["1_scrape", "2_processing", "3_grading", "4_upload"]:
    REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
else:
    REPO_ROOT = SCRIPT_DIR

CONFIG_PATH = os.path.join(REPO_ROOT, "config.json")
DATA_DIR = os.path.join(REPO_ROOT, "data")

def load_config():
    default_config = {
        "zesje_base_url": "https://tn2211-2026.zesje.tudelft.nl",
        "exam_id": 3,
        "firefox_binary": r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "firefox_profile_path": r"C:\Users\Deuts\AppData\Roaming\Mozilla\Firefox\Profiles\39shiy81.default-release",
        "geckodriver_path": r"C:\Geckodriver.exe",
        "problem_mapping": {
            "1": "1a",
            "2": "1b",
            "3": "1b_ext"
        },
        "total_students": 121
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                # Merge with default config to ensure all fields exist
                for k, v in default_config.items():
                    if k not in config:
                        config[k] = v
                return config
        except Exception as e:
            print(f"[Warning] Failed to load config.json: {e}. Using defaults.")
    return default_config

from PIL import Image

def merge_images():
    base_dir = os.path.join(DATA_DIR, "zesje_images")
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
    merge_images()
