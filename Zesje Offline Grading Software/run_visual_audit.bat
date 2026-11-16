@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Zesje Live DOM Visual Audit Inspector
cd /d "%~dp0"

echo =======================================================================
echo       ZESJE LIVE DOM VISUAL AUDIT & INSPECTION SUITE
echo =======================================================================
echo.
echo  This tool launches visible (non-headless) Firefox to visually inspect
echo  and verify live Zesje submissions against your target grading database.
echo.
echo  Select inspection mode:
echo.
echo    [1] Inspect FLAGGED Students (38 Set Aside scans) - Interactive [Enter]
echo    [2] Inspect FLAGGED Students (38 Set Aside scans) - Auto-walkthrough (3s)
echo    [3] Inspect ALL MODIFIED Students (43 students)   - Interactive [Enter]
echo    [4] Inspect FULL COHORT (134 students)            - Interactive [Enter]
echo    [5] Inspect Single Student by Number
echo    [6] Exit
echo.
set /p choice="Enter choice [1-6, default: 1]: "

if "%choice%"=="" set choice=1
if "%choice%"=="1" (
    set /p exam="Exam folder name or unique active exam number: "
    python 4_upload/visual_audit_inspector.py --exam "!exam!" --flagged-only
) else if "%choice%"=="2" (
    set /p exam="Exam folder name or unique active exam number: "
    python 4_upload/visual_audit_inspector.py --exam "!exam!" --flagged-only --auto-step 3.0
) else if "%choice%"=="3" (
    set /p exam="Exam folder name or unique active exam number: "
    python 4_upload/visual_audit_inspector.py --exam "!exam!" --modified-only
) else if "%choice%"=="4" (
    set /p exam="Exam folder name or unique active exam number: "
    python 4_upload/visual_audit_inspector.py --exam "!exam!" --all
) else if "%choice%"=="5" (
    set /p exam="Exam folder name or unique active exam number: "
    set /p sid="Enter student ID (e.g. 5127823): "
    python 4_upload/visual_audit_inspector.py --exam "!exam!" --student !sid!
) else (
    echo Exiting.
    exit /b 0
)

echo.
pause
