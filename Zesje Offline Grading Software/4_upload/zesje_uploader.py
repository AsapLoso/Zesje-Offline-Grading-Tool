"""Per-exam Zesje grade uploader supporting zesje_upload_ready.csv + rubric_mapping.json."""
import csv
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from exam_config import select_exam_config

SLEEP_AFTER_NAV = 1.0
SLEEP_BETWEEN_KEYS = 0.2


def load_rubric_mapping(data_dir):
    """Load rubric_mapping.json from exam data_dir or repo root."""
    for base in (data_dir, REPO_ROOT):
        p = os.path.join(base, "rubric_mapping.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def find_upload_csv(data_dir):
    """Locate zesje_upload_ready.csv in data_dir or repo root."""
    for base in (data_dir, REPO_ROOT):
        p = os.path.join(base, "zesje_upload_ready.csv")
        if os.path.exists(p):
            return p
    return None


def resolve_keys_for_options(option_ids, prob_rubric):
    """Map Zesje option IDs (or labels) to Zesje keyboard shortcuts from rubric_mapping.json."""
    if not prob_rubric:
        return [(opt, opt) for opt in option_ids]
    options = prob_rubric.get("options") if isinstance(prob_rubric, dict) else prob_rubric
    keys = []
    if isinstance(options, dict):
        for oid in option_ids:
            if oid in options:
                entry = options[oid]
                k = entry.get("key") if isinstance(entry, dict) else str(entry)
                keys.append((str(k), oid))
            else:
                keys.append((oid, oid))
    elif isinstance(options, list):
        by_id = {str(o.get("id")): str(o.get("key")) for o in options if isinstance(o, dict) and o.get("id") is not None}
        for oid in option_ids:
            keys.append((by_id.get(oid, oid), oid))
    return keys


def setup_driver(config):
    """Initialize Firefox WebDriver using config.json settings."""
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service

    options = Options()
    if config.get("firefox_binary") and os.path.exists(config["firefox_binary"]):
        options.binary_location = config["firefox_binary"]
    options.accept_insecure_certs = True
    if config.get("firefox_profile_path") and os.path.exists(config["firefox_profile_path"]):
        options.add_argument("-profile")
        options.add_argument(config["firefox_profile_path"])
    options.set_preference("network.proxy.type", 0)
    service = Service(executable_path=config.get("geckodriver_path", "geckodriver.exe"))
    return webdriver.Firefox(service=service, options=options)


def load_progress(path):
    """Return set of already-uploaded keys."""
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_progress(path, key):
    """Append an uploaded key to upload_progress.txt."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(key + "\n")


def page_already_has_selection(driver):
    """Return True if Zesje already shows a checked/active rubric item (no-overwrite guard)."""
    from selenium.webdriver.common.by import By

    checked = driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']:checked, input[type='radio']:checked, .option.selected, .rubric-option.active")
    return len(checked) > 0


def upload_grades(dry_run_flag=False):
    """Interactive per-exam uploader supporting dry-run and non-overwrite upload."""
    config, data_dir = select_exam_config(REPO_ROOT)
    os.makedirs(data_dir, exist_ok=True)
    csv_path = find_upload_csv(data_dir)
    if not csv_path:
        print(f"[Error] zesje_upload_ready.csv not found in {data_dir} or {REPO_ROOT}")
        return

    rubric_map = load_rubric_mapping(data_dir)
    progress_file = os.path.join(data_dir, "upload_progress.txt")
    uploaded = load_progress(progress_file)

    exam_filter = config.get("pipeline_exam_name") or f"exam_{config.get('exam_id')}"
    with open(csv_path, "r", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    exam_rows = [r for r in all_rows if r.get("exam") == exam_filter]
    if not exam_rows:
        available = sorted({r.get("exam", "") for r in all_rows if r.get("exam")})
        print(f"No rows matched '{exam_filter}' in {csv_path}. Available exams: {available}")
        pick = input(f"Enter exam name to upload [{available[0]}]: ").strip() or available[0]
        exam_rows = [r for r in all_rows if r.get("exam") == pick]

    ready_rows = [r for r in exam_rows if r.get("needs_human_review", "NO") != "YES"]
    held_rows = [r for r in exam_rows if r.get("needs_human_review", "NO") == "YES"]
    todo = [r for r in ready_rows if f"{r['problem_id']}:{r['submission_id']}" not in uploaded]

    print("-" * 65)
    print("  ZESJE PER-EXAM GRADE UPLOADER")
    print("-" * 65)
    print(f"  Data dir:      {data_dir}")
    print(f"  CSV:           {csv_path}")
    print(f"  Total / Ready: {len(exam_rows)} / {len(ready_rows)} (held for manual: {len(held_rows)})")
    print(f"  Remaining:     {len(todo)}")
    print("-" * 65)
    for h in held_rows:
        print(f"  [HELD] {h['case_id']} ({h.get('review_reasons', '')})")

    if dry_run_flag:
        mode = "1"
    else:
        print("\nSelect mode:")
        print("  1. Dry-run (preview keys only, no browser)")
        print("  2. Upload without overwriting existing grades (Recommended)")
        mode = input("Choice [1/2, Enter=2]: ").strip() or "2"

    dry_run = mode == "1"
    if not todo:
        print("\nNothing remaining to upload.")
        return

    driver = None
    try:
        if not dry_run:
            from selenium.webdriver.common.by import By

            driver = setup_driver(config)
            driver.get(config.get("zesje_base_url", "https://zesje.tudelft.nl"))
            input("\nLog in to Zesje in Firefox, then press ENTER to start non-overwrite upload (Ctrl+C to abort)...")

        for idx, row in enumerate(todo, 1):
            pid = str(row["problem_id"])
            sid = str(row["submission_id"])
            key = f"{pid}:{sid}"
            opt_ids = [o for o in row.get("adopted_option_ids", "").split() if o]
            keys = resolve_keys_for_options(opt_ids, rubric_map.get(pid))
            print(f"[{idx}/{len(todo)}] {row['case_id']} (prob={pid}, sub={sid}) -> opts={opt_ids} keys={keys}")

            if dry_run:
                continue

            url = f"{config['zesje_base_url']}/exams/{config['exam_id']}/grade/{sid}/{pid}"
            driver.get(url)
            time.sleep(SLEEP_AFTER_NAV)
            if page_already_has_selection(driver):
                print(f"  [SKIP] Existing grade detected on page — not overwriting.")
                save_progress(progress_file, key)
                continue

            body = driver.find_element(By.TAG_NAME, "body")
            for k, lbl in keys:
                body.send_keys(k)
                print(f"  [OK] Pressed '{k}' ({lbl})")
                time.sleep(SLEEP_BETWEEN_KEYS)
            save_progress(progress_file, key)
        print("\nDONE.")
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    upload_grades(dry_run_flag="--dry-run" in sys.argv)
