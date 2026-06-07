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

import glob
import csv
import re
import sys

def manual_workflow():
    image_dir = os.path.join(DATA_DIR, "zesje_images", "1a")
    if not os.path.exists(image_dir):
        print(f"Folder {image_dir} not found. Please ensure you have scraped 1a.")
        return

    images = glob.glob(os.path.join(image_dir, "*.[jp][pn]*"))
    csv_file = os.path.join(DATA_DIR, "zesje_grades.csv")
    
    graded = set()
    if os.path.exists(csv_file):
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row and len(row) >= 3:
                    graded.add(row[2])

    print("==============================================")
    print("  ANTIGRAVITY MANUAL FAST-GRADER WORKFLOW 1A  ")
    print("==============================================")
    print("For each image, does it match this?")
    print("  dI/dt = -(R/L)*I + V_0(t)/L")
    print("  OR   V_0(t) = I(t)*R + L*(dI/dt)")
    print("\nWatch out for +- mistakes! Must be 100% equivalent.")
    print("Type '1' (or 'y') for GOOD, '0' (or 'n') for BAD, 'q' to quit.")
    print("==============================================\n")
    
    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not graded:
            writer.writerow(["Problem", "Submission", "Filename", "TotalScore", "Selections"])
            
        def sort_key(path):
            m = re.search(r'sub_(\d+)', os.path.basename(path))
            return int(m.group(1)) if m else 0

        for img_path in sorted(images, key=sort_key):
            filename = os.path.basename(img_path)
            if filename in graded: continue
            
            sub_match = re.search(r'sub_(\d+)', filename, re.IGNORECASE)
            sub_id = sub_match.group(1) if sub_match else filename.split('.')[0]
            
            print(f"--- Submission {sub_id} ({filename}) ---")
            sys.stdout.flush()
            
            while True:
                ans = input(f"Was the exercise made well? (1/0/q): ").strip().lower()
                if ans == 'q':
                    print("\nQuitting workflow. All progress saved.")
                    return
                elif ans in ['1', 'g', 'good', 'y']:
                    writer.writerow(["1a", sub_id, filename, 1, '"LHS_RHS"'])
                    graded.add(filename)
                    print("-> Saved: GOOD (1 pt)\n")
                    break
                elif ans in ['0', 'b', 'bad', 'n']:
                    writer.writerow(["1a", sub_id, filename, 0, '""'])
                    graded.add(filename)
                    print("-> Saved: BAD (0 pts)\n")
                    break
                else:
                    print("Invalid input. Please type '1' or '0'.")
            f.flush()

if __name__ == "__main__":
    manual_workflow()
