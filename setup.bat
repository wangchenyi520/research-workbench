@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and add it to PATH.
    exit /b 1
)

if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 exit /b 1
)

echo [2/4] Installing backend dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 exit /b 1

echo [3/4] Installing desktop dependencies...
".venv\Scripts\python.exe" -m pip install -r desktop-requirements.txt
if errorlevel 1 exit /b 1

echo [4/4] Building frontend...
where npm >nul 2>nul
if errorlevel 1 (
    echo [WARN] npm not found. Install Node.js 18+ then run:
    echo        cd frontend ^&^& npm ci ^&^& npm run build
) else (
    pushd frontend
    if not exist node_modules call npm ci
    if errorlevel 1 (popd & exit /b 1)
    call npm run build
    if errorlevel 1 (popd & exit /b 1)
    popd
)

echo.
echo Setup complete. Run start.bat for browser mode or start_desktop.bat for desktop mode.
