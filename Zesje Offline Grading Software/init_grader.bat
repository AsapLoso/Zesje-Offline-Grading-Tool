@echo off
title Zesje Offline Grader - Initialization Wizard
echo =========================================================
echo       ZESJE OFFLINE GRADER INITIALIZATION WIZARD
echo =========================================================
echo.
echo Dit script initialiseert het offline grader project:
echo   1. Vraagt om een label voor de examemap
echo   2. Vraagt om de Zesje examenlink (cleant spaties/quotes automatisch)
echo   3. Opent Firefox en vraagt je in te loggen met NetID
echo   4. Navigeer naar de opgaven die je moet nakijken en logt de IDs
echo   5. Vraagt om het aantal (N) extra pagina's / continuation scans
echo   6. Schrijft de config naar de gekozen examemap
echo.
set /p exam_label="Label voor deze examemap (bijv. endterm): "
if "%exam_label%"=="" (
    echo [ERROR] Een examelabel is verplicht.
    exit /b 2
)
pause

python "%~dp0init_grader.py" --label "%exam_label%"
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Initialisatie is gestopt of mislukt.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [VOLTOOID] Project is geconfigureerd en klaar voor scraping en grading!
pause
