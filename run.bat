@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting ActiveLearn AI ...
python -c "import flask, itsdangerous" 2>nul || python -m pip install flask itsdangerous werkzeug
start "" cmd /c "timeout /t 6 >nul & start http://localhost:5000"
python backend\app.py
pause
