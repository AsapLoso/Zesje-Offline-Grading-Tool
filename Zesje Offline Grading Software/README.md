# Zesje Exam Grading Automation (Restructured)

Selenium-based automation toolkit for grading 121 student exam submissions on TU Delft's Zesje platform. This toolkit scrapes student submissions for offline use, provides a custom touch-friendly offline grading browser interface, leverages Gemini 1.5 Pro for AI-assisted math grading, and uploads the final grades back to Zesje with progress tracking.

The project is structured into **four sequential steps** to separate concerns and maintain a clean repository.

---

## 📋 Directory Structure

```
Zesje Offline Grading Software/
├── exam_config.py              # Shared exam selection and config loader
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
└── data/                       # Exam folders plus shared non-exam pipeline data
    ├── example1_demo_exam1/     # Fake example exam (tracked)
    ├── archive/                 # Archived exam folders
    ├── <exam-folder>/           # Real exam files and config.json (gitignored)
    ├── zesje_images/            # Raw scraped PNG images per question
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
2. **Choose an exam**:
   Each exam keeps its own `config.json` and grading files in `data/<exam-folder>/`. Pass `--exam <folder-name-or-number>` to select it. If omitted, a terminal picker lists configured active exams and offers archived exams. The uploader and visual audit inspector also accept `--config <path>` as an explicit config-file override.

---

## 🚀 The 4-Step Workflow

### Step 1: Scrape Zesje (`1_scrape/`)
Iterates through submissions and downloads high-resolution screenshots of student work.
* **Run scraper**:
  ```bash
  python 1_scrape/zesje_scraper.py --exam <folder-name-or-number>
  ```
  * *Interactive mode:* You will be prompted to use the selected exam settings or enter a new Zesje URL, problem mappings, and settings. New inputs are saved in that exam's folder.
* **Rubric & Sneltoetsen Auto-Extractor**:
  ```bash
  python 1_scrape/extract_rubric.py --exam <folder-name-or-number>
  ```
  * *Doel:* Bepaalt automatisch welke sneltoetsen (`1..N`) op welke rubric-items slaan. Zesje kent toetsen toe op volgorde van aanmaak — dus toets `1` kan bij opgave A "alles goed" zijn, maar bij opgave B juist "alles fout" (0 pt).
  * *Instellen:* Het script leest de geselecteerde examconfig, scraapt de opties en slaat `rubric_mapping.json` op in de examemap. Jij hoeft per vraag alleen in te vullen welke keystroke `all_correct` is en welke `all_incorrect`.
* **DOM analysis helper**:
  ```bash
  python 1_scrape/dump_page.py --exam <folder-name-or-number>
  ```
  Dumps the raw HTML page and prints all button element tags/classes for locator updates if the Zesje interface changes.

### ⚡ Native Zesje Export API Endpoints (Instant Data Harvest)
Instead of scraping DOM elements submission-by-submission, Zesje exposes native export endpoints accessible directly through an authenticated browser session:

| Endpoint | Format | Data Contained | Best Used For |
|:---|:---:|:---|:---|
| `/api/export/xlsx_detailed/<exam_id>` | `.xlsx` | **Complete granular breakdown:** Student metadata, every checked rubric feedback item per problem, and exact TA comments/remarks. | **Primary ground truth** for auditing, comparing TA comments, and synchronizing rubric discrepancies. |
| `/api/export/xlsx/<exam_id>` | `.xlsx` | Compact matrix: Student numbers, names, total scores per problem, and exam total. | Final grade submission and quick score calculation. |
| `/api/export/dataframe/<exam_id>` | Python Dataframe | Direct Pandas-compatible data structure with all problem scores and student identifiers. | Programmatic analysis, distribution curves, and cohort analytics in Python. |
| `/api/export/pdf/<exam_id>` | `.pdf` | Annotated / compiled graded exam booklets for all students. **Fragile large binary stream:** Generates massive multi-gigabyte monolithic PDFs; do not scrape naively in a tight loop. Best invoked with an external download manager or chunked Python stream downloader. | Offline student booklet archiving and post-exam distribution. |
| `/api/export/graders/<exam_id>` | JSON / Report | Breakdown per grader (e.g., DJ van Heumen, Hidde Wiefkers, Lucas van Dekken) with counts of graded submissions per question. | Verifying who graded what and tracking workload balance. |
| `/api/export/full` | `.zip` / DB dump | Complete database dump of the Zesje instance. | System backup and disaster recovery. |

* **Quick Download:** While logged in to Zesje in your browser, click **Export** in the navigation bar or navigate directly to `https://<zesje-instance>/api/export/xlsx_detailed/<exam_id>` (or `/api/export/pdf/<exam_id>`).

### Step 2: Processing (`2_processing/`)
Stitches multi-page answers and builds databases.
1. **Merge Multi-Page Submissions**:
   ```bash
   python 2_processing/merge_images.py --exam <folder-name-or-number>
   ```
   Combines `1b` and `1b_ext` images vertically into a single image inside `data/zesje_images/1b_combined/`.
2. **Rename & Finalize Exports**:
   ```bash
   python 2_processing/finalize_exports.py --exam <folder-name-or-number>
   ```
   Organizes files into `data/final_exports/` in a clean `Copy_xxx.png` format.
3. **Build Grade Database**:
   ```bash
   python 2_processing/build_database.py --exam <folder-name-or-number>
   ```
   Merges grades from `data/zesje_grades.csv` (browser/manual grading) and `data/auto_grades_1a.csv` (AI grading), giving manual overrides priority. Compiles the final table `data/grade_database.csv`.

### Step 3: Grading (`3_grading/`)
Facilitates manual and AI grading of scraped submissions.
* **HTML Browser Grader**:
  Open `3_grading/grader.html` in any web browser. Load the `data/zesje_images` folder to grade offline with touch-controls (pinch-to-zoom/pan). Export the results as `zesje_grades.csv` and move it to `data/`.
* **Gemini AI Math Grader**:
  ```bash
  python 3_grading/auto_grade_1a.py --exam <folder-name-or-number>
  ```
  *Requires `GEMINI_API_KEY` in environment.* Multimodal OCR grading of equation equivalence, outputting to `data/auto_grades_1a.csv`.
* **Manual Terminal Grader**:
  ```bash
  python 3_grading/manual_grade_1a.py --exam <folder-name-or-number>
  ```
  Terminal fast-grading utility with windows image popup.

### Step 4: Upload & Synchronization (`4_upload/`)
Uploads finalized grades, feedback criteria, set aside flags, and remarks back to Zesje.

#### 1. High-Speed Differential Uploader (`4_upload/zesje_uploader.py`)
```bash
python 4_upload/zesje_uploader.py --exam <folder-name-or-number> --dry-run
```
* **Pure DOM Manipulation (Keystroke-Independent):** Eliminates previous Bulma tag score-vs-keystroke collisions (where key numbers `1..N` clashed with point values like `1 pt`). Directly queries `.panel-block.feedback-item` and checks/unchecks tags by `data-tooltip` attribute and `.is-link` class.
* **Set Aside Flag Automation:** Zesje marks flagged submissions with `gradedBy = null` and a button labeled `"Approve"`. Submissions that are approved have `gradedBy = <user>` and a button labeled `"Set aside"`. The uploader detects the live button state, clicks it to toggle when required by the master database (`populated_grades.xlsx` column B), and awaits the async `POST /api/solution/approve/{exam}/{sub}/{prob}` response with an active verification loop.
* **Automated Remarks Sync:** Synchronizes tailored feedback comments directly into Zesje's remarks textarea, firing native input and blur events to trigger Zesje auto-save.

---

## 📅 Legacy exam source folders

The `grading_data/` folders below are preserved source folders. The offline tools use each
selected exam's copy under `data/<exam-folder>/`, where its config, rubric, exports, templates,
populated files, and upload progress stay together. Real exam data is gitignored.

| Source folder | Exam | Zesje exam id | Submissions | Status |
|---|---|---:|---:|---|
| `tn22010/` | Midterm TN22010 Q8 round | 2 | 134 | historical |
| `tn22010_q8/` | Midterm TN22010 Q8 upload round | 2 | 134 | historical |
| `tn2211/` | TN2211 | 3 | 128 | historical |
| **`tn22010_endterm/`** | **Endterm TN22010: 2026/2027** | **3** | **108** | 🟡 not started |
| **`tn2244wi_endterm/`** | **Endterm TN2244WI** | **5** | **49** | 🟡 not started |

**November 2026 endterm round** — deadline **2026-11-16 08:00 Europe/Amsterdam**; coordinators
Kateryna Marynets & Sven Aerts; 156 exams across the two exams. Lucas's questions:
**TN22010 Vraag 1 / 6 / 8** and **TN2244WI Vraag 3 / 9**.

Both endterms are separate exams on the **same** Zesje instance
(`tn22010-2026.zesje.tudelft.nl`); `tn2244wi-2026` is not a live vhost. Scans are already on disk
as `Downloads/exam3.zip` (107 PDFs) and `Downloads/exam5.zip` (47 PDFs) — **the entry counts do not
match the submission counts (108 / 49) and are unreconciled.** No export, rubric extraction, grade
or upload has happened for either exam.

Planning and state for this round live in the AaPM dossier:
`Aa Project management/Jobs/TA_Positions/Replies/Kateryna_Sven_Grading_Q1/grading/`
(goal file `GOAL_NOVEMBER_ENDTERM_DUAL_GRADER_AUDIT.md`, inventory tool
`nov_endterm_inventory.py`).

---

## 🔍 Visual Audit & DOM Inspector (`run_visual_audit.bat`)

To guarantee zero grading regressions, ensure compliance with *verbod op reformatio in peius*, and allow visual pair-inspection of modified submissions on your screen:

```cmd
run_visual_audit.bat
```
Or directly via Python:
```bash
python 4_upload/visual_audit_inspector.py --exam <folder-name-or-number> --flagged-only
```

### Key Features:
* **Side-by-Side Verification:** Compares the live rendered Zesje DOM against target expectations in `populated_grades.xlsx` (Criteria keys, Set Aside status, Total Score, Remarks).
* **Interactive Navigation:**
  - `[Enter]`: Advance to next student.
  - `'p'`: Return to previous student.
  - `'s'`: Toggle Set Aside directly in the live browser.
  - `'r'`: Re-read active DOM state.
  - `'q'`: Quit and generate report.
* **Hands-Free Auto-Walkthrough:** `--auto-step SECONDS` (e.g. 3.0s) steps through all flagged students automatically for hands-free visual monitoring.
* **Selective Inspection Modes:**
  - `[1] FLAGGED ONLY`: Inspects only students with `Set Aside = TRUE` (e.g. upward adjustments awaiting teacher review).
  - `[2] ALL MODIFIED`: Inspects all students whose grades or criteria changed vs baseline.
  - `[3] FULL COHORT`: Scans all submissions across the entire exam.
  - `[4] SINGLE STUDENT`: Quick lookup by student ID (e.g. `5127823`).
* **Audit Dossier Generation:** Writes a Markdown audit report to `data/<exam-folder>/visual_audit_report.md` detailing match statuses and any detected discrepancies.

---

## 🛠️ Modern Excel & Differential Grading Workflow

For exams utilizing Excel-driven grading and multi-pass AI audits (e.g. TN22010 Linear Algebra & Differential Equations):

1. **Harvest Ground Truth:**
   Download the detailed export into `data/<exam-folder>/exports/`.
2. **Initialize Course Structure:**
   ```bash
   python init_grader.py --label <label>
   ```
3. **Generate & Populate Grading Sheets:**
   ```bash
   python generate_empty_sheet.py --exam <folder-name-or-number>
   python populate_sheet_from_grader.py --exam <folder-name-or-number> --input <grades-file>
   ```
   Generates `data/<exam-folder>/populated/populated_grades.xlsx` containing Student ID, Set Aside flag, Grading Status, Criteria (1/0 flags), and Remarks.
   If the grading source identifies cases by Zesje `submission_id`, first join it locally
   through the latest `Downloads/course.sql`: `submission.id -> submission.student_id -> student.id`.
   Match that identifier to the detailed export's `Student ID`, then pass the matched IDs and
   rubric keystrokes to the converter. Option IDs must be translated through the exam's current
   `rubric_mapping.json`; submission IDs and Student IDs are distinct keys. Validate a unique,
   complete join and the intended question selections before uploading. Keep identifiers out of
   console logs and reports.
4. **Differential Upload:**
   ```bash
   python 4_upload/zesje_uploader.py --exam <folder-name-or-number>
   ```
5. **Visual Audit Verification:**
   ```cmd
   run_visual_audit.bat
   ```

---

## 💡 Key Technical Insights & Gotchas

* **Bulma Tag Scores vs Keystrokes:**
  In Zesje's UI, `.tag.is-score` displays the *score* (e.g. `1`), NOT the keyboard shortcut! For criteria 2 through 6 which each award 1 point, `tag.innerText.trim()` is `'1'` for all of them. Keystroke shortcuts are stored in `tag.getAttribute('data-tooltip')`. Always use `data-tooltip` for targeting.
* **Set Aside Button Async Latency:**
  Clicking the Set Aside button triggers an asynchronous background network request. Do not read the button text immediately; loop for up to 2.5 seconds waiting for the button text to transition between `"Set aside"` and `"Approve"`.
* **Export vs DB Representation:**
  The native Zesje Excel export (`xlsx_detailed`) contains all checked criteria and calculated scores, but *does not store the Set Aside flag*. The Set Aside status lives exclusively in the Zesje database/DOM (`gradedBy: null` vs `gradedBy: {id, name}`). Maintain the ground truth in `populated_grades.xlsx` column B.

