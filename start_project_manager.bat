@echo off
rem Project-management dashboard (dev tooling, NOT the photo-album app).
rem Local only: http://127.0.0.1:8790  - the album app itself runs on 8765 (start.bat).
chcp 65001 >nul
title AI Album - Project Manager Dashboard (port 8790)
cd /d "%~dp0"
set "PYEXE=%USERPROFILE%\.ai-photo-album\venv\Scripts\python.exe"
if exist "%PYEXE%" (
  "%PYEXE%" -m project_management.server --port 8790
) else (
  py -3.12 -m project_management.server --port 8790
)
pause
