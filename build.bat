@echo off
REM Build the portable Windows .exe (and a portable .zip).
REM Requires: pip install -r requirements.txt pyinstaller
setlocal
cd /d "%~dp0"
python build.py --zip
echo.
echo Output is in the dist\ folder.
pause
