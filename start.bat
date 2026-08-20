@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1
title DFAT Launcher

cd /d "%~dp0"

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║  DFAT — Digital Forensics Automation Tool                     ║
echo ║  AI-Assisted Evidence Analysis                                ║
echo ║  Starting local development environment...                    ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "PYTHONPATH=%ROOT%\src"
set "DFAT_ENV=development"
set "PYTHONDONTWRITEBYTECODE=1"
set "BROWSER=none"

:: ---------------------------------------------------------------------------
:: Timestamp helper
:: ---------------------------------------------------------------------------
goto :main

:timestamp
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "Get-Date -Format 'HH:mm:ss'"`) do set "TS=%%t"
exit /b 0

:elapsed
set "END_EPOCH="
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"`) do set "END_EPOCH=%%t"
set /a "ELAPSED=!END_EPOCH!-!START_EPOCH!"
exit /b 0

:log
call :timestamp
echo [!TS!] %~1
exit /b 0

:log_done
call :timestamp
call :elapsed
echo [!TS!] %~1 ^(!ELAPSED!s^)
exit /b 0

:: ---------------------------------------------------------------------------
:: Main
:: ---------------------------------------------------------------------------
:main

:: --- Prerequisites: Python 3.11+ ---
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
    pause
    exit /b 1
)
"%PY_CMD%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3.11+ is required. Download from
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

:: --- Prerequisites: Node.js 18+ ---
where node >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js 18+ is required. Download from
    echo https://nodejs.org/
    pause
    exit /b 1
)
node -e "const v=process.version.slice(1).split('.').map(Number); process.exit(v[0]>=18?0:1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js 18+ is required. Download from
    echo https://nodejs.org/
    pause
    exit /b 1
)

:: --- Prerequisites: npm ---
where npm >nul 2>&1
if errorlevel 1 (
    echo ERROR: npm is required. It is normally installed with Node.js.
    echo Download from https://nodejs.org/
    pause
    exit /b 1
)

:: --- First-run detection ---
set "NEED_SETUP=0"
if not exist "%ROOT%\.env" set "NEED_SETUP=1"
if not exist "%ROOT%\frontend\node_modules\" set "NEED_SETUP=1"
if not exist "%ROOT%\data\dfat.db" set "NEED_SETUP=1"

if "!NEED_SETUP!"=="1" (
    call :log "First-run setup detected..."

    if not exist "%ROOT%\.env" (
        if exist "%ROOT%\.env.example" (
            copy /Y "%ROOT%\.env.example" "%ROOT%\.env" >nul
            call :log "Created .env from template"
        ) else (
            echo WARNING: .env.example not found — create .env manually.
        )
    )

    call :log "Creating data directories..."
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
    if not exist "%ROOT%\venv\" (
        call :log "Creating Python virtual environment..."
        for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"`) do set "START_EPOCH=%%t"
        "%PY_CMD%" -m venv "%ROOT%\venv"
        if errorlevel 1 (
            echo WARNING: Could not create venv — installing into system Python.
            set "USE_VENV=0"
        ) else (
            call :log_done "Virtual environment created"
        )
    )

    if "!USE_VENV!"=="1" (
        call "%ROOT%\venv\Scripts\activate.bat"
    )

    call :log "Installing backend dependencies..."
    for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"`) do set "START_EPOCH=%%t"
    if "!USE_VENV!"=="1" (
        python -m pip install -e ".[dev]" --quiet
    ) else (
        python -m pip install -e ".[dev]" --quiet --break-system-packages
    )
    if errorlevel 1 (
        echo ERROR: Backend dependency installation failed.
        pause
        exit /b 1
    )
    call :log_done "Backend dependencies installed"

    call :log "Initialising database..."
    for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"`) do set "START_EPOCH=%%t"
    python -m alembic -c src/dfat/database/migrations/alembic.ini upgrade head
    if errorlevel 1 (
        echo ERROR: Database initialisation failed.
        pause
        exit /b 1
    )
    call :log_done "Database initialised"

    if not exist "%ROOT%\frontend\node_modules\" (
        call :log "Installing frontend dependencies..."
        for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "[int][double]::Parse((Get-Date -UFormat %%s))"`) do set "START_EPOCH=%%t"
        pushd "%ROOT%\frontend"
        call npm install --legacy-peer-deps
        if errorlevel 1 (
            popd
            echo ERROR: Frontend dependency installation failed.
            pause
            exit /b 1
        )
        popd
        call :log_done "Frontend dependencies installed"
    )

    :: Seed requires a running API — start temporary backend
    call :log "Starting temporary backend for seed data..."
    if exist "%ROOT%\venv\Scripts\activate.bat" (
        start "DFAT Seed Backend" /MIN cmd /c "cd /d "%ROOT%" && call venv\Scripts\activate.bat && set PYTHONPATH=%ROOT%\src && set DFAT_ENV=development && set PYTHONDONTWRITEBYTECODE=1 && python -m uvicorn dfat.app:create_app --factory --host 127.0.0.1 --port 8000"
    ) else (
        start "DFAT Seed Backend" /MIN cmd /c "cd /d "%ROOT%" && set PYTHONPATH=%ROOT%\src && set DFAT_ENV=development && set PYTHONDONTWRITEBYTECODE=1 && %PY_CMD% -m uvicorn dfat.app:create_app --factory --host 127.0.0.1 --port 8000"
    )

    set "SEED_READY=0"
    for /l %%i in (1,1,60) do (
        if "!SEED_READY!"=="0" (
            curl -sf http://localhost:8000/api/v1/health >nul 2>&1
            if not errorlevel 1 set "SEED_READY=1"
            if "!SEED_READY!"=="0" timeout /t 1 /nobreak >nul
        )
    )

    if "!SEED_READY!"=="1" (
        call :log "Seeding development data..."
        python scripts/seed_dev_data.py
        if errorlevel 1 (
            call :log "Seed data already exists (skipping)"
        ) else (
            call :log "Development data seeded"
            echo.
            echo   Admin:        admin / Admin!Pass#2026
            echo   Investigator: investigator1 / Invest!Pass#2026
            echo   Analyst:      analyst1 / Analyst!Pass#2026
            echo   Viewer:       viewer1 / Viewer!Pass#2026
            echo.
        )
    ) else (
        call :log "WARNING: Could not reach backend for seeding — run seed manually later."
    )

    :: Stop temporary seed backend
    taskkill /FI "WINDOWTITLE eq DFAT Seed Backend" /T /F >nul 2>&1
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
        taskkill /PID %%p /F >nul 2>&1
    )
    timeout /t 2 /nobreak >nul

) else (
    if exist "%ROOT%\venv\Scripts\activate.bat" (
        call "%ROOT%\venv\Scripts\activate.bat"
        call :log "Using existing environment"
    ) else (
        echo WARNING: venv not found — using system Python.
    )
)

:: --- Port availability ---
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo WARNING: Port 8000 already in use. Backend may not start.
)
netstat -ano | findstr ":3000" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo WARNING: Port 3000 already in use. Frontend may not start.
)

:: --- Ollama (optional) ---
curl -sf http://localhost:11434/api/version >nul 2>&1
if not errorlevel 1 (
    echo [OK] Ollama detected — AI features enabled
) else (
    echo [INFO] Ollama not detected — AI will use rule-based fallback. Install from https://ollama.com for full AI features.
)
echo.

:: --- Start backend ---
call :log "Starting backend..."
if exist "%ROOT%\venv\Scripts\activate.bat" (
    start "DFAT Backend" cmd /k "cd /d "%ROOT%" && call venv\Scripts\activate.bat && set PYTHONPATH=%ROOT%\src && set DFAT_ENV=development && set PYTHONDONTWRITEBYTECODE=1 && python -m uvicorn dfat.app:create_app --factory --host 0.0.0.0 --port 8000 --reload"
) else (
    start "DFAT Backend" cmd /k "cd /d "%ROOT%" && set PYTHONPATH=%ROOT%\src && set DFAT_ENV=development && set PYTHONDONTWRITEBYTECODE=1 && %PY_CMD% -m uvicorn dfat.app:create_app --factory --host 0.0.0.0 --port 8000 --reload"
)
echo Backend starting on http://localhost:8000

:: --- Wait for backend health ---
set "HEALTH_OK=0"
for /l %%i in (1,1,30) do (
    if "!HEALTH_OK!"=="0" (
        curl -sf http://localhost:8000/api/v1/health >nul 2>&1
        if not errorlevel 1 set "HEALTH_OK=1"
        if "!HEALTH_OK!"=="0" timeout /t 1 /nobreak >nul
    )
)
if "!HEALTH_OK!"=="1" (
    echo [OK] Backend is healthy
) else (
    echo WARNING: Backend health check timed out. Check the backend console window for errors.
)

:: --- Start frontend ---
call :log "Starting frontend..."
start "DFAT Frontend" cmd /k "cd /d "%ROOT%\frontend" && set BROWSER=none && npm start"
echo Frontend starting on http://localhost:3000

:: --- Open browser after brief compile wait ---
timeout /t 5 /nobreak >nul
if exist "%ROOT%\venv\Scripts\python.exe" (
    "%ROOT%\venv\Scripts\python.exe" scripts\open_browser.py --url http://localhost:3000 --health-url http://localhost:8000/api/v1/health --timeout 60
) else (
    "%PY_CMD%" scripts\open_browser.py --url http://localhost:3000 --health-url http://localhost:8000/api/v1/health --timeout 60
)

echo.
echo ════════════════════════════════════════════════════════════
echo   DFAT is running!
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo   Health:    http://localhost:8000/api/v1/health
echo.
echo   Login with: admin / Admin!Pass#2026
echo.
echo   To stop: close this window or run stop.bat
echo ════════════════════════════════════════════════════════════
echo.

pause
exit /b 0
