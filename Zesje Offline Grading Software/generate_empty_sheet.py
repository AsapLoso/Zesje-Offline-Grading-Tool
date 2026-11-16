#!/usr/bin/env python3
"""
Multi-Tier Header Parser & Empty Template Generator for Zesje Detailed Exports.

Parses any Zesje detailed export (.xlsx) to extract the 3-tier header structure
(Row 1: merged question headers, Row 2: criteria labels & remarks,
 Row 3: Student ID anchor + criteria score columns + Remarks)
and emits an empty .xlsx template preserving the exact layout while injecting
control columns: 'Set Aside' (TRUE/FALSE) and 'Grading Status'
(PENDING/GRADED/FLAGGED/ARBITRATED).

Configuration is read from the selected exam's config.json.
Output: data/<exam>/templates/empty_template.xlsx
"""

import sys
import json
import argparse
from pathlib import Path
from copy import copy

from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

# Windows UTF-8 guardrail
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


SCRIPT_DIR = Path(__file__).parent.resolve()
from exam_config import add_exam_argument, load_exam_config_from_args


def load_config(argv=None):
    parser = argparse.ArgumentParser(description="Generate an empty template for one selected exam.")
    add_exam_argument(parser)
    return load_exam_config_from_args(parser.parse_args(argv))


def find_export_file(config):
    """
    Locate the Zesje detailed export .xlsx file.
    Priority:
    1. Manual export path from config (auth fallback)
    2. data/<exam>/exports/ (most recent .xlsx)
    """
    exam_dir = Path(config["exam_dir"])

    # 1. Manual export path from auth fallback
    manual_path = config.get("manual_export_path")
    if manual_path and Path(manual_path).exists():
        return Path(manual_path)

    # 2. Selected exam folder
    exports_dir = exam_dir / "exports"
    if exports_dir.exists():
        xlsx_files = list(exports_dir.glob("*.xlsx"))
        if xlsx_files:
            return max(xlsx_files, key=lambda f: f.stat().st_mtime)

    return None


def parse_zesje_headers(ws):
    """
    Parse the 3-tier header structure from a Zesje detailed export worksheet.

    Returns:
        dict with keys:
        - 'question_headers': list of (question_label, start_col, end_col) from row 1
        - 'criteria_labels': list of cell values from row 2 (1-indexed columns)
        - 'student_id_col': column index (1-based) where "Student ID" appears in row 3
        - 'criteria_columns': list of column indices for criteria score columns (row 3)
        - 'remarks_col': column index for "Remarks" column (row 3)
        - 'num_criteria': number of criteria columns
        - 'merged_ranges': list of merged cell ranges from row 1
    """
    result = {
        'question_headers': [],
        'criteria_labels': [],
        'student_id_col': None,
        'criteria_columns': [],
        'remarks_col': None,
        'num_criteria': 0,
        'merged_ranges': []
    }

    # Capture merged ranges from row 1
    for merged_range in ws.merged_cells.ranges:
        if merged_range.min_row == 1 and merged_range.max_row == 1:
            result['merged_ranges'].append(merged_range)

    # Row 1: Question headers (merged cells)
    row1_vals = []
    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=1, column=col)
        row1_vals.append(cell.value)

    # Identify question blocks from merged ranges
    for merged_range in result['merged_ranges']:
        q_label = ws.cell(row=1, column=merged_range.min_col).value
        if q_label:
            result['question_headers'].append((
                str(q_label).strip(),
                merged_range.min_col,
                merged_range.max_col
            ))

    # Row 2: Criteria labels & Remarks
    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=2, column=col)
        val = cell.value
        result['criteria_labels'].append(str(val).strip() if val else "")

    # Row 3: Student ID anchor, criteria score columns, Remarks
    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=3, column=col)
        val = cell.value
        if val:
            val_str = str(val).strip().lower()
            if "student id" in val_str:
                result['student_id_col'] = col
            elif "remark" in val_str:
                result['remarks_col'] = col
            else:
                # Criteria score column (typically 1/0 values)
                result['criteria_columns'].append(col)

    result['num_criteria'] = len(result['criteria_columns'])

    return result


def copy_cell_style(source_cell, target_cell):
    """Copy all style attributes from source cell to target cell."""
    if source_cell.has_style:
        target_cell.font = copy(source_cell.font)
        target_cell.alignment = copy(source_cell.alignment)
        target_cell.border = copy(source_cell.border)
        target_cell.fill = copy(source_cell.fill)
        target_cell.number_format = copy(source_cell.number_format)
        target_cell.protection = copy(source_cell.protection)


def write_merged_header_row(ws, row_idx, question_headers, merged_ranges, style_source_ws=None):
    """
    Write Row 1 with merged question headers, preserving original merged ranges.
    """
    for q_label, start_col, end_col in question_headers:
        # Write the label in the first column of the merge
        cell = ws.cell(row=row_idx, column=start_col, value=q_label)
        if style_source_ws:
            src_cell = style_source_ws.cell(row=row_idx, column=start_col)
            copy_cell_style(src_cell, cell)
        
        # Apply merge
        if start_col != end_col:
            ws.merge_cells(start_row=row_idx, start_column=start_col,
                           end_row=row_idx, end_column=end_col)
        
        # Center alignment for merged header
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)


def write_criteria_row(ws, row_idx, criteria_labels, student_id_col, remarks_col,
                       criteria_columns, style_source_ws=None):
    """
    Write Row 2 with criteria labels and Remarks, aligned with Row 3 control columns.
    Inserts 2 empty columns after Student ID for Set Aside and Grading Status headers.
    """
    # Column 1 (Student ID position) - typically empty in Row 2
    cell = ws.cell(row=row_idx, column=student_id_col, value="")
    if style_source_ws:
        src_cell = style_source_ws.cell(row=row_idx, column=student_id_col)
        copy_cell_style(src_cell, cell)
    
    # Columns 2-3 (Set Aside, Grading Status positions) - empty headers
    for col_idx in [student_id_col + 1, student_id_col + 2]:
        cell = ws.cell(row=row_idx, column=col_idx, value="")
        if style_source_ws and student_id_col <= style_source_ws.max_column:
            src_cell = style_source_ws.cell(row=row_idx, column=student_id_col)
            copy_cell_style(src_cell, cell)
    
    # Criteria labels shifted by 2 to align with Row 3 criteria columns
    for i, orig_col in enumerate(criteria_columns):
        new_col = orig_col + 2
        label = criteria_labels[orig_col - 1] if orig_col - 1 < len(criteria_labels) else ""
        cell = ws.cell(row=row_idx, column=new_col, value=label)
        if style_source_ws:
            src_cell = style_source_ws.cell(row=row_idx, column=orig_col)
            copy_cell_style(src_cell, cell)
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    
    # Remarks column shifted by 2
    remarks_new_col = remarks_col + 2
    label = criteria_labels[remarks_col - 1] if remarks_col - 1 < len(criteria_labels) else "Remarks"
    cell = ws.cell(row=row_idx, column=remarks_new_col, value=label)
    if style_source_ws:
        src_cell = style_source_ws.cell(row=row_idx, column=remarks_col)
        copy_cell_style(src_cell, cell)
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)


def write_anchor_row(ws, row_idx, student_id_col, criteria_columns, remarks_col,
                     style_source_ws=None, insert_set_aside=True, insert_grading_status=True):
    """
    Write Row 3: Student ID anchor, criteria score columns, Remarks.
    Inserts 'Set Aside' after Student ID and 'Grading Status' after Set Aside.
    """
    # Calculate new column positions after inserting control columns
    # Original: [Student ID] [criteria...] [Remarks]
    # New:      [Student ID] [Set Aside] [Grading Status] [criteria...] [Remarks]
    
    offset = 0
    
    # Student ID column
    cell = ws.cell(row=row_idx, column=student_id_col, value="Student ID")
    if style_source_ws:
        src_cell = style_source_ws.cell(row=row_idx, column=student_id_col)
        copy_cell_style(src_cell, cell)
    cell.font = Font(bold=True)
    
    # Insert Set Aside column after Student ID
    set_aside_col = student_id_col + 1
    cell = ws.cell(row=row_idx, column=set_aside_col, value="Set Aside")
    if style_source_ws:
        src_cell = style_source_ws.cell(row=row_idx, column=student_id_col)
        copy_cell_style(src_cell, cell)
    cell.font = Font(bold=True)
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    
    # Insert Grading Status column after Set Aside
    grading_status_col = set_aside_col + 1
    cell = ws.cell(row=row_idx, column=grading_status_col, value="Grading Status")
    if style_source_ws:
        src_cell = style_source_ws.cell(row=row_idx, column=student_id_col)
        copy_cell_style(src_cell, cell)
    cell.font = Font(bold=True)
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    
    # Write criteria columns (shifted by 2)
    for i, orig_col in enumerate(criteria_columns):
        new_col = orig_col + 2
        cell = ws.cell(row=row_idx, column=new_col, value="1/0")
        if style_source_ws:
            src_cell = style_source_ws.cell(row=row_idx, column=orig_col)
            copy_cell_style(src_cell, cell)
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Write Remarks column (shifted by 2)
    remarks_new_col = remarks_col + 2
    cell = ws.cell(row=row_idx, column=remarks_new_col, value="Remarks")
    if style_source_ws:
        src_cell = style_source_ws.cell(row=row_idx, column=remarks_col)
        copy_cell_style(src_cell, cell)
    cell.font = Font(bold=True)
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    
    return {
        'student_id_col': student_id_col,
        'set_aside_col': set_aside_col,
        'grading_status_col': grading_status_col,
        'criteria_columns': [c + 2 for c in criteria_columns],
        'remarks_col': remarks_new_col
    }


def create_empty_template(source_ws, header_info, config):
    """
    Create a new workbook with the empty template preserving the 3-tier header
    structure and injecting control columns.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = source_ws.title or "Grades"
    
    # Parse header info
    question_headers = header_info['question_headers']
    criteria_labels = header_info['criteria_labels']
    student_id_col = header_info['student_id_col']
    criteria_columns = header_info['criteria_columns']
    remarks_col = header_info['remarks_col']
    merged_ranges = header_info['merged_ranges']
    
    # Row 1: Question headers (merged)
    write_merged_header_row(ws, 1, question_headers, merged_ranges, source_ws)
    
    # Row 2: Criteria labels & Remarks (aligned with Row 3 control columns)
    write_criteria_row(ws, 2, criteria_labels, student_id_col, remarks_col,
                       criteria_columns, source_ws)
    
    # Row 3: Student ID, Set Aside, Grading Status, criteria, Remarks
    new_col_map = write_anchor_row(
        ws, 3, student_id_col, criteria_columns, remarks_col,
        source_ws, insert_set_aside=True, insert_grading_status=True
    )
    
    # Set column widths based on source (approximate)
    for col_idx in range(1, ws.max_column + 1):
        src_col = col_idx
        # Map back to source columns for width reference
        if col_idx > new_col_map['grading_status_col']:
            src_col = col_idx - 2
        elif col_idx > new_col_map['set_aside_col']:
            src_col = col_idx - 1
        
        if src_col <= source_ws.max_column:
            src_col_letter = get_column_letter(src_col)
            if src_col_letter in source_ws.column_dimensions:
                ws.column_dimensions[get_column_letter(col_idx)].width = \
                    source_ws.column_dimensions[src_col_letter].width
    
    # Ensure minimum widths for new columns
    ws.column_dimensions[get_column_letter(new_col_map['set_aside_col'])].width = 12
    ws.column_dimensions[get_column_letter(new_col_map['grading_status_col'])].width = 18
    
    # Add a few empty student rows (row 4+) with default values
    # This helps validate the structure and gives a starting template
    num_template_rows = 5  # Add 5 empty rows as template
    for row_idx in range(4, 4 + num_template_rows):
        # Student ID column - empty
        ws.cell(row=row_idx, column=new_col_map['student_id_col'], value="")
        
        # Set Aside - default FALSE
        cell = ws.cell(row=row_idx, column=new_col_map['set_aside_col'], value="FALSE")
        cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # Grading Status - default PENDING
        cell = ws.cell(row=row_idx, column=new_col_map['grading_status_col'], value="PENDING")
        cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # Criteria columns - empty (will be filled with 0/1 during grading)
        for crit_col in new_col_map['criteria_columns']:
            cell = ws.cell(row=row_idx, column=crit_col, value="")
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        # Remarks - empty
        ws.cell(row=row_idx, column=new_col_map['remarks_col'], value="")
    
    # Freeze panes at row 4 (after headers)
    ws.freeze_panes = f"A4"
    
    # Auto-filter on header row (row 3)
    last_col_letter = get_column_letter(ws.max_column)
    ws.auto_filter.ref = f"A3:{last_col_letter}3"
    
    return wb, new_col_map


def main():
    print("=" * 70)
    print("ZESJE EMPTY TEMPLATE GENERATOR")
    print("=" * 70)
    
    # Load configuration
    config = load_config()
    course_name = config.get("course_name", "unknown")
    exam_id = config.get("exam_id")
    problem_mapping = config.get("problem_mapping", {})
    
    print(f"Course: {course_name}")
    print(f"Exam ID: {exam_id}")
    print(f"Problem Mapping: {problem_mapping}")
    print()
    
    # Find export file
    export_file = find_export_file(config)
    if not export_file:
        print("[ERROR] No Zesje detailed export (.xlsx) found.")
        print("Expected locations:")
        course_slug = course_name.lower() if course_name else f"exam{exam_id}"
        print(f"  {Path(config['exam_dir']) / 'exports' / '*.xlsx'}")
        print("  3. Manual path from config.json 'manual_export_path'")
        print()
        print("Please download the detailed export from Zesje:")
        print(f"  {config.get('zesje_base_url', '')}/api/export/xlsx_detailed/{exam_id}")
        print("And place it in the exports directory.")
        sys.exit(1)
    
    print(f"[OK] Found export: {export_file}")
    
    # Load source workbook
    print("Parsing Zesje detailed export...")
    src_wb = load_workbook(export_file, data_only=True)
    src_ws = src_wb.active
    
    # Parse headers
    header_info = parse_zesje_headers(src_ws)
    
    print(f"  Questions found: {len(header_info['question_headers'])}")
    for q_label, start, end in header_info['question_headers']:
        print(f"    - {q_label} (cols {start}-{end})")
    print(f"  Criteria columns: {header_info['num_criteria']}")
    print(f"  Student ID column: {header_info['student_id_col']}")
    print(f"  Remarks column: {header_info['remarks_col']}")
    print(f"  Merged ranges in row 1: {len(header_info['merged_ranges'])}")
    print()
    
    # Create empty template
    print("Generating empty template with control columns...")
    template_wb, col_map = create_empty_template(src_ws, header_info, config)
    
    # Prepare output directory
    course_slug = course_name.lower() if course_name else f"exam{exam_id}"
    output_dir = Path(config["exam_dir"]) / "templates"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "empty_template.xlsx"
    
    # Save template
    template_wb.save(output_file)
    print(f"[OK] Empty template saved to: {output_file}")
    print()
    
    # Print column map for verification
    print("Column Map (new template):")
    print(f"  Student ID:      Column {col_map['student_id_col']} ({get_column_letter(col_map['student_id_col'])})")
    print(f"  Set Aside:       Column {col_map['set_aside_col']} ({get_column_letter(col_map['set_aside_col'])}) - TRUE/FALSE")
    print(f"  Grading Status:  Column {col_map['grading_status_col']} ({get_column_letter(col_map['grading_status_col'])}) - PENDING/GRADED/FLAGGED/ARBITRATED")
    print(f"  Criteria:        Columns {[get_column_letter(c) for c in col_map['criteria_columns']]}")
    print(f"  Remarks:         Column {col_map['remarks_col']} ({get_column_letter(col_map['remarks_col'])})")
    print()
    print("Template includes 5 empty student rows with defaults:")
    print("  Set Aside = FALSE, Grading Status = PENDING")
    print()
    print("Next steps:")
    print(f"  1. Review template: {output_file}")
    print("  2. Populate with grades using populate_sheet_from_grader.py")
    print("  3. Upload with 4_upload/zesje_uploader.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
