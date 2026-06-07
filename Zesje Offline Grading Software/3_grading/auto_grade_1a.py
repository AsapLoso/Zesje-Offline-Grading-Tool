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

import glob
import time
import google.generativeai as genai
from PIL import Image
import re
import csv

if "GEMINI_API_KEY" in os.environ:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
else:
    print("WARNING: GEMINI_API_KEY not found in environment.")

model = genai.GenerativeModel('gemini-1.5-pro')

PROMPT = """You are an expert university physics grader evaluating an exam.
Look closely at this student's handwritten answer for an electrical circuits problem.

Determine whether the student has correctly derived or written down this exact differential equation (or a mathematically equivalent form):

dI/dt = -(R/L)*I + V_0(t)/L

Alternative acceptable form:
V_0(t) = I(t)*R + L*(dI/dt)

Notes for grading:
- They might use lowercase 'i' instead of 'I'.
- They might drop the '(t)' which is perfectly acceptable.
- Look for mathematically equivalent rearrangements.
- If they have this correct equation ANYWHERE in the image, give them 1 point.
- If it is completely missing, fundamentally incorrect, or incomplete, give 0 points.

You MUST respond with a valid JSON object matching this schema exactly, and nothing else:
{
    "score": 1,
    "reason": "Brief explanation of what you found"
}
"""

def grade_1a():
    image_dir = os.path.join(DATA_DIR, "zesje_images", "1a")
    if not os.path.exists(image_dir):
        print(f"Directory '{image_dir}' not found. Have you scraped 1a yet?")
        return

    image_paths = glob.glob(os.path.join(image_dir, "*.[jp][pn]*"))
    if not image_paths:
        print(f"No images found in {image_dir}.")
        return

    csv_file = os.path.join(DATA_DIR, "auto_grades_1a.csv")
    
    graded_files = set()
    if os.path.exists(csv_file):
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row: graded_files.add(row[0])

    print(f"Found {len(image_paths)} submissions to grade.")
    
    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not graded_files:
            writer.writerow(['Filename', 'Submission', 'Score', 'Reason'])

        for img_path in sorted(image_paths):
            filename = os.path.basename(img_path)
            if filename in graded_files:
                continue
                
            sub_match = re.search(r'sub_(\d+)', filename, re.IGNORECASE)
            submission = sub_match.group(1) if sub_match else filename
            
            print(f"\n[AI Grader] Analyzing Submission {submission}...")
            
            try:
                img = Image.open(img_path)
                response = model.generate_content([PROMPT, img])
                
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text[7:-3].strip()
                elif text.startswith("```"):
                    text = text[3:-3].strip()
                    
                result = json.loads(text)
                score = result.get('score', 0)
                reason = result.get('reason', 'No reason provided')
                
                writer.writerow([filename, submission, score, reason])
                f.flush()
                
                color = "\033[92m" if score == 1 else "\033[91m"
                reset = "\033[0m"
                print(f"  -> Score: {color}{score}{reset}/1. Reason: {reason}")
                
            except Exception as e:
                print(f"  -> Error processing {filename}: {e}")
                
            time.sleep(3)

if __name__ == "__main__":
    grade_1a()
