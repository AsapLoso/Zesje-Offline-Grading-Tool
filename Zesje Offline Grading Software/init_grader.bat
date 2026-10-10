@echo off
title Zesje Offline Grader - Initialization Wizard
echo =========================================================
echo       ZESJE OFFLINE GRADER INITIALIZATION WIZARD
echo =========================================================
echo.
echo Dit script initialiseert het offline grader project:
echo   1. Vraagt om de Zesje examenlink (cleant spaties/quotes automatisch)
echo   2. Opent Firefox en vraagt je in te loggen met NetID
echo   3. Navigeer naar de opgaven die je moet nakijken en logt de IDs
echo   4. Vraagt om het aantal (N) extra pagina's / continuation scans
echo   5. Schrijft automatisch config.json en rubric mapping settings
echo.
pause

"C:\Users\Deuts\tudelft-conda\python.exe" "%~dp0init_grader.py"
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Initialisatie is gestopt of mislukt.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [VOLTOOID] Project is geconfigureerd en klaar voor scraping en grading!
pause
