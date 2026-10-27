@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m resell_radar login
pause
