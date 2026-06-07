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
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By

def dump_page():
    config = load_config()
    options = Options()
    options.binary_location = config.get("firefox_binary")
    options.accept_insecure_certs = True
    options.add_argument("-profile")
    options.add_argument(config.get("firefox_profile_path"))

    service = Service(executable_path=config.get("geckodriver_path"))
    driver = webdriver.Firefox(service=service, options=options)

    try:
        url = f"{config.get('zesje_base_url')}/exams/{config.get('exam_id')}/grade/1/1"
        print(f"Loading {url}...")
        driver.get(url)
        time.sleep(5)  # Let it fully render

        html = driver.page_source
        dump_filepath = os.path.join(DATA_DIR, "zesje_page_dump.html")
        with open(dump_filepath, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved to {dump_filepath}")

        buttons = driver.find_elements(By.CSS_SELECTOR, "button, [role='button'], label, .btn")
        print(f"\nFound {len(buttons)} button-like elements:")
        for i, btn in enumerate(buttons):
            classes = btn.get_attribute("class") or ""
            text = btn.text.strip()[:60]
            tag = btn.tag_name
            print(f"  [{i}] <{tag}> class=\"{classes}\" text=\"{text}\"")

    finally:
        input("\nPress Enter to close browser...")
        driver.quit()

if __name__ == "__main__":
    dump_page()
