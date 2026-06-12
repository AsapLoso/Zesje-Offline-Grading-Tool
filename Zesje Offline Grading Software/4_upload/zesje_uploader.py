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

import time
import csv
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Key mappings
KEY_1A_GOOD = "1"
KEY_1A_BAD = "2"
KEY_1B_LHS_RHS = "1"
KEY_1B_TAU = "2"
KEY_1B_I_0 = "3"
KEY_1B_I_1 = "4"
KEY_1B_NONE = "5"
KEY_1B_ALL = "6"

# Timing
SLEEP_AFTER_NAV = 1.0
SLEEP_BETWEEN_KEYS = 0.2
SLEEP_BEFORE_NEXT = 1.0

# Files
DATABASE_CSV = os.path.join(DATA_DIR, "grade_database.csv")
PROGRESS_FILE = os.path.join(DATA_DIR, "upload_progress.txt")

MANUAL_NOTE_STUDENTS = {7, 8, 16, 20, 25, 27, 47, 52, 63, 77, 79, 81, 96}

def setup_driver(config):
    options = Options()
    options.binary_location = config.get("firefox_binary")
    options.accept_insecure_certs = True
    options.add_argument("-profile")
    options.add_argument(config.get("firefox_profile_path"))

    options.set_preference("network.proxy.type", 0)
    options.set_preference("browser.cache.disk.enable", False)
    options.set_preference("browser.cache.memory.enable", False)
    options.set_preference("browser.cache.offline.enable", False)

    service = Service(executable_path=config.get("geckodriver_path"))
    return webdriver.Firefox(service=service, options=options)

def read_database():
    database = {}
    if not os.path.exists(DATABASE_CSV):
        return database
    with open(DATABASE_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            n = int(row["student"])
            database[n] = {
                "good": int(row["good"]),
                "LHS_RHS": int(row["LHS_RHS"]),
                "tau": int(row["tau"]),
                "I_0": int(row["I_0"]),
                "I_1": int(row["I_1"]),
                "check_1a": int(row["check_1a"]),
                "check_1b": int(row["check_1b"]),
            }
    return database

def load_progress():
    uploaded = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            for line in f:
                uploaded.add(line.strip())
    return uploaded

def save_progress(key):
    with open(PROGRESS_FILE, "a") as f:
        f.write(key + "\n")

def press_key(driver, key):
    body = driver.find_element(By.TAG_NAME, "body")
    body.send_keys(key)

def get_1b_keys(row):
    lhs, tau, i0, i1 = row["LHS_RHS"], row["tau"], row["I_0"], row["I_1"]
    if lhs and tau and i0 and i1: return [(KEY_1B_ALL, "ALL correct")]
    if not (lhs or tau or i0 or i1): return [(KEY_1B_NONE, "NONE correct")]
    keys = []
    if lhs: keys.append((KEY_1B_LHS_RHS, "LHS_RHS"))
    if tau: keys.append((KEY_1B_TAU, "tau"))
    if i0: keys.append((KEY_1B_I_0, "I_0"))
    if i1: keys.append((KEY_1B_I_1, "I_1"))
    return keys

def format_1b_criteria(row):
    criteria = []
    for c in ["LHS_RHS", "tau", "I_0", "I_1"]:
        if row[c]: criteria.append(c)
    return "|".join(criteria) if criteria else "NONE"

def prompt(msg, quit_allowed=True):
    suffix = " (or 'q' to quit)" if quit_allowed else ""
    print(f"  >>> {msg}{suffix}: ", end="", flush=True)
    response = input().strip().lower()
    return response != "q"

def wait_for_confirmation(student, exercise, description, is_check=False, is_manual_note=False):
    if is_check:
        print(f"  !!! CHECK IT !!! - Data missing/conflicting, grade manually in browser!")
    if is_manual_note:
        print(f"  NOTE: MANUAL REVIEW NEEDED - Verify this submission carefully!")
    if not is_check:
        print(f"  [Plan] Will grade: {description}")
    return prompt("Page loaded? Press ENTER to press the grade keys")

def navigate_and_wait(driver, url):
    driver.get(url)
    time.sleep(SLEEP_AFTER_NAV)
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "img")))
    except:
        print("  [Warn] Page may not have fully loaded")
    time.sleep(0.2)

def upload_grades(dry_run=False):
    config = load_config()
    if not os.path.exists(DATABASE_CSV):
        print(f"Error: {DATABASE_CSV} not found! Please build the database first.")
        return
    database = read_database()
    uploaded = load_progress()
    
    total_students = config.get("total_students", 121)
    total_tasks = total_students * 2
    remaining = total_tasks - len(uploaded)

    print("-" * 60)
    print("  ZESJE GRADE UPLOADER")
    print("-" * 60)
    print(f"  Database:      {DATABASE_CSV}")
    print(f"  Remaining:     {remaining}")
    print(f"  Mode:          {'DRY RUN' if dry_run else 'LIVE'}")
    print("-" * 60)

    if remaining == 0:
        print("\nAll grades already uploaded!")
        return

    driver = None
    if not dry_run:
        print("\nStarting Firefox...")
        driver = setup_driver(config)
        driver.get(config.get("zesje_base_url"))
        time.sleep(3)
        print("Ready!\n")

    count = 0
    try:
        for n in range(1, total_students + 1):
            if n not in database: continue
            row = database[n]
            is_manual_note = (n in MANUAL_NOTE_STUDENTS)

            for ex, prob_id, check_key in [("1a", 1, "check_1a"), ("1b", 2, "check_1b")]:
                key = f"{n}:{ex}"
                if key in uploaded: continue
                count += 1
                is_check = bool(row[check_key])
                
                if ex == "1a":
                    desc = "Good" if row["good"] else "Bad"
                    keys = [(KEY_1A_GOOD if row["good"] else KEY_1A_BAD, desc)]
                else:
                    desc = format_1b_criteria(row)
                    keys = get_1b_keys(row)
                
                keys_display = ", ".join(f"'{k}' ({d})" for k, d in keys)
                print(f"\n" + "-" * 60)
                print(f"  [{count}/{remaining}] Student {n}/{total_students} - {ex}")
                if is_check: print(f"  Grade: !!! CHECK IT (manual review needed)")
                else: print(f"  Action: {desc} -> press {keys_display} + Enter")

                if not dry_run:
                    url = f"{config.get('zesje_base_url')}/exams/{config.get('exam_id')}/grade/{n}/{prob_id}"
                    navigate_and_wait(driver, url)
                    if not wait_for_confirmation(n, ex, f"press {keys_display} + Enter", is_check, is_manual_note):
                        print("\nStopped. Progress saved."); return
                    if not is_check:
                        for k, d in keys:
                            press_key(driver, k)
                            print(f"  [OK] Pressed '{k}' ({d})")
                            time.sleep(SLEEP_BETWEEN_KEYS)
                        print(f"  Keys sent to browser.")
                    if not prompt("Keys registered in Zesje? Press ENTER to continue to next page"):
                        print("\nStopped. Progress saved."); return
                if not dry_run:
                    save_progress(key)
                    uploaded.add(key)

        print("\n" + "=" * 60 + "\n  DONE!\n" + "=" * 60)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        if driver: driver.quit()

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    upload_grades(dry_run=dry_run)
