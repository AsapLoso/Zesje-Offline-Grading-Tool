import os
import json
import sys
import time

# --- PATH RESOLUTION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
CONFIG_PATH = os.path.join(REPO_ROOT, "config.json")
OUTPUT_PATH = os.path.join(REPO_ROOT, "rubric_mapping.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    print(f"[Error] config.json not found at {CONFIG_PATH}")
    sys.exit(1)

def extract_rubric():
    config = load_config()
    from selenium import webdriver
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.common.by import By

    options = Options()
    if os.path.exists(config.get("firefox_binary", "")):
        options.binary_location = config["firefox_binary"]
    options.accept_insecure_certs = True
    if config.get("firefox_profile_path") and os.path.exists(config["firefox_profile_path"]):
        options.add_argument("-profile")
        options.add_argument(config["firefox_profile_path"])

    service = Service(executable_path=config.get("geckodriver_path", "geckodriver.exe"))
    driver = webdriver.Firefox(service=service, options=options)

    rubric_result = {}
    try:
        base_url = config.get("zesje_base_url")
        exam_id = config.get("exam_id")
        problem_mapping = config.get("problem_mapping", {})

        print("=" * 65)
        print("   ZESJE RUBRIC & KEYSTROKE AUTO-EXTRACTOR")
        print("=" * 65)
        print(f"Target: {base_url}/exams/{exam_id}")
        print("Navigating to first grading page to inspect rubric layout...")

        driver.get(f"{base_url}/exams/{exam_id}")
        time.sleep(2)

        for prob_id, prob_name in problem_mapping.items():
            url = f"{base_url}/exams/{exam_id}/grade/1/{prob_id}"
            print(f"\nScanning Problem '{prob_name}' (Problem ID {prob_id}) -> {url}")
            driver.get(url)
            time.sleep(2)

            # Extract feedback options from DOM
            script = """
            const items = [];
            // Query all feedback option elements
            const elements = Array.from(document.querySelectorAll('.feedback-item, [data-feedback-id], input[type="checkbox"]'));
            elements.forEach((el, index) => {
                const label = el.closest('label') || el.parentElement;
                const text = label ? label.innerText.trim() : (el.innerText || '');
                const id = el.getAttribute('data-feedback-id') || el.value || el.id || String(index + 1);
                const stroke = String(index + 1);
                if (text && !items.some(x => x.id === id)) {
                    items.push({
                        keystroke: stroke,
                        feedback_id: id,
                        text: text
                    });
                }
            });
            return items;
            """
            items = driver.execute_script(script)
            rubric_result[prob_name] = {
                "problem_id": prob_id,
                "all_correct_keystroke": "1", # Default placeholder; user reviews and adjusts
                "all_incorrect_keystroke": str(len(items)) if items else "0",
                "options": items
            }
            print(f"  Found {len(items)} feedback options for {prob_name}:")
            for it in items:
                print(f"    Key [{it['keystroke']}] -> {it['text'][:60]}")

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(rubric_result, f, indent=4)
        print("\n" + "=" * 65)
        print(f"[SUCCESS] Rubric extracted and saved to: {OUTPUT_PATH}")
        print(">>> Stap 2: Open rubric_mapping.json en geef per vraag aan")
        print("           welke keystroke 'all_correct' en 'all_incorrect' is!")
        print("=" * 65)

    finally:
        driver.quit()

if __name__ == "__main__":
    extract_rubric()
