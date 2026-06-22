@echo off
echo ========================================
echo   MyAISpace Search API - Starting...
echo ========================================
cd /d %~dp0
pip install -r requirements.txt
echo.
echo Server: http://localhost:8000
echo.
python app/main.py
pause
