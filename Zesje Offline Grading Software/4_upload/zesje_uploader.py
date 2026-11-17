#!/usr/bin/env python3
"""
Zesje Differential Uploader - Generic & Config-Driven

Features:
- Config-driven: reads everything from config.json + rubric_mapping.json + populated_grades.xlsx
- Pre-pull live state via API (/api/exams/<id>, /api/export/xlsx_detailed/<id>)
- Delta computation: minimal keystrokes to reconcile target vs current state
- Mutual exclusion handling for "All correct" options
- Stateful Set Aside toggle ('a' key) with button label detection
- Post-verification: re-pull and verify 100% match
- Progress logging + exception logging
- CLI: --dry-run, --student, --problem, --resume
"""

import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
import sqlite3
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from openpyxl import load_workbook


SCRIPT_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))
from exam_config import add_exam_argument, load_exam_config_from_args


def get_course_paths(config: Dict[str, Any]) -> Tuple[Path, Path, Path, Path]:
    """Resolve the selected exam's grading files."""
    base = Path(config["exam_dir"])
    rubric_path = base / "rubric_mapping.json"
    populated_path = base / "populated" / "populated_grades.xlsx"
    progress_path = base / "upload_progress.txt"
    exceptions_path = base / "grading_exceptions.json"

    return rubric_path, populated_path, progress_path, exceptions_path


def _zesje_keystroke(index: int) -> str:
    """Map 0-based rubric option index to Zesje UI shortcut ('1'..'9', '0' for 10th)."""
    return "0" if index == 9 else str(index + 1)


def load_rubric_mapping(rubric_path: Path) -> Dict[str, Any]:
    """Load rubric mapping with keystroke -> feedback_id mapping."""
    if not rubric_path.exists():
        raise FileNotFoundError(f"Rubric mapping not found: {rubric_path}")
    with open(rubric_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_populated_grades(populated_path: Path) -> List[Dict[str, Any]]:
    """Load populated grades from XLSX."""
    if not populated_path.exists():
        raise FileNotFoundError(f"Populated grades not found: {populated_path}")

    wb = load_workbook(populated_path, data_only=True)
    ws = wb.active

    # Parse header row (row 3) to find column indices
    student_id_col = None
    set_aside_col = None
    grading_status_col = None
    criteria_columns = []
    remarks_col = None

    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=3, column=col)
        if cell.value:
            h = str(cell.value).strip().lower()
            if "student id" in h:
                student_id_col = col
            elif "set aside" in h:
                set_aside_col = col
            elif "grading status" in h:
                grading_status_col = col
            elif "remark" in h:
                remarks_col = col
            else:
                criteria_columns.append(col)

    if not student_id_col:
        raise ValueError("Could not find 'Student ID' column in row 3")

    students = []
    for row in range(4, ws.max_row + 1):
        cell = ws.cell(row=row, column=student_id_col)
        if not cell.value:
            continue
        student_id = str(cell.value).strip()

        criteria = {}
        for i, crit_col in enumerate(criteria_columns):
            val = ws.cell(row=row, column=crit_col).value
            if val is not None and str(val).strip() in ("1", "1.0", 1, True):
                criteria[_zesje_keystroke(i)] = 1

        set_aside_val = ws.cell(row=row, column=set_aside_col).value if set_aside_col else "FALSE"
        set_aside = str(set_aside_val).strip().upper() == "TRUE"

        grading_status = ws.cell(row=row, column=grading_status_col).value if grading_status_col else "PENDING"
        grading_status = str(grading_status).strip().upper()

        remarks = ws.cell(row=row, column=remarks_col).value if remarks_col else ""
        remarks = str(remarks).strip() if remarks else ""

        students.append({
            "student_id": student_id,
            "criteria": criteria,
            "set_aside": set_aside,
            "grading_status": grading_status,
            "remarks": remarks
        })

    return students


def load_progress(progress_path: Path) -> Set[str]:
    """Load uploaded progress keys."""
    if not progress_path.exists():
        return set()
    with open(progress_path, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_progress(progress_path: Path, key: str):
    """Append progress key."""
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with open(progress_path, "a", encoding="utf-8") as f:
        f.write(key + "\n")


def load_exceptions(exceptions_path: Path) -> List[Dict[str, Any]]:
    """Load exceptions log."""
    if not exceptions_path.exists():
        return []
    with open(exceptions_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_exceptions(exceptions_path: Path, exceptions: List[Dict[str, Any]]):
    """Save exceptions log."""
    exceptions_path.parent.mkdir(parents=True, exist_ok=True)
    with open(exceptions_path, "w", encoding="utf-8") as f:
        json.dump(exceptions, f, indent=2)


def setup_driver(config: Dict[str, Any]) -> webdriver.Firefox:
    """Initialize Firefox driver with profile."""
    options = Options()
    if config.get("firefox_binary") and Path(config["firefox_binary"]).exists():
        options.binary_location = config["firefox_binary"]
    options.accept_insecure_certs = True
    if config.get("firefox_profile_path") and Path(config["firefox_profile_path"]).exists():
        options.add_argument("-profile")
        options.add_argument(config["firefox_profile_path"])

    options.set_preference("network.proxy.type", 0)
    options.set_preference("browser.cache.disk.enable", False)
    options.set_preference("browser.cache.memory.enable", False)
    options.set_preference("browser.cache.offline.enable", False)

    gecko_path = config.get("geckodriver_path", "geckodriver.exe")
    service = Service(executable_path=gecko_path)
    return webdriver.Firefox(service=service, options=options)


def extract_cookies_from_driver(driver: webdriver.Firefox) -> Dict[str, str]:
    """Extract cookies from Selenium driver."""
    return {c['name']: c['value'] for c in driver.get_cookies()}


def extract_cookies_from_profile(profile_path: Optional[str], host: Optional[str] = None) -> Dict[str, str]:
    """Extract cookies from Firefox profile SQLite database without running browser."""
    if not profile_path:
        return {}
    p = Path(profile_path)
    cookie_db = p / "cookies.sqlite"
    if not cookie_db.exists():
        return {}
    try:
        conn = sqlite3.connect(cookie_db)
        c = conn.cursor()
        if host:
            c.execute("SELECT name, value FROM moz_cookies WHERE host LIKE ?", (f"%{host}%",))
        else:
            c.execute("SELECT name, value FROM moz_cookies")
        cookies = {name: val for name, val in c.fetchall()}
        conn.close()
        return cookies
    except Exception as e:
        print(f"[WARN] Failed to read cookies from profile: {e}")
        return {}


def parse_live_exams_json(
    exams_data: Dict[str, Any],
    rubric_mapping: Dict[str, Any]
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """
    Parse /api/exams/<id> JSON directly for 100% accurate ground-truth live state.
    Returns:
        (live_state, student_to_sub_id_map)
    """
    problem_opt_map = {}
    for r_key, r_val in rubric_mapping.items():
        if r_key.startswith("_") or r_key == "instructions":
            continue
        pid = str(r_val.get("problem_id", ""))
        problem_opt_map[pid] = {
            int(opt["feedback_id"]): str(opt["keystroke"])
            for opt in r_val.get("options", [])
            if "feedback_id" in opt and "keystroke" in opt
        }

    live_state = {}
    student_to_sub = {}

    for sub in exams_data.get("submissions", []):
        sub_id = str(sub["id"])
        stud = sub.get("student")
        s_num = str(stud["id"]) if stud and stud.get("id") else sub_id
        student_to_sub[s_num] = sub_id
        student_to_sub[sub_id] = sub_id

        for prob in sub.get("problems", []):
            pid = str(prob.get("problemId", ""))
            fb = prob.get("feedback", [])
            opt_map = problem_opt_map.get(pid, {})
            crit = {opt_map[o]: 1 for o in fb if o in opt_map}
            graded_by = prob.get("gradedBy")
            set_aside = (graded_by is None)
            rem = prob.get("remark", "") or ""

            entry = {
                "submission_id": sub_id,
                "student_id": s_num,
                "problem_id": pid,
                "criteria": crit,
                "remarks": rem,
                "set_aside": set_aside,
                "feedback": fb,
                "grading_status": "SET_ASIDE" if set_aside else "GRADED"
            }
            live_state[f"{s_num}:{pid}"] = entry
            live_state[f"{sub_id}:{pid}"] = entry

    return live_state, student_to_sub



def api_prepull(base_url: str, exam_id: int, cookies: Dict[str, str]) -> Tuple[Optional[Dict], Optional[bytes]]:
    """Pre-pull live state from Zesje API."""
    host = urlparse(base_url).netloc
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items()) if cookies else ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
    }
    if cookie_header:
        headers["Cookie"] = cookie_header

    exams_data = None
    export_data = None

    # /api/exams/<id>
    exams_url = f"{base_url}/api/exams/{exam_id}"
    try:
        req = Request(exams_url, headers=headers)
        with urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                exams_data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, Exception) as e:
        print(f"[WARN] /api/exams/{exam_id} failed: {e}")

    # /api/export/xlsx_detailed/<id>
    export_url = f"{base_url}/api/export/xlsx_detailed/{exam_id}"
    try:
        req = Request(export_url, headers=headers)
        with urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                export_data = resp.read()
    except (HTTPError, URLError, Exception) as e:
        print(f"[WARN] /api/export/xlsx_detailed/{exam_id} failed: {e}")

    return exams_data, export_data


def parse_live_xlsx(export_bytes: bytes, problem_mapping: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """Parse live Zesje detailed export to extract current state per student/problem."""
    import io
    wb = load_workbook(io.BytesIO(export_bytes), data_only=True)
    ws = wb.active

    # Row 1: Question headers (merged)
    # Row 2: Criteria labels
    # Row 3: Student ID, criteria columns, Remarks
    # Row 4+: Data

    # Find problem columns from row 1 merged cells
    problem_cols = {}
    for merged_range in ws.merged_cells.ranges:
        if merged_range.min_row == 1 and merged_range.max_row == 1:
            q_label = ws.cell(row=1, column=merged_range.min_col).value
            if q_label:
                q_str = str(q_label).strip()
                for prob_id, prob_name in problem_mapping.items():
                    if prob_name.upper() in q_str.upper() or prob_name.lower() in q_str.lower():
                        problem_cols[prob_id] = (merged_range.min_col, merged_range.max_col)

    # Fallback: use problem_mapping order
    if not problem_cols:
        for i, (prob_id, prob_name) in enumerate(problem_mapping.items()):
            start_col = 2 + i * 7
            problem_cols[prob_id] = (start_col, start_col + 6)

    # Row 3: Find Student ID column and criteria columns per problem
    student_id_col = None
    problem_criteria_cols = {}
    remarks_cols = {}

    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=3, column=col)
        if cell.value:
            val = str(cell.value).strip().lower()
            if "student id" in val:
                student_id_col = col

    # Map criteria columns to problems
    for prob_id, (start_col, end_col) in problem_cols.items():
        criteria = []
        remarks_col = None
        for col in range(start_col, min(end_col + 1, ws.max_column + 1)):
            cell = ws.cell(row=3, column=col)
            if cell.value:
                val = str(cell.value).strip().lower()
                if "remark" in val:
                    remarks_col = col
                else:
                    criteria.append(col)
        if criteria:
            problem_criteria_cols[prob_id] = criteria
        if remarks_col:
            remarks_cols[prob_id] = remarks_col

    # Extract student data
    live_state = {}
    if student_id_col:
        for row in range(4, ws.max_row + 1):
            cell = ws.cell(row=row, column=student_id_col)
            if not cell.value:
                continue
            student_id = str(cell.value).strip()

            for prob_id in problem_mapping.keys():
                criteria_vals = {}
                criteria_cols = problem_criteria_cols.get(prob_id, [])
                for i, crit_col in enumerate(criteria_cols):
                    val = ws.cell(row=row, column=crit_col).value
                    if val is not None and str(val).strip() in ("1", "1.0", 1, True):
                        criteria_vals[_zesje_keystroke(i)] = 1

                remarks = ""
                if prob_id in remarks_cols:
                    rval = ws.cell(row=row, column=remarks_cols[prob_id]).value
                    if rval:
                        remarks = str(rval).strip()

                key = f"{student_id}:{prob_id}"
                live_state[key] = {
                    "student_id": student_id,
                    "problem_id": prob_id,
                    "criteria": criteria_vals,
                    "remarks": remarks,
                    "set_aside": False,  # Not in export, need DOM check
                    "grading_status": "UNKNOWN"
                }

    return live_state


def get_rubric_for_problem(rubric_mapping: Dict[str, Any], problem_id: str) -> Dict[str, Any]:
    """Find rubric entry for a problem_id."""
    for key, val in rubric_mapping.items():
        if key.startswith("_") or key == "instructions":
            continue
        if val.get("problem_id") == problem_id:
            return val
    # Fallback: return first non-instruction entry
    for key, val in rubric_mapping.items():
        if not key.startswith("_") and key != "instructions":
            return val
    return {}


def compute_delta(
    target: Dict[str, Any],
    current: Dict[str, Any],
    rubric: Dict[str, Any]
) -> Dict[str, Any]:
    """Compute minimal keystrokes to transform current -> target."""
    delta = {
        "criteria_on": [],      # Keystrokes to turn ON
        "criteria_off": [],     # Keystrokes to turn OFF
        "remarks": None,        # New remarks text if different
        "set_aside": None,      # True/False/None (None = no change)
    }

    # Criteria delta
    target_criteria = set(target.get("criteria", {}).keys())
    current_criteria = set(current.get("criteria", {}).keys())

    # Mutual exclusion: if target has "all_correct" keystroke, must untoggle partials first
    all_correct_key = rubric.get("all_correct_keystroke", "")
    all_incorrect_key = rubric.get("all_incorrect_keystroke", "")
    all_option_keys = {opt["keystroke"] for opt in rubric.get("options", [])}

    # If target wants all_correct, we need to turn OFF any other criteria first
    if all_correct_key in target_criteria:
        # Turn off all other criteria keys except all_correct
        for k in current_criteria:
            if k != all_correct_key and k in all_option_keys:
                delta["criteria_off"].append(k)
        # Turn on all_correct if not already on
        if all_correct_key not in current_criteria:
            delta["criteria_on"].append(all_correct_key)
    else:
        # Normal diff
        for k in target_criteria - current_criteria:
            if k in all_option_keys:
                delta["criteria_on"].append(k)
        for k in current_criteria - target_criteria:
            if k in all_option_keys:
                delta["criteria_off"].append(k)

    # Remarks delta - only update if target explicitly provides a non-empty remark
    target_remarks = target.get("remarks", "")
    current_remarks = current.get("remarks", "")
    if target_remarks and str(target_remarks).strip() and str(target_remarks).strip() != str(current_remarks).strip():
        delta["remarks"] = str(target_remarks).strip()

    # Set Aside delta (stateful)
    target_sa = target.get("set_aside", False)
    current_sa = current.get("set_aside", False)
    if target_sa != current_sa:
        delta["set_aside"] = target_sa

    return delta


def execute_delta(
    driver: webdriver.Firefox,
    delta: Dict[str, Any],
    rubric: Dict[str, Any],
    target: Optional[Dict[str, Any]] = None,
    wait_time: float = 0.2
) -> Tuple[bool, List[str]]:
    """Execute target criteria state and delta in browser via robust DOM manipulation."""
    errors = []

    try:
        # Determine target criteria keys
        if target and "criteria" in target:
            target_keys = [str(k) for k in target["criteria"].keys()]
        else:
            target_keys = [str(k) for k in delta.get("criteria_on", [])]

        # Phase 1: Turn OFF any active feedback items that should NOT be active
        driver.execute_script("""
        const targetKeys = arguments[0];
        const items = Array.from(document.querySelectorAll('.panel-block.feedback-item, a.feedback-item'));
        for (const item of items) {
            const tag = item.querySelector('.tag.is-score');
            if (!tag) continue;
            const key = tag.getAttribute('data-tooltip');
            if (key && tag.classList.contains('is-link') && !targetKeys.includes(key)) {
                item.click();
            }
        }
        """, target_keys)
        time.sleep(0.25)

        # Phase 2: Turn ON any feedback items that SHOULD be active but currently are not
        driver.execute_script("""
        const targetKeys = arguments[0];
        const items = Array.from(document.querySelectorAll('.panel-block.feedback-item, a.feedback-item'));
        for (const item of items) {
            const tag = item.querySelector('.tag.is-score');
            if (!tag) continue;
            const key = tag.getAttribute('data-tooltip');
            if (key && !tag.classList.contains('is-link') && targetKeys.includes(key)) {
                item.click();
            }
        }
        """, target_keys)
        time.sleep(0.25)

        # Remarks (only if target explicitly provides non-empty remarks)
        if delta.get("remarks") is not None:
            try:
                textarea = driver.find_element(By.CSS_SELECTOR, "textarea.remarks, textarea[placeholder*='remark' i], textarea[name*='remark' i]")
                if not textarea:
                    textareas = driver.find_elements(By.TAG_NAME, "textarea")
                    if textareas:
                        textarea = textareas[0]
                if textarea:
                    textarea.clear()
                    time.sleep(0.1)
                    textarea.send_keys(delta["remarks"])
                    time.sleep(wait_time)
                else:
                    errors.append("Remarks textarea not found")
            except Exception as e:
                errors.append(f"Remarks error: {e}")

        # Set Aside - toggle if delta["set_aside"] or target["set_aside"] is specified
        target_sa = delta.get("set_aside")
        if target_sa is None and target and "set_aside" in target:
            target_sa = target["set_aside"]

        if target_sa is not None:
            try:
                btn_info = driver.execute_script("""
                const btn = Array.from(document.querySelectorAll('button')).find(b => {
                    const t = b.innerText.trim().toLowerCase();
                    return t === 'set aside' || t === 'approve';
                });
                return btn ? { text: btn.innerText.trim(), disabled: btn.disabled } : null;
                """)
                if btn_info:
                    btn_text = btn_info["text"].strip().lower()
                    is_currently_sa = ("approve" in btn_text)
                    if target_sa and not is_currently_sa:
                        # Turn Set Aside ON
                        driver.execute_script("""
                        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim().toLowerCase() === 'set aside');
                        if (btn && !btn.disabled) btn.click();
                        """)
                        for _ in range(25):
                            time.sleep(0.1)
                            b_text = driver.execute_script("""
                            const btn = Array.from(document.querySelectorAll('button')).find(b => {
                                const t = b.innerText.trim().toLowerCase();
                                return t === 'set aside' || t === 'approve';
                            });
                            return btn ? btn.innerText.trim().toLowerCase() : '';
                            """)
                            if 'approve' in b_text:
                                break
                    elif not target_sa and is_currently_sa:
                        # Turn Set Aside OFF
                        driver.execute_script("""
                        const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.trim().toLowerCase() === 'approve');
                        if (btn && !btn.disabled) btn.click();
                        """)
                        for _ in range(25):
                            time.sleep(0.1)
                            b_text = driver.execute_script("""
                            const btn = Array.from(document.querySelectorAll('button')).find(b => {
                                const t = b.innerText.trim().toLowerCase();
                                return t === 'set aside' || t === 'approve';
                            });
                            return btn ? btn.innerText.trim().toLowerCase() : '';
                            """)
                            if 'set aside' in b_text:
                                break
                else:
                    errors.append("Set Aside button not found")
            except Exception as e:
                errors.append(f"Set Aside error: {e}")

    except Exception as e:
        errors.append(f"Execution error: {e}")
        return False, errors

    return len(errors) == 0, errors


def verify_state(
    driver: webdriver.Firefox,
    target: Dict[str, Any],
    rubric: Dict[str, Any]
) -> Tuple[bool, List[str]]:
    """Verify browser state matches target after upload."""
    errors = []

    # Read current active criteria and Set Aside status from DOM
    try:
        dom_state = driver.execute_script("""
        const activeKeys = [];
        const items = Array.from(document.querySelectorAll('.panel-block.feedback-item, a.feedback-item'));
        items.forEach(item => {
            const tag = item.querySelector('.tag.is-score');
            if (tag && tag.classList.contains('is-link')) {
                const k = tag.getAttribute('data-tooltip');
                if (k) {
                    activeKeys.push(k);
                }
            }
        });
        const btn = Array.from(document.querySelectorAll('button')).find(b => {
            const t = b.innerText.trim().toLowerCase();
            return t === 'set aside' || t === 'approve';
        });
        return {
            activeKeys: activeKeys,
            btnText: btn ? btn.innerText.trim() : null
        };
        """)

        active_keys = set(str(k) for k in dom_state.get("activeKeys", []))
        target_keys = set(str(k) for k in target.get("criteria", {}).keys())

        if active_keys != target_keys:
            errors.append(f"Criteria mismatch: expected {sorted(target_keys)}, got {sorted(active_keys)}")

        # Verify Set Aside
        target_sa = target.get("set_aside", False)
        btn_text = dom_state.get("btnText")
        if btn_text:
            btn_lower = btn_text.lower()
            if target_sa and "approve" not in btn_lower:
                errors.append(f"Set Aside should be ON (button 'Approve'), but button is '{btn_text}'")
            elif not target_sa and "set aside" not in btn_lower:
                errors.append(f"Set Aside should be OFF (button 'Set aside'), but button is '{btn_text}'")
        else:
            errors.append("Set Aside / Approve button not found in DOM")

    except Exception as e:
        errors.append(f"Verification DOM error: {e}")

    # Verify remarks (only if target explicitly specified non-empty remarks)
    try:
        target_remarks = target.get("remarks", "")
        if target_remarks and str(target_remarks).strip():
            textarea = driver.find_element(By.CSS_SELECTOR, "textarea.remarks, textarea[placeholder*='remark' i], textarea[name*='remark' i]")
            if not textarea:
                textareas = driver.find_elements(By.TAG_NAME, "textarea")
                if textareas:
                    textarea = textareas[0]
            if textarea:
                current_remarks = textarea.get_attribute("value") or ""
                if current_remarks.strip() != str(target_remarks).strip():
                    errors.append(f"Remarks mismatch: expected '{target_remarks[:50]}', got '{current_remarks[:50]}'")
    except Exception as e:
        errors.append(f"Verification remarks error: {e}")

    return len(errors) == 0, errors


def upload_grades(
    config: Dict[str, Any],
    rubric_mapping: Dict[str, Any],
    students: List[Dict[str, Any]],
    progress_path: Path,
    exceptions_path: Path,
    dry_run: bool = False,
    filter_student: Optional[str] = None,
    filter_problem: Optional[str] = None,
    resume: bool = False,
    auto_continue: bool = True
):
    """Main upload loop."""
    base_url = config["zesje_base_url"]
    exam_id = config["exam_id"]
    problem_mapping = config["problem_mapping"]
    total_students = config.get("total_students", 1000)

    uploaded = load_progress(progress_path) if resume else set()
    exceptions = load_exceptions(exceptions_path)

    # Filter students
    if filter_student:
        students = [s for s in students if s["student_id"] == filter_student]
    if filter_problem:
        # Problem filter applies during iteration
        pass

    print("=" * 70)
    print("ZESJE DIFFERENTIAL UPLOADER")
    print("=" * 70)
    print(f"Course: {config.get('course_name')}")
    print(f"Exam ID: {exam_id}")
    print(f"Problems: {list(problem_mapping.values())}")
    print(f"Students to process: {len(students)}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    if filter_student: print(f"Filter Student: {filter_student}")
    if filter_problem: print(f"Filter Problem: {filter_problem}")
    print("=" * 70)

    driver = None
    cookies = {}
    student_to_sub = {}

    if not dry_run:
        print("\nStarting Firefox...")
        driver = setup_driver(config)
        driver.get(base_url)
        time.sleep(3)
        cookies = extract_cookies_from_driver(driver)
        test_exams, _ = api_prepull(base_url, exam_id, cookies) if cookies else (None, None)
        if not test_exams:
            input("\n[LOGIN REQUIRED] Log in to Zesje in the browser window, then press ENTER to continue...")
            cookies = extract_cookies_from_driver(driver)
        print(f"Session cookies: {len(cookies)} cookies")
    else:
        # In dry run, try to read cookies from profile database to fetch real live API state
        profile_path = config.get("firefox_profile_path")
        host = urlparse(base_url).netloc
        cookies = extract_cookies_from_profile(profile_path, host=host)
        if cookies:
            print(f"Loaded {len(cookies)} session cookies from Firefox profile SQLite")

    # API Pre-pull
    if cookies:
        print("\nPre-pulling live state from API...")
        exams_data, export_data = api_prepull(base_url, exam_id, cookies)
        if exams_data:
            print("  Parsing live exams JSON...")
            live_state, student_to_sub = parse_live_exams_json(exams_data, rubric_mapping)
            print(f"  Loaded {len(live_state)} ground-truth student/problem states from API")
        elif export_data:
            print("  Parsing live XLSX export...")
            live_state = parse_live_xlsx(export_data, problem_mapping)
            print(f"  Loaded {len(live_state)} student/problem states from XLSX")
        else:
            print("  [WARN] No live export data, will rely on DOM state")
            live_state = {}
    else:
        live_state = {}

    # Build target lookup (supports both per_problem_targets.json and single-problem XLSX)
    target_lookup = {}
    for student in students:
        if "problem_id" in student:
            prob_id = str(student["problem_id"])
            if filter_problem and prob_id != filter_problem:
                continue
            key = f"{student['student_id']}:{prob_id}"
            target_lookup[key] = {
                **student,
                "problem_id": prob_id,
                "problem_name": problem_mapping.get(prob_id, student.get("case_id", prob_id)),
            }
        else:
            for prob_id, prob_name in problem_mapping.items():
                key = f"{student['student_id']}:{prob_id}"
                if filter_problem and prob_id != filter_problem:
                    continue
                target_lookup[key] = {
                    **student,
                    "problem_id": prob_id,
                    "problem_name": prob_name
                }

    total_tasks = len(target_lookup)
    remaining = [k for k in target_lookup if k not in uploaded]
    print(f"\nTotal tasks: {total_tasks}, Already uploaded: {len(uploaded)}, Remaining: {len(remaining)}")

    if not remaining:
        print("\nAll tasks already uploaded!")
        if driver:
            driver.quit()
        return

    count = 0
    try:
        for key in sorted(remaining):
            if key in uploaded:
                continue
            count += 1

            target = target_lookup[key]
            student_id = target["student_id"]
            prob_id = target["problem_id"]
            prob_name = target["problem_name"]

            progress_key = f"{student_id}:{prob_id}"

            print(f"\n[{count}/{len(remaining)}] Student {student_id} - {prob_name} (Problem {prob_id})")

            # Get current state from live pull
            current = live_state.get(progress_key, {
                "student_id": student_id,
                "problem_id": prob_id,
                "criteria": {},
                "remarks": "",
                "set_aside": False,
                "grading_status": "UNKNOWN"
            })

            # Get rubric for this problem
            rubric = get_rubric_for_problem(rubric_mapping, prob_id)

            # Compute delta
            delta = compute_delta(target, current, rubric)

            print(f"  Target criteria: {sorted(target.get('criteria', {}).keys())}")
            print(f"  Current criteria: {sorted(current.get('criteria', {}).keys())}")
            print(f"  Delta ON: {delta['criteria_on']}, OFF: {delta['criteria_off']}")
            if delta["remarks"] is not None:
                print(f"  Remarks: '{delta['remarks'][:50]}...'")
            if delta["set_aside"] is not None:
                print(f"  Set Aside: {delta['set_aside']}")

            has_changes = any([
                delta["criteria_on"],
                delta["criteria_off"],
                delta["remarks"] is not None,
                delta["set_aside"] is not None
            ])

            if not has_changes:
                print("  [SKIP] No changes needed")
                if not dry_run:
                    save_progress(progress_path, progress_key)
                uploaded.add(progress_key)
                continue

            if dry_run:
                print("  [DRY RUN] Would execute delta")
                uploaded.add(progress_key)
                continue

            # Navigate to grading page
            sub_id = student_to_sub.get(student_id, student_id)
            url = f"{base_url}/exams/{exam_id}/grade/{sub_id}/{prob_id}"
            print(f"  Navigating to {url} (Submission {sub_id})")
            driver.get(url)
            time.sleep(1.5)

            # Wait for page load
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "img")))
            except:
                print("  [WARN] Page may not have fully loaded")

            # Execute delta
            success, exec_errors = execute_delta(driver, delta, rubric, target=target)

            if exec_errors:
                for e in exec_errors:
                    print(f"  [ERROR] {e}")

            # Post-verification
            print("  Verifying...")
            verify_ok, verify_errors = verify_state(driver, target, rubric)

            if verify_errors:
                for e in verify_errors:
                    print(f"  [VERIFY FAIL] {e}")

            if success and verify_ok:
                print("  [OK] Uploaded and verified")
                save_progress(progress_path, progress_key)
                uploaded.add(progress_key)
            else:
                print("  [FAIL] Upload or verification failed")
                exception = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "student_id": student_id,
                    "submission_id": sub_id,
                    "problem_id": prob_id,
                    "progress_key": progress_key,
                    "target": target,
                    "current": current,
                    "delta": delta,
                    "exec_errors": exec_errors,
                    "verify_errors": verify_errors
                }
                exceptions.append(exception)
                save_exceptions(exceptions_path, exceptions)

                if not dry_run and not auto_continue:
                    cont = input("  Continue? [y/N]: ").strip().lower()
                    if cont != 'y':
                        print("\nStopped by user.")
                        break

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress saved.")
    except Exception as e:
        print(f"\n\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()

    print("\n" + "=" * 70)
    print(f"Done. Uploaded this session: {count}")
    print(f"Total uploaded: {len(uploaded)}")
    print(f"Exceptions logged: {len(exceptions)}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Zesje Differential Uploader")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without browser")
    add_exam_argument(parser, include_config=True)
    parser.add_argument("--student", help="Process only this student ID")
    parser.add_argument("--problem", help="Process only this problem ID")
    parser.add_argument("--resume", action="store_true", help="Resume from progress file")
    parser.add_argument("--interactive", action="store_true", help="Pause and prompt on error")
    args = parser.parse_args()

    config = load_exam_config_from_args(args)
    rubric_path, populated_path, progress_path, exceptions_path = get_course_paths(config)

    try:
        rubric_mapping = load_rubric_mapping(rubric_path)
        per_prob_path = populated_path.parent / "per_problem_targets.json"
        if per_prob_path.exists():
            students = list(json.loads(per_prob_path.read_text(encoding="utf-8")).values())
            print(f"[INFO] Loaded {len(students)} per-problem targets from {per_prob_path}")
        else:
            students = load_populated_grades(populated_path)
    except Exception as e:
        print(f"[FATAL] Failed to load data: {e}")
        sys.exit(1)

    upload_grades(
        config=config,
        rubric_mapping=rubric_mapping,
        students=students,
        progress_path=progress_path,
        exceptions_path=exceptions_path,
        dry_run=args.dry_run,
        filter_student=args.student,
        filter_problem=args.problem,
        resume=args.resume,
        auto_continue=not args.interactive
    )


if __name__ == "__main__":
    main()
