@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "PROJECT_DIR=%CD%"
set "VENV_DIR=%PROJECT_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "BASE_PY="

call :ensure_venv
if errorlevel 1 exit /b 1

call :ensure_dependencies
if errorlevel 1 exit /b 1

echo Checking database...
if not exist "%PROJECT_DIR%\database\app.db" (
    echo Database not found. Initializing...
    "%VENV_PY%" database\init_db.py
    if errorlevel 1 (
        echo Failed to initialize the database.
        exit /b 1
    )
) else (
    echo Database already exists.
)

echo Opening app at http://127.0.0.1:5000
"%VENV_PY%" -c "from app import app; app.run(debug=False, use_reloader=False)"
exit /b %errorlevel%

:ensure_venv
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        echo Using existing virtual environment...
        exit /b 0
    )

    echo Existing virtual environment is broken. Recreating it...
    rmdir /s /q "%VENV_DIR%" >nul 2>&1
)

call :find_python
if errorlevel 1 exit /b 1

echo Creating virtual environment...
call %BASE_PY% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo Failed to create the virtual environment.
    exit /b 1
)

"%VENV_PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo Bootstrapping pip...
    "%VENV_PY%" -m ensurepip --upgrade
    if errorlevel 1 (
        echo Failed to bootstrap pip for the virtual environment.
        exit /b 1
    )
)

exit /b 0

:ensure_dependencies
"%VENV_PY%" -c "import flask, sklearn, openpyxl, sentence_transformers" >nul 2>&1
if not errorlevel 1 (
    echo Dependencies already installed.
    exit /b 0
)

echo Installing dependencies...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    exit /b 1
)

exit /b 0

:find_python
set "BASE_PY="

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "BASE_PY="%LocalAppData%\Programs\Python\Python312\python.exe""
    exit /b 0
)

if exist "%ProgramFiles%\Python312\python.exe" (
    set "BASE_PY="%ProgramFiles%\Python312\python.exe""
    exit /b 0
)

if exist "%ProgramFiles%\Python\Python312\python.exe" (
    set "BASE_PY="%ProgramFiles%\Python\Python312\python.exe""
    exit /b 0
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        set "BASE_PY=py -3.12"
        exit /b 0
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "BASE_PY=python"
        exit /b 0
    )
)

where winget >nul 2>&1
if not errorlevel 1 (
    echo Python 3.12 not found. Installing it with winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo Python 3.12 installation failed.
        exit /b 1
    )

    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
        set "BASE_PY="%LocalAppData%\Programs\Python\Python312\python.exe""
        exit /b 0
    )

    where py >nul 2>&1
    if not errorlevel 1 (
        py -3.12 -c "import sys" >nul 2>&1
        if not errorlevel 1 (
            set "BASE_PY=py -3.12"
            exit /b 0
        )
    )

    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
        if not errorlevel 1 (
            set "BASE_PY=python"
            exit /b 0
        )
    )
)

echo Python 3.12 is required. Install it, then run run.bat again.
exit /b 1
