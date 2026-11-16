import os
import sys
import json
import argparse
import re
import time
import shutil
import sqlite3
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = SCRIPT_DIR

# Windows UTF-8 guardrail
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

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

def extract_cookies_from_firefox(profile_path, host):
    """Extract session cookies from Firefox profile for the exact host."""
    if not profile_path or not os.path.exists(profile_path):
        return {}
    
    # Copy cookies.sqlite to temp dir to avoid locking the live profile
    temp_dir = tempfile.mkdtemp(prefix="zesje_cookies_")
    cookies_src = os.path.join(profile_path, "cookies.sqlite")
    cookies_dst = os.path.join(temp_dir, "cookies.sqlite")
    
    try:
        if not os.path.exists(cookies_src):
            return {}
        shutil.copy2(cookies_src, cookies_dst)
        # Also copy WAL/SHM if they exist
        for suffix in ("-wal", "-shm"):
            src = cookies_src + suffix
            dst = cookies_dst + suffix
            if os.path.exists(src):
                shutil.copy2(src, dst)
    except Exception:
        return {}
    
    cookies = {}
    try:
        conn = sqlite3.connect(f"file:{cookies_dst}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Filter by EXACT host match to avoid cross-subdomain contamination
        cursor.execute("""
            SELECT name, value, host, path, expiry, isSecure, isHttpOnly
            FROM moz_cookies
            WHERE host = ?
        """, (host,))
        
        for row in cursor.fetchall():
            # Only include non-expired cookies
            expiry = row['expiry']
            if expiry and expiry > 0 and expiry < int(time.time()):
                continue
            cookies[row['name']] = row['value']
        
        conn.close()
    except Exception:
        pass
    finally:
        # Clean up temp files
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
    
    return cookies

def test_api_endpoints(base_url, exam_id, cookies, config):
    """Test /api/exams/<id> and /api/export/xlsx_detailed/<id> endpoints."""
    host = urlparse(base_url).netloc
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items()) if cookies else ""
    
    results = {
        "exams": {"status": None, "data": None, "error": None},
        "export": {"status": None, "data": None, "error": None}
    }
    
    # Test /api/exams/<id>
    exams_url = f"{base_url}/api/exams/{exam_id}"
    try:
        req = Request(exams_url, headers={"Cookie": cookie_header} if cookie_header else {})
        with urlopen(req, timeout=15) as resp:
            results["exams"]["status"] = resp.status
            results["exams"]["data"] = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        results["exams"]["status"] = e.code
        results["exams"]["error"] = str(e)
    except URLError as e:
        results["exams"]["error"] = str(e)
    except Exception as e:
        results["exams"]["error"] = str(e)
    
    # Test /api/export/xlsx_detailed/<id>
    export_url = f"{base_url}/api/export/xlsx_detailed/{exam_id}"
    try:
        req = Request(export_url, headers={"Cookie": cookie_header} if cookie_header else {})
        with urlopen(req, timeout=30) as resp:
            results["export"]["status"] = resp.status
            results["export"]["data"] = resp.read()
    except HTTPError as e:
        results["export"]["status"] = e.code
        results["export"]["error"] = str(e)
    except URLError as e:
        results["export"]["error"] = str(e)
    except Exception as e:
        results["export"]["error"] = str(e)
    
    return results

def handle_auth_fallback(config, exam_id, course_name):
    """Graceful fallback on auth expiry: prompt for manual download or skip."""
    exports_dir = os.path.join(REPO_ROOT, config["data_dir"], "exports")
    os.makedirs(exports_dir, exist_ok=True)
    
    print("\n" + "=" * 65)
    print("AUTHENTICATION EXPIRED OR INVALID")
    print("=" * 65)
    print(f"API endpoints returned 401/403. Session cookies may have expired.")
    print()
    print("Options:")
    print(f"  1. Place manual XLSX export in: {exports_dir}")
    print("     (Download from Zesje UI: Exam → Export → Detailed XLSX)")
    print("  2. Press 's' to skip API pre-pull and continue setup")
    print()
    
    while True:
        choice = input("Choice [1/s]: ").strip().lower()
        if choice == 's':
            return {"action": "skip", "cross_ref": "Sheet reading error"}
        
        if choice == '1' or choice == '':
            # Check if file exists in exports dir
            xlsx_files = [f for f in os.listdir(exports_dir) if f.endswith('.xlsx')]
            if not xlsx_files:
                print(f"   No .xlsx files found in {exports_dir}. Please place the file and try again.")
                continue
            
            # Use the most recent file
            latest_file = max(xlsx_files, key=lambda f: os.path.getmtime(os.path.join(exports_dir, f)))
            file_path = os.path.join(exports_dir, latest_file)
            
            print(f"   Found: {latest_file}")
            print("   Attempting cross-reference verification...")
            
            # Try to read the file and verify structure
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, read_only=True)
                ws = wb.active
                
                # Check for expected 3-tier header structure
                row1 = [cell.value for cell in ws[1]] if ws.max_row >= 1 else []
                row2 = [cell.value for cell in ws[2]] if ws.max_row >= 2 else []
                row3 = [cell.value for cell in ws[3]] if ws.max_row >= 3 else []
                
                # Look for "Student ID" in row 3 (anchor row)
                has_student_id = any("student id" in str(v).lower() for v in row3 if v)
                has_questions = any(v and str(v).strip() for v in row1)
                
                wb.close()
                
                if has_student_id and has_questions:
                    print("   [OK] Cross-reference structure verified.")
                    return {"action": "manual", "file": file_path, "cross_ref": "Successfully cross referenced"}
                else:
                    print("   [WARN] Sheet structure doesn't match expected format.")
                    return {"action": "manual", "file": file_path, "cross_ref": "Sheet didn't update"}
            except Exception as e:
                print(f"   [ERROR] Could not read XLSX: {e}")
                return {"action": "manual", "file": file_path, "cross_ref": "Sheet reading error"}
        
        print("   Invalid choice. Enter '1' to use manual file or 's' to skip.")

def main(argv=None):
    parser = argparse.ArgumentParser(description="Initialize an exam-specific offline grading folder.")
    parser.add_argument("--label", required=True, help="Folder label for the exam, e.g. endterm")
    parser.add_argument("--course", help="Course slug used in the exam folder name")
    parser.add_argument("--from-export", metavar="EXPORT_JSON", help="Build a config offline from a saved exam export")
    parser.add_argument("--questions", metavar="ID=LABEL,...", help="Problem ids and labels for --from-export")
    parser.add_argument("--base-url", default="https://tn22010-2026.zesje.tudelft.nl",
                        help="Zesje base URL for --from-export; default is the current grading instance")
    args = parser.parse_args(argv)
    if not args.label.strip():
        parser.error("--label must not be empty")
    if args.from_export:
        if not args.questions:
            parser.error("--questions is required with --from-export")
        setup_from_export(args, parser)
        return

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
    if args.course:
        course_name = args.course.strip().lower()
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

        # COOKIE HARVESTING: Extract session cookies from Firefox profile after login
        host = urlparse(base_url).netloc
        cookies = extract_cookies_from_firefox(config.get("firefox_profile_path", ""), host)
        if cookies:
            config["cookies"] = cookies
            print(f"   -> Harvested {len(cookies)} session cookies for {host}")
        else:
            print(f"   [WARN] No cookies found for {host}. API calls may fail.")
            config["cookies"] = {}

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
        dataset_dir_name = f"{args.label.strip()}_{course_name}_exam{exam_id}" if course_name else f"{args.label.strip()}_exam{exam_id}"
        dataset_dir = os.path.join(REPO_ROOT, "data", dataset_dir_name)
        config["data_dir"] = os.path.relpath(dataset_dir, REPO_ROOT).replace(os.sep, "/")
        dataset_config_path = os.path.join(dataset_dir, "config.json")
        if os.path.exists(dataset_config_path):
            raise FileExistsError(f"Refusing to overwrite existing exam config: {dataset_config_path}")
        os.makedirs(dataset_dir, exist_ok=True)

        # API PRE-PULL: Test authentication with harvested cookies
        print("\n" + "=" * 65)
        print("5. API PRE-PULL VERIFICATION")
        print("=" * 65)
        print("Testing API endpoints with harvested session cookies...")
        api_results = test_api_endpoints(base_url, exam_id, config.get("cookies", {}), config)
        
        exams_ok = api_results["exams"]["status"] == 200
        export_ok = api_results["export"]["status"] == 200
        
        if exams_ok and export_ok:
            print("   [OK] /api/exams/<id>        -> 200 OK")
            print("   [OK] /api/export/xlsx_detailed/<id> -> 200 OK")
            print("   Authentication verified successfully.")
        else:
            print(f"   [FAIL] /api/exams/<id>        -> {api_results['exams']['status'] or 'ERROR'}")
            print(f"   [FAIL] /api/export/xlsx_detailed/<id> -> {api_results['export']['status'] or 'ERROR'}")
            
            # Check for auth expiry (401/403)
            auth_expired = any(
                api_results[key]["status"] in (401, 403) 
                for key in ("exams", "export") 
                if api_results[key]["status"]
            )
            
            if auth_expired:
                fallback = handle_auth_fallback(config, exam_id, course_name)
                config["auth_fallback"] = fallback
                if fallback["action"] == "manual":
                    config["manual_export_path"] = fallback["file"]
                    print(f"   Cross-reference: {fallback['cross_ref']}")
                else:
                    print("   Skipping API pre-pull. Manual export will be needed later.")
            else:
                print("   Non-auth error. Check network or API availability.")
                config["auth_fallback"] = {"action": "error", "cross_ref": "Sheet reading error"}

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

        # Save the config only in this exam's folder.
        with open(dataset_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

        print("\n" + "=" * 65)
        print(f"[SUCCESS] Config saved to data/{dataset_dir_name}/config.json.")
        print("Configuration summary:")
        print(f"  Base URL:         {config['zesje_base_url']}")
        print(f"  Exam ID:          {config['exam_id']}")
        print(f"  Questions:        {config['problem_mapping']}")
        print(f"  Extra Pages:      {config['n_extra_pages']}")
        print(f"  Total Students:   {config['total_students']}")
        print("=" * 65)

    finally:
        driver.quit()

def setup_from_export(args, parser):
    """Build the exam config from a saved /api/exams/<id> JSON. No browser, no login, no network."""
    with open(args.from_export, encoding="utf-8") as f:
        export = json.load(f)

    exam_id = int(export["id"])
    exam_name = export.get("name", "")
    problems = {int(p["id"]): p for p in export.get("problems", [])}
    n_students = len(export.get("submissions", []))

    mapping = {}
    for pair in args.questions.split(","):
        pid_text, sep, label = pair.partition("=")
        try:
            pid = int(pid_text.strip())
        except ValueError:
            parser.error(f"bad problem id in --questions: {pair!r}")
        if not sep or not label.strip():
            parser.error(f"expected ID=LABEL, got {pair!r}")
        if pid not in problems:
            parser.error(f"problem id {pid} is not in this export")
        mapping[str(pid)] = label.strip()

    n_extra = sum(1 for p in problems.values() if str(p.get("name", "")).lower().startswith("extra"))

    course = args.course.strip().lower() if args.course else None
    if not course:
        m = re.search(r"\b(TN\d+[A-Za-z]*)\b", exam_name, re.IGNORECASE)
        course = m.group(1).lower() if m else f"exam{exam_id}"

    label = args.label.strip()
    dataset_dir_name = f"{label}_{course}_exam{exam_id}"
    dataset_dir = os.path.join(REPO_ROOT, "data", dataset_dir_name)
    dataset_config_path = os.path.join(dataset_dir, "config.json")
    if os.path.exists(dataset_config_path):
        parser.error(f"Refusing to overwrite existing exam config: data/{dataset_dir_name}/config.json")
    os.makedirs(dataset_dir, exist_ok=True)

    config = {
        "zesje_base_url": args.base_url.rstrip("/"),
        "course_name": course,
        "exam_id": exam_id,
        "exam_name": exam_name,
        "data_dir": os.path.relpath(dataset_dir, REPO_ROOT).replace(os.sep, "/"),
        "problem_mapping": mapping,
        "n_extra_pages": n_extra,
        "total_students": n_students,
        "setup_source": os.path.basename(args.from_export),
    }

    with open(dataset_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    print(f"[SUCCESS] data/{dataset_dir_name}/config.json written from the saved export; no login or network used.")
    print(f"  Exam ID: {exam_id}")
    print(f"  Problems: {len(problems)}")
    print(f"  Submissions: {n_students}")


if __name__ == "__main__":
    main()
