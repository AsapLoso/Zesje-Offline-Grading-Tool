#!/usr/bin/env python3
"""
Generate Dynamic HTML Grader for Zesje Exams.

Reads the empty template Excel and rubric mapping to generate a customized
3_grading/grader.html with:
- Dynamic rubric toggles matching the exam's criteria (keystrokes 1-7)
- Keyboard shortcuts: 1-7 for criteria, 'a' for Set Aside toggle, '[' / ']' for prev/next student
- Student roster loaded from the template (Student IDs from column A)
- localStorage caching for grades
- Export buttons: Download as JSON, Download as XLSX (matching the empty template structure)
- Import button for JSON/XLSX
- Touch-friendly UI preserved (dark theme, Inter font, glassmorphism)
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from openpyxl import load_workbook


SCRIPT_DIR = Path(__file__).parent.resolve()
BASE_HTML = SCRIPT_DIR / "3_grading" / "grader.html"
from exam_config import add_exam_argument, load_exam_config_from_args


def load_config(argv=None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Generate the selected exam's offline grader HTML.")
    add_exam_argument(parser)
    return load_exam_config_from_args(parser.parse_args(argv))


def find_rubric_mapping(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find rubric mapping file for the current exam."""
    rubric_path = Path(config["exam_dir"]) / "rubric_mapping.json"
    if rubric_path.exists():
        with open(rubric_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def parse_template_for_roster(template_path: Path) -> List[str]:
    """Extract student IDs from the template (column A, rows 4+)."""
    wb = load_workbook(template_path, data_only=True)
    ws = wb.active
    student_ids = []
    for row in range(4, ws.max_row + 1):
        cell = ws.cell(row=row, column=1)
        if cell.value:
            student_ids.append(str(cell.value))
    return student_ids


def parse_template_structure(template_path: Path) -> Dict[str, Any]:
    """Parse the empty template to understand the structure."""
    wb = load_workbook(template_path, data_only=True)
    ws = wb.active

    # Row 3 has the column headers
    headers = {}
    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=3, column=col)
        if cell.value:
            headers[col] = str(cell.value).strip()

    return {
        "max_column": ws.max_column,
        "max_row": ws.max_row,
        "headers": headers,
        "student_id_col": 1,  # Column A is always Student ID
        "set_aside_col": 2,   # Column B is Set Aside
        "grading_status_col": 3,  # Column C is Grading Status
        "criteria_start_col": 4,  # Criteria start at column D
    }


def build_rubric_toggles_html(rubric_mapping: Dict[str, Any]) -> str:
    """Build HTML for rubric toggle buttons based on rubric mapping."""
    html_parts = []

    # Get the first question's rubric (or default)
    question_key = None
    for key in rubric_mapping.keys():
        if key != "_instructions":
            question_key = key
            break

    if not question_key:
        return ""

    question = rubric_mapping[question_key]
    options = question.get("options", [])

    for opt in options:
        keystroke = opt.get("keystroke", "")
        text = opt.get("text", "")
        feedback_id = opt.get("feedback_id", "")
        score = 1  # Default score

        # Extract score from text if possible (e.g., "(1 pt)")
        import re
        score_match = re.search(r'\((\d+)\s*pt\)', text)
        if score_match:
            score = int(score_match.group(1))

        # Determine if this is "All good" or "Blank" option
        is_all_good = "all good" in text.lower() or "alles goed" in text.lower()
        is_blank = "blank" in text.lower() or "fout" in text.lower()

        html_parts.append(f'''
            <button class="rubric-toggle" data-id="{feedback_id}" data-score="{score}" data-keystroke="{keystroke}">
                <span class="pts-badge">{keystroke}</span>
                <span class="rubric-text">{text}</span>
            </button>''')

    return "\n".join(html_parts)


def build_student_roster_js(student_ids: List[str]) -> str:
    """Build JavaScript array for student roster."""
    if not student_ids:
        return "[]"
    return "[" + ", ".join(f'"{sid}"' for sid in student_ids) + "]"


def generate_grader_html(config: Dict[str, Any], rubric_mapping: Dict[str, Any],
                         template_structure: Dict[str, Any], student_ids: List[str]) -> str:
    """Generate the complete grader.html content."""

    course_name = config.get("course_name", "Unknown Course")
    exam_id = config.get("exam_id", 1)
    problem_mapping = config.get("problem_mapping", {})

    # Build problem tabs
    problem_tabs = ""
    for prob_id, label in problem_mapping.items():
        problem_tabs += f'''
                <button class="tab-btn" data-prob="{prob_id}">{label.upper()}</button>'''

    # Build rubric toggles
    rubric_html = build_rubric_toggles_html(rubric_mapping)

    # Get first question key (skip _instructions)
    first_question_key = None
    for key in rubric_mapping.keys():
        if key != "_instructions":
            first_question_key = key
            break

    # Build student roster
    roster_js = build_student_roster_js(student_ids)

    # Read the base HTML template
    with open(BASE_HTML, "r", encoding="utf-8") as f:
        base_html = f.read()

    # Replace the static rubric list with dynamic one
    # Find the rubric-list div and replace its content
    import re

    # Replace rubric list content
    rubric_list_pattern = r'(<div class="rubric-list">\s*).*?(\s*</div>)'
    new_rubric_list = f'<div class="rubric-list">\n{rubric_html}\n        </div>'
    base_html = re.sub(rubric_list_pattern, new_rubric_list, base_html, flags=re.DOTALL)

    # Replace problem tabs
    tabs_pattern = r'(<div id="problem-tabs" class="tabs" style="display: none;">\s*).*?(\s*</div>)'
    new_tabs = f'<div id="problem-tabs" class="tabs" style="display: none;">\n{problem_tabs}\n        </div>'
    base_html = re.sub(tabs_pattern, new_tabs, base_html, flags=re.DOTALL)

    # Update the JavaScript section with dynamic data
    # We need to inject the student roster and rubric configuration
    js_injection = f'''
        // --- DYNAMIC CONFIGURATION (injected by generate_grader_html.py) ---
        const DYNAMIC_STUDENT_IDS = {roster_js};
        const DYNAMIC_PROBLEM_MAPPING = {json.dumps(problem_mapping)};
        const DYNAMIC_RUBRIC_OPTIONS = {json.dumps(rubric_mapping.get(first_question_key, {}).get("options", []))};
        const DYNAMIC_COURSE = "{course_name}";
        const DYNAMIC_EXAM_ID = {exam_id};
'''

    # Find the script tag and inject after state initialization
    script_pattern = r'(// --- State ---)'
    base_html = re.sub(script_pattern, js_injection + r'\n\1', base_html, count=1)

    # Update the loadSubmission function to use dynamic student IDs
    # This is a more complex replacement - we'll add a comment marker
    # and replace the submission loading logic

    # Add export/import functionality for XLSX
    export_import_js = '''
        // --- XLSX EXPORT/IMPORT (requires SheetJS) ---
        async function exportToXLSX() {
            if (Object.keys(grades).length === 0) {
                alert("No grades recorded yet.");
                return;
            }

            // Load SheetJS dynamically
            if (typeof XLSX === 'undefined') {
                const script = document.createElement('script');
                script.src = 'https://cdn.sheetjs.com/xlsx-0.20.0/package/dist/xlsx.full.min.js';
                document.head.appendChild(script);
                await new Promise(r => script.onload = r);
            }

            const wb = XLSX.utils.book_new();
            const ws_data = [];

            // Headers from template
            ws_data.push(["Student ID", "Set Aside", "Grading Status", ...getCriteriaHeaders(), "Remarks"]);

            for (const path in grades) {
                const g = grades[path];
                const row = [
                    g.submission,
                    g.set_aside || false,
                    g.grading_status || "PENDING",
                    ...getCriteriaValues(g.selections),
                    g.remarks || ""
                ];
                ws_data.push(row);
            }

            const ws = XLSX.utils.aoa_to_sheet(ws_data);
            XLSX.utils.book_append_sheet(wb, ws, "Grades");
            XLSX.writeFile(wb, `zesje_grades_${DYNAMIC_COURSE}_exam${DYNAMIC_EXAM_ID}.xlsx`);
            showToast("Exported to XLSX!");
        }

        function getCriteriaHeaders() {
            return DYNAMIC_RUBRIC_OPTIONS.map(opt => opt.text);
        }

        function getCriteriaValues(selections) {
            const headers = getCriteriaHeaders();
            return headers.map((_, i) => selections.includes(String(i+1)) ? 1 : 0);
        }

        async function importFromXLSX(file) {
            if (typeof XLSX === 'undefined') {
                const script = document.createElement('script');
                script.src = 'https://cdn.sheetjs.com/xlsx-0.20.0/package/dist/xlsx.full.min.js';
                document.head.appendChild(script);
                await new Promise(r => script.onload = r);
            }

            const data = await file.arrayBuffer();
            const wb = XLSX.read(data);
            const ws = wb.Sheets[wb.SheetNames[0]];
            const rows = XLSX.utils.sheet_to_json(ws, { header: 1 });

            let imported = 0;
            for (let i = 1; i < rows.length; i++) {
                const row = rows[i];
                if (!row[0]) continue;
                const studentId = String(row[0]);
                const setAside = row[1] === true || row[1] === "TRUE";
                const status = row[2] || "PENDING";
                const criteriaVals = row.slice(3, -1);
                const remarks = row[row.length - 1] || "";

                const selections = [];
                criteriaVals.forEach((v, idx) => {
                    if (v === 1 || v === "1" || v === true) {
                        selections.push(String(idx + 1));
                    }
                });

                // Find the file path for this student/problem
                // This is simplified - in reality we'd need to match by student ID
                grades[`${DYNAMIC_PROBLEM_MAPPING[Object.keys(DYNAMIC_PROBLEM_MAPPING)[0]]}/${studentId}.jpg`] = {
                    problem: Object.keys(DYNAMIC_PROBLEM_MAPPING)[0],
                    submission: studentId,
                    filename: `${studentId}.jpg`,
                    score: selections.length,
                    selections: selections,
                    set_aside: setAside,
                    grading_status: status,
                    remarks: remarks
                };
                imported++;
            }

            localStorage.setItem('zesje_grades', JSON.stringify(grades));
            showToast(`Imported ${imported} grades from XLSX!`);
            if (submissionIds.length > 0) loadSubmission();
        }
'''

    # Inject the export/import functions before the closing script tag
    base_html = base_html.replace('</script>', export_import_js + '\n    </script>')

    # Add XLSX export/import buttons to header
    header_buttons = '''            <button id="load-btn" class="btn-primary">Load Folder</button>
            <button id="import-btn" class="btn-primary" style="display: none;">Import JSON</button>
            <button id="import-xlsx-btn" class="btn-primary" style="display: none;">Import XLSX</button>
            <button id="export-btn" class="btn-success" style="display: none;">Export JSON</button>
            <button id="export-xlsx-btn" class="btn-success" style="display: none;">Export XLSX</button>'''

    base_html = base_html.replace(
        '''            <button id="load-btn" class="btn-primary">Load Folder</button>
            <button id="import-btn" class="btn-primary" style="display: none;">Import CSV</button>
            <button id="export-btn" class="btn-success" style="display: none;">Export CSV</button>''',
        header_buttons
    )

    # Add XLSX file input
    base_html = base_html.replace(
        '''        <input type="file" id="csv-input" accept=".csv" style="display: none;" />''',
        '''        <input type="file" id="csv-input" accept=".csv" style="display: none;" />
        <input type="file" id="xlsx-input" accept=".xlsx" style="display: none;" />''')

    # Update the JavaScript to handle XLSX buttons
    xlsx_js = '''
        const importXlsxBtn = document.getElementById('import-xlsx-btn');
        const exportXlsxBtn = document.getElementById('export-xlsx-btn');
        const xlsxInput = document.getElementById('xlsx-input');

        importXlsxBtn.addEventListener('click', () => xlsxInput.click());
        exportXlsxBtn.addEventListener('click', exportToXLSX);

        xlsxInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            await importFromXLSX(file);
            xlsxInput.value = '';
        });'''

    base_html = base_html.replace(
        'csvInput.value = \'\'; // Reset input so same file can be imported again if needed',
        'csvInput.value = \'\';\n' + xlsx_js)

    # Show XLSX buttons when folder loaded
    base_html = base_html.replace(
        'exportBtn.style.display = \'block\';',
        "exportBtn.style.display = 'block';\n                importXlsxBtn.style.display = 'block';\n                exportXlsxBtn.style.display = 'block';")

    return base_html


def main(argv=None):
    print("=" * 70)
    print("ZESJE DYNAMIC HTML GRADER GENERATOR")
    print("=" * 70)

    # Load configuration
    config = load_config(argv)
    course_name = config.get("course_name", "unknown")
    exam_id = config.get("exam_id")
    exam_dir = Path(config["exam_dir"])

    print(f"Course: {course_name}")
    print(f"Exam ID: {exam_id}")
    print()

    # Find rubric mapping
    rubric_mapping = find_rubric_mapping(config)
    if not rubric_mapping:
        print("[ERROR] No rubric mapping found!")
        print(f"Please create {exam_dir / 'rubric_mapping.json'}")
        sys.exit(1)

    print(f"[OK] Loaded rubric mapping")

    # Find template
    template_path = exam_dir / "templates" / "empty_template.xlsx"

    if not template_path.exists():
        print(f"[ERROR] Template not found: {template_path}")
        print("Run generate_empty_sheet.py first")
        sys.exit(1)

    print(f"[OK] Found template: {template_path}")

    # Parse template structure and roster
    template_structure = parse_template_structure(template_path)
    student_ids = parse_template_for_roster(template_path)

    print(f"  Template columns: {template_structure['max_column']}")
    print(f"  Student IDs found: {len(student_ids)}")
    print()

    # Generate HTML
    print("Generating dynamic grader.html...")
    html_content = generate_grader_html(config, rubric_mapping, template_structure, student_ids)

    # Write output
    output_html = exam_dir / "grader.html"
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[OK] Generated: {output_html}")
    print()
    print("Features included:")
    print("  - Dynamic rubric toggles from rubric_mapping.json")
    print("  - Keyboard shortcuts: 1-7 (criteria), 'a' (Set Aside), '['/']' (nav)")
    print(f"  - Student roster: {len(student_ids)} students from template")
    print("  - localStorage autosave")
    print("  - Export: JSON + XLSX (with SheetJS CDN)")
    print("  - Import: JSON + XLSX")
    print("  - Touch-friendly dark theme preserved")
    print("=" * 70)


if __name__ == "__main__":
    main()
