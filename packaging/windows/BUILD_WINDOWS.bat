@echo off
rem ============================================================
rem  Nasolt Vault - one-click build (double-click this file)
rem ============================================================
setlocal
cd /d "%~dp0..\.."
set "NOPAUSE="
if /i "%~1"=="nopause" set "NOPAUSE=1"

echo.
echo === Nasolt Vault: building the Windows program ===
echo.

set "PY="
py -3.12 --version >nul 2>nul && set "PY=py -3.12"
if not defined PY ( python --version >nul 2>nul && set "PY=python" )
if not defined PY goto nopython

%PY% -c "import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)"
if errorlevel 1 goto oldpython

echo Using this Python:
%PY% -c "import sys; print('  ' + sys.executable + '   (version ' + sys.version.split()[0] + ')')"
echo.

rem Keep build dependencies separate from the developer environment.
if not exist "packaging\windows\.venv-build\Scripts\python.exe" %PY% -m venv "packaging\windows\.venv-build"
if errorlevel 1 goto venvfail

set "BUILD_PY=packaging\windows\.venv-build\Scripts\python.exe"
"%BUILD_PY%" -m pip install -r "packaging\requirements.txt" -r "packaging\requirements-build.txt"
if errorlevel 1 goto pipfail

"%BUILD_PY%" -c "import customtkinter, PIL, cryptography, argon2, pyperclip, PyInstaller; print('All libraries installed OK')"
if errorlevel 1 goto pipfail

"%BUILD_PY%" "packaging\windows\build.py"
if errorlevel 1 goto buildfail

echo.
echo Done!  Local, unverified program: %CD%\packaging\windows\artifacts\dist\Nasolt Vault.exe
goto end

:nopython
echo Python was not found. Install Python 3.12 from https://www.python.org/downloads/
echo On the first installer screen, tick "Add python.exe to PATH", then run this file again.
goto fail
:oldpython
echo This build requires Python 3.12 from https://www.python.org/downloads/
goto fail
:venvfail
echo Could not create the private environment.
goto fail
:pipfail
echo Installing the libraries failed.  Check your internet connection, then run this file again.
goto fail
:buildfail
echo.
echo The build failed - scroll up and read the message above this line.
goto fail

:fail
echo.
if not defined NOPAUSE pause
exit /b 1

:end
if not defined NOPAUSE pause
exit /b 0
