@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\app\main.py" (
    echo [ERROR] backend\app\main.py was not found.
    pause
    exit /b 1
)

set "PYW=pythonw.exe"
if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"

start "" /d "%~dp0backend" "%PYW%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning
timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:8000"
exit /b 0
