@echo off
chcp 65001 >nul
cd /d "%~dp0"
:loop
python -m resell_radar run
echo.
echo Stopped. Restarting in 30 seconds. Close this window to quit.
timeout /t 30 >nul
goto loop
