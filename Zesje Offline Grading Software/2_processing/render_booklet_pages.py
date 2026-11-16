"""Render named exam pages from student booklet ZIPs as a traceable local fallback."""
import argparse
import json
import zipfile
from pathlib import Path

import pymupdf


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--exam-json', required=True, type=Path)
    p.add_argument('--zip', required=True, type=Path)
    p.add_argument('--problem', action='append', required=True, type=int)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    exam = json.loads(args.exam_json.read_text(encoding='utf-8'))
    problems = {q['id']: q for q in exam['problems']}
    if not set(args.problem) <= problems.keys():
        p.error('unknown problem ID')
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'exam_id': exam['id'], 'source': str(args.zip), 'method': 'whole booklet page, JPEG 1.5x', 'saved': [], 'missing': [], 'failed': []}
    with zipfile.ZipFile(args.zip) as archive:
        names = set(archive.namelist())
        for submission in exam['submissions']:
            sid = submission['id']
            student = submission.get('student')
            name = f"student-{student['id']}.pdf" if student else None
            if not name or name not in names:
                report['missing'].append(sid)
                continue
            try:
                with pymupdf.open(stream=archive.read(name), filetype='pdf') as doc:
                    rendered = {}
                    for pid in args.problem:
                        page_number = problems[pid]['page']
                        if page_number not in rendered:
                            pix = doc[page_number].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                            rendered[page_number] = pix.tobytes('jpeg', jpg_quality=85)
                        folder = args.output / f'problem_{pid}'
                        folder.mkdir(exist_ok=True)
                        (folder / f'sub_{sid}.jpg').write_bytes(rendered[page_number])
                        report['saved'].append([sid, pid, page_number])
            except Exception as exc:
                report['failed'].append([sid, type(exc).__name__])
            (args.output / 'booklet_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (args.output / 'booklet_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(f"Exam {exam['id']}: {len(report['saved'])} page files, {len(report['missing'])} missing booklets, {len(report['failed'])} failures", flush=True)


if __name__ == '__main__':
    main()
