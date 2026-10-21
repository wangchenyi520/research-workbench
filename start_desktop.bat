@echo off
setlocal
cd /d "%~dp0"
set "PYW=pythonw.exe"
if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"

start "" /b "%PYW%" desktop.py
exit /b 0
