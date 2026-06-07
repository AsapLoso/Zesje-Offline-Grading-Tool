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

import shutil

def finalize_structure():
    src_base = os.path.join(DATA_DIR, "zesje_images")
    dst_base = os.path.join(DATA_DIR, "final_exports")
    
    mappings = {
        os.path.join(src_base, "1a"): os.path.join(dst_base, "1a"),
        os.path.join(src_base, "1b_combined"): os.path.join(dst_base, "1b")
    }

    if not os.path.exists(dst_base):
        os.makedirs(dst_base)

    for src_dir, dst_dir in mappings.items():
        if not os.path.exists(src_dir):
            print(f"Source {src_dir} not found. Skipping.")
            continue
            
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)

        files = [f for f in os.listdir(src_dir) if f.startswith("sub_") and f.endswith(".png")]
        print(f"Processing {len(files)} files from {src_dir} -> {dst_dir}")

        for filename in files:
            try:
                sub_id = filename.split("_")[1].split(".")[0]
                padded_id = sub_id.zfill(3)
                new_filename = f"Copy_{padded_id}.png"
                
                shutil.copy2(
                    os.path.join(src_dir, filename),
                    os.path.join(dst_dir, new_filename)
                )
            except Exception as e:
                print(f"Error copying {filename}: {e}")

    print("\nFinal structure complete!")

if __name__ == "__main__":
    finalize_structure()
