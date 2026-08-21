@echo off
setlocal EnableExtensions EnableDelayedExpansion
title DFAT Launcher

:: Keep the window open even if something unexpected fails
cd /d "%~dp0" || (
    echo ERROR: Could not change to script directory.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo   DFAT - Digital Forensics Automation Tool
echo   AI-Assisted Evidence Analysis
echo   Starting local development environment...
echo ================================================================
echo.

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PYTHONPATH=%ROOT%\src"
set "DFAT_ENV=development"
set "PYTHONDONTWRITEBYTECODE=1"
set "BROWSER=none"

:: ---------------------------------------------------------------------------
:: Prerequisites: Python 3.11+
:: ---------------------------------------------------------------------------
set "PY_CMD="
where python >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"
if not defined PY_CMD (
    where python3 >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python3"
)
if not defined PY_CMD (
    echo ERROR: Python 3.11+ is required. Download from
    echo https://www.python.org/downloads/
    goto :fail
)
"%PY_CMD%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.11+ is required. Download from
    echo https://www.python.org/downloads/
    goto :fail
)

:: ---------------------------------------------------------------------------
:: Prerequisites: Node.js 18+
:: ---------------------------------------------------------------------------
where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js 18+ is required. Download from
    echo https://nodejs.org/
    goto :fail
)
node -e "const v=process.version.slice(1).split('.').map(Number); process.exit(v[0]>=18?0:1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js 18+ is required. Download from
    echo https://nodejs.org/
    goto :fail
)

:: ---------------------------------------------------------------------------
:: Prerequisites: npm
:: ---------------------------------------------------------------------------
where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm is required. It is normally installed with Node.js.
    echo Download from https://nodejs.org/
    goto :fail
)

:: ---------------------------------------------------------------------------
:: First-run detection
:: ---------------------------------------------------------------------------
set "NEED_SETUP=0"
if not exist "%ROOT%\.env" set "NEED_SETUP=1"
if not exist "%ROOT%\frontend\node_modules\" set "NEED_SETUP=1"
if not exist "%ROOT%\data\dfat.db" set "NEED_SETUP=1"

if "!NEED_SETUP!"=="1" goto :first_run
goto :subsequent_run

:first_run
echo [%TIME%] First-run setup detected...

if not exist "%ROOT%\.env" (
    if exist "%ROOT%\.env.example" (
        copy /Y "%ROOT%\.env.example" "%ROOT%\.env" >nul
        echo [%TIME%] Created .env from template
    ) else (
        echo WARNING: .env.example not found - create .env manually.
    )
)

echo [%TIME%] Creating data directories...
if not exist "%ROOT%\data" mkdir "%ROOT%\data"
if not exist "%ROOT%\data\evidence" mkdir "%ROOT%\data\evidence"
if not exist "%ROOT%\data\datasets" mkdir "%ROOT%\data\datasets"
if not exist "%ROOT%\data\outputs" mkdir "%ROOT%\data\outputs"
if not exist "%ROOT%\data\ground_truth" mkdir "%ROOT%\data\ground_truth"
if not exist "%ROOT%\data\questionnaire" mkdir "%ROOT%\data\questionnaire"
if not exist "%ROOT%\data\ml" mkdir "%ROOT%\data\ml"
if not exist "%ROOT%\data\knowledge" mkdir "%ROOT%\data\knowledge"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

set "USE_VENV=1"
if not exist "%ROOT%\venv\Scripts\activate.bat" (
    echo [%TIME%] Creating Python virtual environment...
    "%PY_CMD%" -m venv "%ROOT%\venv"
    if errorlevel 1 (
        echo WARNING: Could not create venv - installing into system Python.
        set "USE_VENV=0"
    ) else (
        echo [%TIME%] Virtual environment created
    )
)

if "!USE_VENV!"=="1" (
    call "%ROOT%\venv\Scripts\activate.bat"
)

echo [%TIME%] Installing backend dependencies...
:: auth is required to import the app; reporting matches QUICKSTART
if "!USE_VENV!"=="1" (
    python -m pip install -e ".[dev,auth,reporting]" --quiet
) else (
    python -m pip install -e ".[dev,auth,reporting]" --quiet --break-system-packages
)
if errorlevel 1 (
    echo ERROR: Backend dependency installation failed.
    goto :fail
)
echo [%TIME%] Backend dependencies installed
:: Optional extras (degrade gracefully if install fails)
python -m pip install -e ".[intelligence,ml,threat_intel]" --quiet >nul 2>&1
if errorlevel 1 (
    echo [%TIME%] Optional intelligence/ml extras skipped - core app will still run
) else (
    echo [%TIME%] Optional intelligence/ml extras installed
)

echo [%TIME%] Initialising database...
python -m alembic -c src/dfat/database/migrations/alembic.ini upgrade head
if errorlevel 1 (
    echo ERROR: Database initialisation failed.
    goto :fail
)
echo [%TIME%] Database initialised

if not exist "%ROOT%\frontend\node_modules\" (
    echo [%TIME%] Installing frontend dependencies...
    pushd "%ROOT%\frontend"
    call npm install --legacy-peer-deps
    if errorlevel 1 (
        popd
        echo ERROR: Frontend dependency installation failed.
        goto :fail
    )
    popd
    echo [%TIME%] Frontend dependencies installed
)

echo [%TIME%] Starting temporary backend for seed data...
if exist "%ROOT%\venv\Scripts\activate.bat" (
    start "DFAT Seed Backend" /MIN cmd /k "cd /d ""%ROOT%"" && call ""%ROOT%\venv\Scripts\activate.bat"" && set PYTHONPATH=%ROOT%\src&& set DFAT_ENV=development&& set PYTHONDONTWRITEBYTECODE=1&& python -m uvicorn dfat.app:create_app --factory --host 127.0.0.1 --port 8000"
) else (
    start "DFAT Seed Backend" /MIN cmd /k "cd /d ""%ROOT%"" && set PYTHONPATH=%ROOT%\src&& set DFAT_ENV=development&& set PYTHONDONTWRITEBYTECODE=1&& %PY_CMD% -m uvicorn dfat.app:create_app --factory --host 127.0.0.1 --port 8000"
)

set "SEED_READY=0"
for /l %%i in (1,1,60) do (
    if "!SEED_READY!"=="0" (
        curl -sf http://127.0.0.1:8000/api/v1/health >nul 2>&1
        if not errorlevel 1 set "SEED_READY=1"
        if "!SEED_READY!"=="0" timeout /t 1 /nobreak >nul
    )
)

if "!SEED_READY!"=="1" (
    echo [%TIME%] Seeding development data...
    python scripts\seed_dev_data.py
    if errorlevel 1 (
        echo [%TIME%] Seed data already exists (skipping)
    ) else (
        echo [%TIME%] Development data seeded
        echo.
        echo   Admin:        admin / Admin!Pass#2026
        echo   Investigator: investigator1 / Invest!Pass#2026
        echo   Analyst:      analyst1 / Analyst!Pass#2026
        echo   Viewer:       viewer1 / Viewer!Pass#2026
        echo.
    )
) else (
    echo [%TIME%] WARNING: Could not reach backend for seeding - run seed manually later.
)

taskkill /FI "WINDOWTITLE eq DFAT Seed Backend*" /T /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)
timeout /t 2 /nobreak >nul
goto :after_setup

:subsequent_run
if exist "%ROOT%\venv\Scripts\activate.bat" (
    call "%ROOT%\venv\Scripts\activate.bat"
    echo [%TIME%] Using existing environment
) else (
    echo WARNING: venv not found - using system Python.
)

:: Ensure required auth package is present (older installs used .[dev] only)
python -c "import jose" >nul 2>&1
if errorlevel 1 (
    echo [%TIME%] Missing auth dependencies - installing...
    python -m pip install -e ".[dev,auth,reporting]" --quiet
    if errorlevel 1 (
        echo ERROR: Could not install required Python packages.
        goto :fail
    )
    echo [%TIME%] Dependencies updated
)

:after_setup
:: ---------------------------------------------------------------------------
:: Port availability
:: ---------------------------------------------------------------------------
netstat -ano 2>nul | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo WARNING: Port 8000 already in use. Backend may not start.
)
netstat -ano 2>nul | findstr ":3000" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo WARNING: Port 3000 already in use. Frontend may not start.
)

:: ---------------------------------------------------------------------------
:: Ollama (optional)
:: ---------------------------------------------------------------------------
curl -sf http://127.0.0.1:11434/api/version >nul 2>&1
if not errorlevel 1 (
    echo [OK] Ollama detected - AI features enabled
) else (
    echo [INFO] Ollama not detected - AI will use rule-based fallback.
    echo        Install from https://ollama.com for full AI features.
)
echo.

:: ---------------------------------------------------------------------------
:: Start backend
:: ---------------------------------------------------------------------------
echo [%TIME%] Starting backend...
if exist "%ROOT%\venv\Scripts\activate.bat" (
    start "DFAT Backend" cmd /k "cd /d ""%ROOT%"" && call ""%ROOT%\venv\Scripts\activate.bat"" && set PYTHONPATH=%ROOT%\src&& set DFAT_ENV=development&& set PYTHONDONTWRITEBYTECODE=1&& python -m uvicorn dfat.app:create_app --factory --host 0.0.0.0 --port 8000 --reload"
) else (
    start "DFAT Backend" cmd /k "cd /d ""%ROOT%"" && set PYTHONPATH=%ROOT%\src&& set DFAT_ENV=development&& set PYTHONDONTWRITEBYTECODE=1&& %PY_CMD% -m uvicorn dfat.app:create_app --factory --host 0.0.0.0 --port 8000 --reload"
)
echo Backend starting on http://localhost:8000

:: ---------------------------------------------------------------------------
:: Wait for backend health
:: ---------------------------------------------------------------------------
set "HEALTH_OK=0"
for /l %%i in (1,1,30) do (
    if "!HEALTH_OK!"=="0" (
        curl -sf http://127.0.0.1:8000/api/v1/health >nul 2>&1
        if not errorlevel 1 set "HEALTH_OK=1"
        if "!HEALTH_OK!"=="0" timeout /t 1 /nobreak >nul
    )
)
if "!HEALTH_OK!"=="1" (
    echo [OK] Backend is healthy
) else (
    echo WARNING: Backend health check timed out.
    echo Check the DFAT Backend console window for errors.
)

:: ---------------------------------------------------------------------------
:: Start frontend
:: ---------------------------------------------------------------------------
echo [%TIME%] Starting frontend...
start "DFAT Frontend" cmd /k "cd /d ""%ROOT%\frontend"" && set BROWSER=none&& npm start"
echo Frontend starting on http://localhost:3000

:: ---------------------------------------------------------------------------
:: Open browser after compile wait
:: ---------------------------------------------------------------------------
timeout /t 5 /nobreak >nul
if exist "%ROOT%\venv\Scripts\python.exe" (
    "%ROOT%\venv\Scripts\python.exe" "%ROOT%\scripts\open_browser.py" --url http://localhost:3000 --health-url http://localhost:8000/api/v1/health --timeout 60
) else (
    "%PY_CMD%" "%ROOT%\scripts\open_browser.py" --url http://localhost:3000 --health-url http://localhost:8000/api/v1/health --timeout 60
)

echo.
echo ================================================================
echo   DFAT is running!
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo   Health:    http://localhost:8000/api/v1/health
echo.
echo   Login with: admin / Admin!Pass#2026
echo.
echo   To stop: close this window or run stop.bat
echo ================================================================
echo.
goto :end

:fail
echo.
echo Launcher stopped due to an error.
echo.

:end
echo Press any key to close this window...
pause >nul
endlocal
exit /b 0
