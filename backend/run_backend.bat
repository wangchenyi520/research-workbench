@echo off
cd /d "%~dp0"
set "PY=python"
if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"

"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning
if errorlevel 1 pause
