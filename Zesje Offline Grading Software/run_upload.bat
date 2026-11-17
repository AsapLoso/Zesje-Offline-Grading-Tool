@echo off
cd /d "%~dp0"

set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

"%PY%" -c "import json, subprocess, sys, exam_config as ec; act=ec.list_active_exams(); arch=ec.list_archived_exams(); all_ex=[(p, False) for p in act]+[(p, True) for p in arch]; pop=[p for p in act if (p/'populated'/'per_problem_targets.json').exists() or (p/'populated'/'populated_grades.xlsx').exists()]; print('='*60+'\n  ZESJE DIFFERENTIAL UPLOADER (exam_config selector)\n'+'='*60); [print(f'  {i}. {p.name} (exam_id={json.loads((p/\"config.json\").read_text(encoding=\"utf-8\")).get(\"exam_id\")})' + (' [ARCHIVE]' if ar else '')) for i,(p,ar) in enumerate(all_ex,1)]; print('  A. ALL populated active exams (Differential)\n  D. Dry-run ALL populated active exams\n'+'='*60); ch=(input(f'Select [A/D/1-{len(all_ex)}, Enter=A]: ').strip() or 'A').upper(); targets=(pop if ch in ('A','D') else [all_ex[int(ch)-1][0]]); dry=(['--dry-run'] if ch=='D' else []); [subprocess.run([sys.executable, '4_upload/zesje_uploader.py', '--config', str(p/'config.json')]+dry, check=True) for p in targets]"
pause
