@echo off
cd /d "%~dp0"
set /p EXAM_NAME=Enter exam folder name (e.g. endterm_tn22010_exam3): 
if "%EXAM_NAME%"=="" (
    echo [ERROR] No exam name provided.
    pause
    exit /b 1
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "4_upload\zesje_uploader.py" --exam "%EXAM_NAME%" --resume
) else (
    python "4_upload\zesje_uploader.py" --exam "%EXAM_NAME%" --resume
)
pause
