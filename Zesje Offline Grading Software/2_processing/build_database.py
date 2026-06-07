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

import csv
import re

INPUT_CSV = os.path.join(DATA_DIR, "zesje_grades.csv")
AI_CSV = os.path.join(DATA_DIR, "auto_grades_1a.csv")
OUTPUT_CSV = os.path.join(DATA_DIR, "grade_database.csv")

CRITERIA_1B = ["LHS_RHS", "tau", "I_0", "I_1"]

def parse_raw_csv(filepath):
    records = []
    if not os.path.exists(filepath):
        return records
    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, 1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            if raw_line.startswith('"') and raw_line.endswith('"'):
                raw_line = raw_line[1:-1]
            raw_line = raw_line.replace('""', '"')
            parts = []
            for match in csv.reader([raw_line]):
                parts = match
                break
            if len(parts) < 6:
                continue
            exercise = parts[1].strip()
            copy_name = parts[2].strip()
            score_str = parts[4].strip()
            label = parts[5].strip()
            m = re.search(r"(?:Copy_|sub_)(\d+)", copy_name)
            if not m:
                continue
            student_num = int(m.group(1))
            score = int(score_str) if score_str.isdigit() else 0
            records.append({
                "exercise": exercise,
                "student_num": student_num,
                "score": score,
                "label": label,
            })
    return records

def parse_ai_csv(filepath):
    records = []
    if not os.path.exists(filepath):
        return records
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sub_str = row.get("Submission", "")
            score_str = row.get("Score", "0")
            try:
                student_num = int(sub_str)
                score = int(score_str)
                label = "Good" if score == 1 else "Bad"
                records.append({
                    "exercise": "1a",
                    "student_num": student_num,
                    "score": score,
                    "label": label
                })
            except Exception as e:
                pass
    return records

def build_database(manual_records, ai_records, config):
    index = {}
    # Load AI grades first
    for r in ai_records:
        key = (r["exercise"], r["student_num"])
        index[key] = r
    # Override/merge with manual/browser grades
    for r in manual_records:
        key = (r["exercise"], r["student_num"])
        index[key] = r
        
    database = []
    max_students = config.get("total_students", 121)
    for n in range(1, max_students + 1):
        row = {
            "student": n,
            "good": 0,
            "LHS_RHS": 0,
            "tau": 0,
            "I_0": 0,
            "I_1": 0,
            "check_1a": 0,
            "check_1b": 0,
        }
        r1a = index.get(("1a", n))
        if r1a:
            label = r1a["label"]
            if label in ["Good", "LHS_RHS"]:
                row["good"] = 1
            elif "Good" in label and "Bad" in label:
                row["good"] = 0
                row["check_1a"] = 1
            else:
                row["good"] = 0
        else:
            row["check_1a"] = 1
            
        r1b = index.get(("1b", n))
        if r1b:
            label = r1b["label"]
            if label and label != "Blank":
                criteria_present = [c.strip() for c in label.split("|")]
                for criterion in CRITERIA_1B:
                    if criterion in criteria_present:
                        row[criterion] = 1
        else:
            row["check_1b"] = 1
        database.append(row)
    return database

def write_database(database, filepath):
    fieldnames = ["student", "good", "LHS_RHS", "tau", "I_0", "I_1", "check_1a", "check_1b"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(database)

def main():
    config = load_config()
    manual_records = parse_raw_csv(INPUT_CSV)
    ai_records = parse_ai_csv(AI_CSV)
    
    if not manual_records and not ai_records:
        print("No grades found to build database.")
        return
        
    database = build_database(manual_records, ai_records, config)
    write_database(database, OUTPUT_CSV)
    print(f"Database built successfully at {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
