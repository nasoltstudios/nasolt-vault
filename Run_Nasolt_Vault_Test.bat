@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Nasolt Vault - Safe Test Mode

rem Always run from the folder containing this launcher.
cd /d "%~dp0"
if errorlevel 1 goto :folder_error

if not exist "main.py" goto :wrong_folder
if not exist "requirements.txt" goto :wrong_folder

set "TEST_PYTHON=%~dp0.venv-test\Scripts\python.exe"
if exist "%TEST_PYTHON%" goto :environment_ready

rem Create the environment with Python 3.12. The py launcher is not present
rem or discoverable on every Windows installation.
py -3.12 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if not errorlevel 1 goto :create_with_py
python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if not errorlevel 1 goto :create_with_python
goto :python_missing

:create_with_py
echo Creating a local Python test environment for this project...
py -3.12 -m venv ".venv-test"
if errorlevel 1 goto :setup_error
goto :environment_ready

:create_with_python
echo Creating a local Python test environment for this project...
python -m venv ".venv-test"
if errorlevel 1 goto :setup_error

:environment_ready
"%TEST_PYTHON%" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if errorlevel 1 goto :setup_error

if not exist ".venv-test\.nasolt_setup_done" (
    echo Installing the required Python packages ^(first launch only^)...
    "%TEST_PYTHON%" -m pip install -r "requirements.txt"
    if errorlevel 1 goto :setup_error
    type nul > ".venv-test\.nasolt_setup_done"
)

rem Force a separate, persistent data folder. Never use the user's regular vault.
rem NASOLT_TEST_DATA_DIR is an optional override for disposable launcher checks.
if not defined NASOLT_TEST_DATA_DIR set "NASOLT_TEST_DATA_DIR=%LOCALAPPDATA%\Nasolt Vault Test Data"
set "NASOLT_DATA_DIR=%NASOLT_TEST_DATA_DIR%"
if not exist "%NASOLT_DATA_DIR%" mkdir "%NASOLT_DATA_DIR%"
if errorlevel 1 goto :data_error

cls
echo =======================================================
echo                  NASOLT VAULT TEST MODE
echo =======================================================
echo This uses separate TEST storage, NOT your personal vault.
echo Use ONLY fictional passwords and recovery methods.
echo.
echo Test storage: "%NASOLT_DATA_DIR%"
echo.
echo Launching Nasolt Vault...
echo.
"%TEST_PYTHON%" -u "main.py"
if errorlevel 1 goto :app_error

echo.
echo Nasolt Vault closed. Your test data is saved for next time.
pause
exit /b 0

:wrong_folder
echo ERROR: Put this BAT file in the same folder as main.py and requirements.txt.
goto :failed
:python_missing
echo ERROR: Python 3.12 was not found.
echo Install Python 3.12 and ensure python.exe or py.exe can be run.
goto :failed
:folder_error
echo ERROR: Could not open the application folder.
goto :failed
:setup_error
echo ERROR: Environment setup failed. Check the error shown above.
echo The first setup requires internet access to install Python packages.
goto :failed
:data_error
echo ERROR: Could not create the separate test-data folder.
goto :failed
:app_error
echo ERROR: Nasolt Vault exited during startup or use.
echo Review the error type and code location above and the local test-data log.
echo Never share a vault, password, or unreviewed log.
goto :failed
:failed
pause
exit /b 1
