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
from seleniumwire import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class ImageOrError:
    def __init__(self, selector):
        self.selector = selector

    def __call__(self, driver):
        elements = driver.find_elements(By.CSS_SELECTOR, self.selector)
        if elements:
            return elements[0]
        try:
            text = driver.find_element(By.TAG_NAME, "body").text
            if "Oops" in text or "does not exist" in text:
                return "ERROR"
        except Exception:
            pass
        return False

def get_interactive_config():
    config = load_config()
    print("\n=== ZESJE SCRAPER CONFIGURATION ===")
    print("Press Enter to keep the default value in brackets.")
    
    base_url = input(f"Zesje Base URL [{config['zesje_base_url']}]: ").strip()
    if base_url:
        config['zesje_base_url'] = base_url
        
    exam_id_str = input(f"Exam ID [{config['exam_id']}]: ").strip()
    if exam_id_str:
        config['exam_id'] = int(exam_id_str)
        
    total_students_str = input(f"Number of Students [{config['total_students']}]: ").strip()
    if total_students_str:
        config['total_students'] = int(total_students_str)
        
    profile_path = input(f"Firefox Profile Path [{config['firefox_profile_path']}]: ").strip()
    if profile_path:
        config['firefox_profile_path'] = profile_path
        
    mapping_str = input("Problem specification (e.g. 1:1a, 2:1b, 3:1b_ext) [Default]: ").strip()
    if mapping_str:
        try:
            new_map = {}
            for item in mapping_str.split(","):
                k, v = item.split(":")
                new_map[k.strip()] = v.strip()
            config['problem_mapping'] = new_map
        except Exception as e:
            print(f"Invalid format ({e}). Keeping default.")
            
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    print("Settings saved to config.json!\n")
    return config

def setup_driver(config):
    options = Options()
    options.binary_location = config.get("firefox_binary")
    options.accept_insecure_certs = True
    options.add_argument("-profile")
    options.add_argument(config.get("firefox_profile_path"))
    
    options.set_preference("browser.cache.disk.enable", False)
    options.set_preference("browser.cache.memory.enable", False)
    options.set_preference("browser.cache.offline.enable", False)
    options.set_preference("network.http.use-cache", False)
    
    service = Service(executable_path=config.get("geckodriver_path"))
    return webdriver.Firefox(service=service, options=options)

def scrape():
    config = load_config()
    print("=== ZESJE IMAGE SCRAPER ===")
    print("1. Run with current config.json settings")
    print("2. Enter new settings (Interactive)")
    choice = input("Select option (1/2): ").strip()
    
    if choice == "2":
        config = get_interactive_config()
        
    output_dir = os.path.join(DATA_DIR, "zesje_images")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("IMPORTANT: Close main Firefox window first!")
    driver = setup_driver(config)

    try:
        driver.get(config.get("zesje_base_url"))
        print("\nNavigated to base URL. Waiting a few seconds for the page to initialize...")
        time.sleep(5)

        url_template = config.get("zesje_base_url") + "/exams/" + str(config.get("exam_id")) + "/grade/{submission_id}/{problem_id}"

        for problem_id, problem_name in config.get("problem_mapping").items():
            print(f"\n--- Scraping Problem: {problem_name} (URL suffix: /{problem_id}) ---")
            
            problem_dir = os.path.join(output_dir, problem_name)
            if not os.path.exists(problem_dir):
                os.makedirs(problem_dir)

            consecutive_errors = 0
            MAX_ERRORS = 10
            submission_id = 1
            max_students = config.get("total_students", 121)
            
            while submission_id <= max_students:
                filename = os.path.join(problem_dir, f"sub_{submission_id}.png")
                if os.path.exists(filename):
                    print(f"-> Skipping submission {submission_id} (already exists).")
                    consecutive_errors = 0
                    submission_id += 1
                    continue

                url = url_template.format(submission_id=submission_id, problem_id=problem_id)
                print(f"Loading: {url}")
                
                del driver.requests
                driver.get(url)

                IMAGE_SELECTOR = 'img'

                try:
                    result = WebDriverWait(driver, 10).until(
                        ImageOrError(IMAGE_SELECTOR)
                    )
                    
                    if result == "ERROR":
                        print(f"-> Submission {submission_id} does not exist (Error page detected).")
                        consecutive_errors += 1
                    else:
                        img_element = result
                        time.sleep(0.5)

                        filename = os.path.join(problem_dir, f"sub_{submission_id}.png")
                        img_element.screenshot(filename)
                        print(f"-> Saved screenshot: {filename}")
                        consecutive_errors = 0

                except Exception as e:
                    print(f"-> Warning: Timed out waiting for image on submission {submission_id}.")
                    consecutive_errors += 1

                if consecutive_errors >= MAX_ERRORS:
                    print(f"Hit {MAX_ERRORS} missing submissions in a row. Moving to next problem.")
                    break

                submission_id += 1

    except KeyboardInterrupt:
        print("\nStopped manually by user.")
    except Exception as e:
        print(f"\nError occurred: {e}")
    finally:
        print("Closing browser...")
        driver.quit()

if __name__ == "__main__":
    scrape()
