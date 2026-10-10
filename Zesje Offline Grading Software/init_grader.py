import os
import sys
import json
import re
import time
from urllib.parse import urlparse

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = SCRIPT_DIR
CONFIG_PATH = os.path.join(REPO_ROOT, "config.json")

def clean_url(raw_url):
    raw_url = raw_url.strip().strip("'\"")
    # Clean whitespace and trailing slashes
    raw_url = re.sub(r"\s+", "", raw_url)
    raw_url = raw_url.rstrip("/")
    return raw_url

def parse_exam_url(url):
    url = clean_url(url)
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    exam_id = None
    match = re.search(r"/exams/(\d+)", parsed.path)
    if match:
        exam_id = int(match.group(1))
        
    return base_url, exam_id

def detect_firefox_profile():
    appdata = os.environ.get("APPDATA", "")
    profiles_dir = os.path.join(appdata, "Mozilla", "Firefox", "Profiles")
    if not os.path.exists(profiles_dir):
        return ""
    import glob
    candidates = glob.glob(os.path.join(profiles_dir, "*default-release*"))
    if not candidates:
        candidates = glob.glob(os.path.join(profiles_dir, "*"))
    if candidates:
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidates[0]
    return ""

def main():
    print("=" * 65)
    print("      ZESJE OFFLINE GRADER - INTERACTIVE SETUP WIZARD")
    print("=" * 65)
    print()

    # STAP 1: Exam Link input (auto-cleans spaces & formatting)
    default_link = "https://tn22010-2026.zesje.tudelft.nl/exams/2"
    raw_input_url = input(f"1. Paste Zesje Exam Link [{default_link}]: ").strip()
    if not raw_input_url:
        raw_input_url = default_link

    base_url, exam_id = parse_exam_url(raw_input_url)
    if not exam_id:
        print("   Could not detect exam ID from URL. Please enter manually.")
        exam_id = int(input("   Exam ID (number): ").strip())

    print(f"   -> Detected Base URL: {base_url}")
    print(f"   -> Detected Exam ID:  {exam_id}")
    print()

    # Load existing config or defaults
    config = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass

    config["zesje_base_url"] = base_url
    config["exam_id"] = exam_id
    if not config.get("firefox_profile_path"):
        config["firefox_profile_path"] = detect_firefox_profile()
    if not config.get("firefox_binary"):
        config["firefox_binary"] = r"C:\Program Files\Mozilla Firefox\firefox.exe"
    if not config.get("geckodriver_path"):
        config["geckodriver_path"] = os.path.join(REPO_ROOT, "geckodriver.exe")

    # STAP 2: Open Browser and instruct navigation
    print("=" * 65)
    print("2. OPENING BROWSER FOR INTERACTIVE QUESTION DISCOVERY")
    print("=" * 65)
    print("A browser window will now open.")
    print("  a. Log in with your NetID / SSO if needed.")
    print("  b. Navigate to the exam overview or a submission page.")
    print("=" * 65)
    
    from selenium import webdriver
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.firefox.options import Options

    options = Options()
    if os.path.exists(config["firefox_binary"]):
        options.binary_location = config["firefox_binary"]
    options.accept_insecure_certs = True
    if config["firefox_profile_path"] and os.path.exists(config["firefox_profile_path"]):
        options.add_argument("-profile")
        options.add_argument(config["firefox_profile_path"])

    service = Service(executable_path=config["geckodriver_path"])
    driver = webdriver.Firefox(service=service, options=options)

    try:
        landing_url = f"{base_url}/exams/{exam_id}"
        driver.get(landing_url)
        time.sleep(2)

        input("\n>>> Logged in and ready? Press [ENTER] to configure questions... ")

        # Interactive Question Logging
        print("\n" + "=" * 65)
        print("3. LOGGING QUESTIONS TO GRADE")
        print("=" * 65)
        print("Navigate to the questions you need to grade, or type their IDs.")
        print("Example: If your URL ends in .../grade/1/1 and .../grade/1/9, the IDs are 1 and 9.")
        print("Current browser URL:", driver.current_url)
        print("-" * 65)

        problem_mapping = {}
        while True:
            q_name = input("Enter Question Label (e.g. Q1, Q8, 1a, 1b) [or press Enter when done]: ").strip()
            if not q_name:
                break
            
            # Check if current URL contains a problem ID
            curr_match = re.search(r"/grade/\d+/(\d+)", driver.current_url)
            suggested_id = curr_match.group(1) if curr_match else "1"
            
            p_id = input(f"Enter Problem ID for {q_name} [{suggested_id}]: ").strip()
            if not p_id:
                p_id = suggested_id
            
            problem_mapping[p_id] = q_name
            print(f"  -> Logged: Problem ID {p_id} = '{q_name}'\n")

        if not problem_mapping:
            # Fallback to defaults if user pressed enter immediately
            problem_mapping = config.get("problem_mapping", {"1": "Q1", "9": "Q8"})

        config["problem_mapping"] = problem_mapping

        # Extra Pages / Continuation handling
        print("=" * 65)
        print("4. EXTRA PAGES / BLANKS DISCOVERY")
        print("=" * 65)
        extra_pages_str = input("How many (N) extra space / continuation pages does this exam have? [0]: ").strip()
        n_extra = int(extra_pages_str) if extra_pages_str.isdigit() else 0

        if n_extra > 0:
            print(f"Exam has {n_extra} extra pages. These will be mapped from the tail problem IDs.")
            config["n_extra_pages"] = n_extra
        else:
            config["n_extra_pages"] = 0

        # Total students
        tot_students_str = input(f"Total number of students [{config.get('total_students', 134)}]: ").strip()
        if tot_students_str.isdigit():
            config["total_students"] = int(tot_students_str)

        # Save config
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

        print("\n" + "=" * 65)
        print("[SUCCESS] config.json successfully created and saved!")
        print("Configuration summary:")
        print(f"  Base URL:         {config['zesje_base_url']}")
        print(f"  Exam ID:          {config['exam_id']}")
        print(f"  Questions:        {config['problem_mapping']}")
        print(f"  Extra Pages:      {config['n_extra_pages']}")
        print(f"  Total Students:   {config['total_students']}")
        print("=" * 65)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
