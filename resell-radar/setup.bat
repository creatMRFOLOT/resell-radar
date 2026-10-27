@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install it from python.org and tick Add Python to PATH.
  pause
  exit /b 1
)
python -m pip install -q -r requirements.txt
python -m resell_radar setup
pause
