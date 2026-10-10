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
    
    # Extract course tag (e.g. 'tn2211' from 'tn2211-2026.zesje.tudelft.nl' or 'tn22010')
    host = parsed.netloc.split(".")[0]
    course_name = host.split("-")[0] if "-" in host else host
    
    exam_id = None
    match = re.search(r"/exams/(\d+)", parsed.path)
    if match:
        exam_id = int(match.group(1))
        
    return base_url, exam_id, course_name

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

    base_url, exam_id, course_name = parse_exam_url(raw_input_url)
    if not exam_id:
        print("   [i] Geen exam ID direct in link gevonden.")
        print("       Geen zorgen: de browser opent zo meteen de site. Navigeer naar het gewenste")
        print("       examen of grading scherm, dan leest het script het Exam ID automatisch uit!")
        exam_id = None

    # Load existing config or defaults
    config = {}
    config["zesje_base_url"] = base_url
    config["course_name"] = course_name
    if not config.get("firefox_profile_path"):
        config["firefox_profile_path"] = detect_firefox_profile()
    if not config.get("firefox_binary"):
        config["firefox_binary"] = r"C:\Program Files\Mozilla Firefox\firefox.exe"
    if not config.get("geckodriver_path"):
        config["geckodriver_path"] = os.path.join(REPO_ROOT, "geckodriver.exe")

    # STAP 2: Open Browser and instruct navigation
    print("=" * 65)
    print("2. OPENING BROWSER FOR INTERACTIVE DISCOVERY")
    print("=" * 65)
    print("A browser window will now open.")
    print("  a. Log in with your NetID / SSO if needed.")
    print("  b. Navigeer naar het specifieke examen of grading overzicht.")
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
        landing_url = f"{base_url}/exams/{exam_id}" if exam_id else base_url
        driver.get(landing_url)
        time.sleep(2)

        input("\n>>> Klaar met inloggen & genavigeerd naar het examen? Druk op [ENTER]... ")

        # If exam_id wasn't known yet, extract it live from browser URL
        if not exam_id:
            curr_url = driver.current_url
            m_exam = re.search(r"/exams/(\d+)", curr_url)
            if m_exam:
                exam_id = int(m_exam.group(1))
                print(f"   -> Automatisch Exam ID {exam_id} gedetecteerd uit URL!")
            else:
                exam_id_input = input("   Exam ID kon niet uit URL gehaald worden. Voer Exam ID in (getal): ").strip()
                exam_id = int(exam_id_input) if exam_id_input.isdigit() else 1

        config["exam_id"] = exam_id
        dataset_dir_name = f"data_{course_name}_exam{exam_id}" if course_name else f"data_exam{exam_id}"
        dataset_dir = os.path.join(REPO_ROOT, dataset_dir_name)
        os.makedirs(dataset_dir, exist_ok=True)
        config["data_dir"] = dataset_dir_name
        dataset_config_path = os.path.join(dataset_dir, "config.json")

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

        # Save config in dataset-specific folder and update active root config
        with open(dataset_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

        print("\n" + "=" * 65)
        print(f"[SUCCESS] Config saved to {dataset_dir_name}/config.json and active config.json!")
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
