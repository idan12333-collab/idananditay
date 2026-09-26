@echo off
rem DEV MODE (developer tooling, ADR-020): runs the album app (8765) AND the project dashboard (8790)
rem and restarts them automatically whenever a code file changes; the browser page reloads by itself.
rem For normal use keep using start.bat / start_project_manager.bat (unchanged).
rem Run start.bat once first so the Python environment exists.
chcp 65001 >nul
title AI Album - DEV auto-reload (8765 + 8790)
cd /d "%~dp0"
set "PYEXE=%USERPROFILE%\.ai-photo-album\venv\Scripts\python.exe"
if not exist "%PYEXE%" (
  echo Python environment not found. Run start.bat once first.
  echo לא נמצאה סביבת פייתון. הפעילו פעם אחת את start.bat ואז נסו שוב.
  pause
  exit /b 1
)
"%PYEXE%" scripts\dev_supervisor.py %*
pause
