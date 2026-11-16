#!/usr/bin/env python3
"""
Zesje Visual Audit Inspector - Non-Headless Interactive & Automated DOM Verification

Features:
- Launches visible, non-headless Firefox for live pair-inspection of student work.
- Extracts live DOM criteria, button state ('Approve' vs 'Set aside'), and remarks.
- Compares live DOM reading against target expectation (populated_grades.xlsx / JSON).
- Side-by-side terminal verification display.
- Modes:
    --interactive (default): Press Enter to advance, 'p' for prev, 's' to toggle Set Aside, 'q' to quit.
    --auto-step SECONDS: Automatically advances every N seconds for hands-free visual audit.
    --flagged-only: Inspects only students with Set Aside = True (e.g. the 38 upward adjustments).
    --modified-only: Inspects students with changes vs original baseline.
    --all: Inspects entire cohort.
    --student ID: Inspects a single student number.
- Generates a Markdown audit dossier in data/<exam>/visual_audit_report.md.
"""

import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from urllib.parse import urlparse
import sqlite3

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from openpyxl import load_workbook

SCRIPT_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))
from exam_config import add_exam_argument, load_exam_config_from_args


def get_course_paths(config: Dict[str, Any]) -> Tuple[Path, Path, Path, Path]:
    base = Path(config["exam_dir"])
    rubric_path = base / "rubric_mapping.json"
    populated_path = base / "populated" / "populated_grades.xlsx"
    staged_json_path = base / "q8_zesje_staged_payload.json"
    report_path = base / "visual_audit_report.md"

    return rubric_path, populated_path, staged_json_path, report_path


def load_rubric_mapping(rubric_path: Path) -> Dict[str, Any]:
    if not rubric_path.exists():
        return {}
    with open(rubric_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_populated_grades(populated_path: Path) -> List[Dict[str, Any]]:
    if not populated_path.exists():
        raise FileNotFoundError(f"Populated grades not found: {populated_path}")

    wb = load_workbook(populated_path, data_only=True)
    ws = wb.active

    student_id_col = 1
    set_aside_col = 2
    status_col = 3
    remarks_col = 11

    # Criteria columns: 4 (key 1) to 10 (key 7)
    criteria_map = {4: "1", 5: "2", 6: "3", 7: "4", 8: "5", 9: "6", 10: "7"}

    students = []
    for row in range(4, ws.max_row + 1):
        cell_id = ws.cell(row=row, column=student_id_col).value
        if not cell_id or str(cell_id).strip() in ("", "None"):
            continue
        sid = str(cell_id).strip()

        sa_val = ws.cell(row=row, column=set_aside_col).value
        sa = bool(sa_val) if isinstance(sa_val, bool) else (str(sa_val).strip().upper() == "TRUE")

        status = str(ws.cell(row=row, column=status_col).value or "").strip().upper()

        crit = {}
        for col_idx, key in criteria_map.items():
            val = ws.cell(row=row, column=col_idx).value
            if val is not None and str(val).strip() in ("1", "1.0", 1, True):
                crit[key] = 1

        rem_val = ws.cell(row=row, column=remarks_col).value or ""
        rem = str(rem_val).strip()

        score_val = ws.cell(row=row, column=12).value if ws.max_column >= 12 else None
        try:
            score = float(score_val) if score_val is not None else compute_live_score(list(crit.keys()), {})
        except:
            score = compute_live_score(list(crit.keys()), {})

        students.append({
            "student_id": sid,
            "set_aside": sa,
            "grading_status": status,
            "criteria": crit,
            "remarks": rem,
            "target_score": score
        })

    return students


def extract_cookies(profile_path: str, host: str = "zesje.tudelft.nl") -> Dict[str, str]:
    db = Path(profile_path) / "cookies.sqlite"
    if not db.exists():
        return {}
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT name, value FROM moz_cookies WHERE host LIKE ?", (f"%{host}%",))
    cookies = {name: val for name, val in cur.fetchall()}
    conn.close()
    return cookies


def fetch_student_to_sub(base_url: str, exam_id: int, cookies: Dict[str, str]) -> Dict[str, int]:
    import urllib.request
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers = {"Cookie": cookie_str}
    url = f"{base_url}/api/exams/{exam_id}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        mapping = {}
        for sub in data.get("submissions", []):
            sub_id = sub["id"]
            stud = sub.get("student")
            if stud and stud.get("id"):
                mapping[str(stud["id"])] = sub_id
            else:
                mapping[str(sub_id)] = sub_id
        return mapping
    except Exception as e:
        print(f"[WARN] Failed to fetch student mapping from API: {e}")
        return {}


def setup_visible_driver(config: Dict[str, Any], headless: bool = False) -> webdriver.Firefox:
    options = Options()
    binary = config.get("firefox_binary")
    if binary and Path(binary).exists():
        options.binary_location = binary

    profile_path = config.get("firefox_profile_path")
    if profile_path and Path(profile_path).exists():
        options.set_preference("profile", profile_path)
        options.add_argument("-profile")
        options.add_argument(profile_path)

    if headless:
        options.add_argument("--headless")

    driver = webdriver.Firefox(options=options)
    if not headless:
        driver.maximize_window()
    return driver


def read_dom_state(driver: webdriver.Firefox) -> Dict[str, Any]:
    """Read the active grading state directly from the visible DOM."""
    return driver.execute_script("""
    const items = Array.from(document.querySelectorAll('.panel-block.feedback-item, a.feedback-item'));
    const activeCriteria = [];
    const allOptions = [];

    items.forEach(item => {
        const tag = item.querySelector('.tag.is-score');
        const key = tag ? tag.getAttribute('data-tooltip') : null;
        const score = tag ? tag.innerText.trim() : null;
        const isActive = tag ? tag.classList.contains('is-link') : false;
        const text = item.innerText.replace(/\\n/g, ' ').trim();

        allOptions.push({ key: key, score: score, active: isActive, text: text });
        if (isActive && key) {
            activeCriteria.push({ key: key, score: score, text: text });
        }
    });

    const btn = Array.from(document.querySelectorAll('button')).find(b => {
        const t = b.innerText.trim().toLowerCase();
        return t === 'set aside' || t === 'approve';
    });

    const textarea = document.querySelector("textarea.remarks, textarea[placeholder*='remark' i], textarea[name*='remark' i], textarea");
    const remarks = textarea ? textarea.value : "";

    return {
        url: window.location.href,
        buttonText: btn ? btn.innerText.trim() : null,
        isSetAside: btn ? (btn.innerText.trim().toLowerCase() === 'approve') : false,
        activeCriteria: activeCriteria,
        activeKeys: activeCriteria.map(c => c.key),
        allOptions: allOptions,
        remarks: remarks
    };
    """)


def compute_live_score(active_keys: List[str], rubric: Dict[str, Any]) -> float:
    if "1" in active_keys:
        return 5.0
    if "7" in active_keys:
        return 0.0
    # TN22010 Q8 default criteria score mapping: keys 2..6 are 1 pt each
    score = 0.0
    for k in active_keys:
        if k in ("2", "3", "4", "5", "6"):
            score += 1.0
    return score


def inspect_cohort(
    config: Dict[str, Any],
    students: List[Dict[str, Any]],
    student_to_sub: Dict[str, int],
    rubric: Dict[str, Any],
    report_path: Path,
    mode: str = "interactive",
    auto_step_sec: float = 3.0,
    filter_mode: str = "flagged",
    headless: bool = False
):
    base_url = config["zesje_base_url"]
    exam_id = config["exam_id"]
    problem_id = list(config["problem_mapping"].keys())[0] if config.get("problem_mapping") else "9"
    prob_name = config.get("problem_mapping", {}).get(problem_id, f"Problem {problem_id}")

    # Filtering students
    if filter_mode == "flagged":
        target_students = [s for s in students if s["set_aside"]]
        mode_desc = f"FLAGGED STUDENTS ONLY (Set Aside = TRUE: {len(target_students)} students)"
    elif filter_mode == "modified":
        target_students = [s for s in students if s["grading_status"] in ("RELAXATION_APPLIED", "OPTIONS_REFINED") or s["set_aside"]]
        mode_desc = f"ALL MODIFIED STUDENTS ({len(target_students)} students)"
    else:
        target_students = students
        mode_desc = f"FULL COHORT ({len(target_students)} students)"

    print("=" * 80)
    print("  ZESJE LIVE DOM VISUAL AUDIT & INSPECTOR")
    print("=" * 80)
    print(f"Target URL:    {base_url}/exams/{exam_id}")
    print(f"Problem:       {prob_name} (ID: {problem_id})")
    print(f"Inspection:    {mode_desc}")
    print(f"Pacing:        {'INTERACTIVE (Press Enter per student)' if mode == 'interactive' else f'AUTOMATIC ({auto_step_sec}s step-pause)'}")
    print("=" * 80)
    print("\nStarting visible Firefox browser on your desktop..." if not headless else "\nStarting headless Firefox browser...")

    driver = setup_visible_driver(config, headless=headless)

    report_entries = []
    idx = 0
    total = len(target_students)

    try:
        while idx < total:
            target = target_students[idx]
            sid = target["student_id"]
            sub_id = student_to_sub.get(sid, sid)

            url = f"{base_url}/exams/{exam_id}/grade/{sub_id}/{problem_id}"
            driver.get(url)

            # Wait for feedback items to appear
            try:
                WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".panel-block.feedback-item, a.feedback-item"))
                )
            except:
                time.sleep(1.5)

            # Extra settle time for image canvas / SVG
            time.sleep(0.5)

            dom = read_dom_state(driver)

            # Verification comparisons
            target_keys = sorted(target["criteria"].keys())
            live_keys = sorted(dom["activeKeys"])
            crit_match = (target_keys == live_keys)

            target_sa = target["set_aside"]
            live_sa = dom["isSetAside"]
            sa_match = (target_sa == live_sa)

            target_score = target["target_score"]
            live_score = compute_live_score(live_keys, rubric)
            score_match = (abs(target_score - live_score) < 1e-4)

            overall_match = crit_match and sa_match and score_match

            # Terminal Display
            print("\n" + "=" * 80)
            status_tag = "[MATCH: 100% OK]" if overall_match else "[MISMATCH / DISCREPANCY DETECTED]"
            print(f"[{idx + 1}/{total}] Student: {sid} | Submission: {sub_id} | {prob_name} -> {status_tag}")
            print(f"URL: {url}")
            print("-" * 80)

            print(f"  TARGET EXPECTATION:")
            print(f"    - Criteria:   {target_keys} (Score: {target_score:.1f} / 5.0)")
            print(f"    - Set Aside:  {'TRUE [FLAGGED for teacher inspection]' if target_sa else 'FALSE [APPROVED]'}")
            if target.get("remarks"):
                print(f"    - Remarks:    \"{target['remarks'][:60]}...\"")

            print(f"  LIVE DOM READING:")
            print(f"    - Criteria:   {live_keys} (Score: {live_score:.1f} / 5.0)")
            for item in dom["activeCriteria"]:
                print(f"        * Key {item['key']}: {item['text'][:65]}")
            button_label = dom["buttonText"] or "NOT FOUND"
            print(f"    - Button DOM: '{button_label}' -> {'FLAGGED (Set Aside is ON)' if live_sa else 'APPROVED (Set Aside is OFF)'}")
            if dom.get("remarks"):
                print(f"    - Remarks:    \"{dom['remarks'][:60]}...\"")

            print("-" * 80)
            print(f"  VERIFICATION AUDIT:")
            print(f"    - Criteria Match:   {'[OK]' if crit_match else '[FAIL - Mismatch]'}")
            print(f"    - Set Aside Match:  {'[OK]' if sa_match else f'[FAIL - Target={target_sa}, DOM={live_sa}]'}")
            print(f"    - Score Match:      {'[OK]' if score_match else f'[FAIL - Target={target_score}, Live={live_score}]'}")
            print("=" * 80)

            # Record entry
            report_entries.append({
                "student_id": sid,
                "submission_id": sub_id,
                "target_keys": target_keys,
                "live_keys": live_keys,
                "target_sa": target_sa,
                "live_sa": live_sa,
                "target_score": target_score,
                "live_score": live_score,
                "match": overall_match
            })

            # User navigation / pacing
            if mode == "interactive":
                prompt = "  [Enter: Next | 'p': Prev | 's': Toggle Set Aside | 'r': Re-read | 'q': Quit]: "
                choice = input(prompt).strip().lower()
                if choice == "q":
                    print("\nInspection stopped by user.")
                    break
                elif choice == "p":
                    idx = max(0, idx - 1)
                    continue
                elif choice == "r":
                    continue
                elif choice == "s":
                    # Manually toggle Set aside in live browser
                    driver.execute_script("""
                    const btn = Array.from(document.querySelectorAll('button')).find(b => {
                        const t = b.innerText.trim().toLowerCase();
                        return t === 'set aside' || t === 'approve';
                    });
                    if (btn && !btn.disabled) btn.click();
                    """)
                    time.sleep(0.5)
                    continue
                else:
                    idx += 1
            else:
                # Automatic step pacing
                time.sleep(auto_step_sec)
                idx += 1

    except KeyboardInterrupt:
        print("\n\nAudit interrupted by user. Generating report up to current student...")
    finally:
        driver.quit()

    # Generate Markdown Report
    passed = sum(1 for e in report_entries if e["match"])
    total_inspected = len(report_entries)
    mismatches = [e for e in report_entries if not e["match"]]

    report_content = f"""# Visual Audit Inspection Report

- **Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}
- **Course / Problem:** {config.get('course_name', 'tn22010')} - {prob_name} (Problem {problem_id})
- **Total Inspected:** {total_inspected}
- **Perfect Matches:** {passed} / {total_inspected} ({100.0 * passed / max(1, total_inspected):.1f}%)
- **Mismatches:** {len(mismatches)}

## Summary Table

| Student ID | Sub ID | Target Criteria | Live DOM Criteria | Target SA | Live SA | Score | Status |
| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :--- |
"""
    for e in report_entries:
        status_md = "✅ MATCH" if e["match"] else "❌ MISMATCH"
        report_content += f"| `{e['student_id']}` | {e['submission_id']} | `{e['target_keys']}` | `{e['live_keys']}` | {e['target_sa']} | {e['live_sa']} | {e['live_score']:.1f} | {status_md} |\n"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print("\n" + "=" * 80)
    print("AUDIT COMPLETE")
    print(f"Inspected: {total_inspected} | Matches: {passed} / {total_inspected} | Discrepancies: {len(mismatches)}")
    print(f"Report saved to: {report_path}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Zesje Live DOM Visual Audit Inspector")
    add_exam_argument(parser, include_config=True)
    parser.add_argument("--auto-step", type=float, default=None, help="Auto-step through submissions with pause in seconds (e.g. 3.0)")
    parser.add_argument("--flagged-only", action="store_true", help="Inspect only Set Aside = True students (default)")
    parser.add_argument("--modified-only", action="store_true", help="Inspect all students with grade or option modifications")
    parser.add_argument("--all", action="store_true", help="Inspect entire cohort")
    parser.add_argument("--student", help="Inspect single student number")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (useful for fast verification)")
    args = parser.parse_args()

    config = load_exam_config_from_args(args)
    rubric_path, populated_path, staged_json_path, report_path = get_course_paths(config)

    students = load_populated_grades(populated_path)
    rubric = load_rubric_mapping(rubric_path)

    if args.student:
        students = [s for s in students if s["student_id"] == args.student]

    # Fetch live student-to-submission mapping using SQLite cookies
    base_url = config["zesje_base_url"]
    exam_id = config["exam_id"]
    profile_path = config.get("firefox_profile_path", "")
    host = urlparse(base_url).netloc
    cookies = extract_cookies(profile_path, host)
    student_to_sub = fetch_student_to_sub(base_url, exam_id, cookies)

    filter_mode = "all" if args.all else ("modified" if args.modified_only else "flagged")
    pacing_mode = "auto" if args.auto_step is not None else "interactive"
    auto_sec = args.auto_step if args.auto_step is not None else 3.0

    inspect_cohort(
        config=config,
        students=students,
        student_to_sub=student_to_sub,
        rubric=rubric,
        report_path=report_path,
        mode=pacing_mode,
        auto_step_sec=auto_sec,
        filter_mode=filter_mode,
        headless=args.headless
    )


if __name__ == "__main__":
    main()
