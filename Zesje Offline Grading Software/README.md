# Zesje Exam Grading Automation (Restructured)

Selenium-based automation toolkit for grading 121 student exam submissions on TU Delft's Zesje platform. This toolkit scrapes student submissions for offline use, provides a custom touch-friendly offline grading browser interface, leverages Gemini 1.5 Pro for AI-assisted math grading, and uploads the final grades back to Zesje with progress tracking.

The project is structured into **four sequential steps** to separate concerns and maintain a clean repository.

---

## 📋 Directory Structure

```
Zesje Offline Grading Software/
├── config.json                 # Centralized configuration (URLs, Firefox profile, settings)
├── requirements.txt            # Python dependencies
├── README.md                   # Project documentation
├── README.html                 # Styled HTML version of documentation
├── 1_scrape/                   # STEP 1: Scraping tools
│   ├── zesje_scraper.py        # Selenium scraper (takes Zesje links and downloads submissions)
│   └── dump_page.py            # Developer helper to dump DOM grading page HTML
├── 2_processing/               # STEP 2: Data processing & preparation
│   ├── merge_images.py         # Merges multi-page answers (1b and 1b_ext)
│   ├── finalize_exports.py     # Copies and renames files to standardized structure
│   └── build_database.py       # Merges raw grading CSVs into clean grade_database.csv
├── 3_grading/                  # STEP 3: Offline grading clients
│   ├── grader.html             # Standalone touch-optimized browser grading interface
│   ├── auto_grade_1a.py        # Gemini 1.5 Pro AI automatic math equation grader
│   └── manual_grade_1a.py      # Terminal-based manual grading fallback
├── 4_upload/                   # STEP 4: Grading sync tools
│   └── zesje_uploader.py       # Selenium grade uploader (keyboard emulation)
└── data/                       # Shared storage for active exam records (gitignored)
    ├── zesje_images/           # Raw scraped PNG images per question
    ├── final_exports/          # Renamed and structured images ready for review/upload
    ├── rebuilt.zesje_pdfs/     # Optional original PDF booklets
    ├── zesje_grades.csv        # Raw output csv from manual/browser grading
    ├── auto_grades_1a.csv      # Raw output csv from Gemini AI grading
    ├── grade_database.csv      # Unified database of compiled final student grades
    └── upload_progress.txt     # Progress tracking log of uploaded student grades
```

---

## ⚙️ Setup & Configuration

1. **Install Dependencies**:
   Ensure you have Firefox and Geckodriver installed on your machine. Install the Python packages:
   ```bash
   pip install -r requirements.txt
   ```
2. **Central Configuration (`config.json`)**:
   Adjust paths and parameters in the root-level `config.json` before running scripts. All scripts dynamically load their configuration from this file:
   ```json
   {
       "zesje_base_url": "https://tn2211-2026.zesje.tudelft.nl",
       "exam_id": 3,
       "firefox_binary": "C:\\Program Files\\Mozilla Firefox\\firefox.exe",
       "firefox_profile_path": "C:\\Users\\Deuts\\AppData\\Roaming\\Mozilla\\Firefox\\Profiles\\39shiy81.default-release",
       "geckodriver_path": "C:\\Geckodriver.exe",
       "problem_mapping": {
           "1": "1a",
           "2": "1b",
           "3": "1b_ext"
       },
       "total_students": 121
   }
   ```

---

## 🚀 The 4-Step Workflow

### Step 1: Scrape Zesje (`1_scrape/`)
Iterates through submissions and downloads high-resolution screenshots of student work.
* **Run scraper**:
  ```bash
  python 1_scrape/zesje_scraper.py
  ```
  * *Interactive mode:* You will be prompted to confirm if you want to use the settings in `config.json` or input a new Zesje URL, problem mappings, and settings. New inputs are saved directly to `config.json`.
* **DOM analysis helper**:
  ```bash
  python 1_scrape/dump_page.py
  ```
  Dumps the raw HTML page and prints all button element tags/classes for locator updates if the Zesje interface changes.

### Step 2: Processing (`2_processing/`)
Stitches multi-page answers and builds databases.
1. **Merge Multi-Page Submissions**:
   ```bash
   python 2_processing/merge_images.py
   ```
   Combines `1b` and `1b_ext` images vertically into a single image inside `data/zesje_images/1b_combined/`.
2. **Rename & Finalize Exports**:
   ```bash
   python 2_processing/finalize_exports.py
   ```
   Organizes files into `data/final_exports/` in a clean `Copy_xxx.png` format.
3. **Build Grade Database**:
   ```bash
   python 2_processing/build_database.py
   ```
   Merges grades from `data/zesje_grades.csv` (browser/manual grading) and `data/auto_grades_1a.csv` (AI grading), giving manual overrides priority. Compiles the final table `data/grade_database.csv`.

### Step 3: Grading (`3_grading/`)
Facilitates manual and AI grading of scraped submissions.
* **HTML Browser Grader**:
  Open `3_grading/grader.html` in any web browser. Load the `data/zesje_images` folder to grade offline with touch-controls (pinch-to-zoom/pan). Export the results as `zesje_grades.csv` and move it to `data/`.
* **Gemini AI Math Grader**:
  ```bash
  python 3_grading/auto_grade_1a.py
  ```
  *Requires `GEMINI_API_KEY` in environment.* Multimodal OCR grading of equation equivalence, outputting to `data/auto_grades_1a.csv`.
* **Manual Terminal Grader**:
  ```bash
  python 3_grading/manual_grade_1a.py
  ```
  Terminal fast-grading utility with windows image popup.

### Step 4: Upload Software (`4_upload/`)
Uploads finalized grades back to Zesje.
* **Run synchronization**:
  ```bash
  python 4_upload/zesje_uploader.py
  ```
  Reads `data/grade_database.csv` and automates grading entries in Zesje via keyboard emulation. Keeps track of progress in `data/upload_progress.txt` so it is safely resumable.
