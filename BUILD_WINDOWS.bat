@echo off
rem ============================================================
rem  Nasolt Vault - one-click build (double-click this file)
rem ============================================================
setlocal
cd /d "%~dp0"
set "NOPAUSE="
if /i "%~1"=="nopause" set "NOPAUSE=1"

echo.
echo === Nasolt Vault: building the Windows program ===
echo.

set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY ( python --version >nul 2>nul && set "PY=python" )
if not defined PY goto nopython

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto oldpython

echo Using this Python:
%PY% -c "import sys; print('  ' + sys.executable + '   (version ' + sys.version.split()[0] + ')')"
echo.

rem Always start from a fresh private environment, so an old or half-installed one is never reused.
if exist ".venv" rmdir /s /q ".venv"
%PY% -m venv .venv
if errorlevel 1 goto venvfail

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto pipfail

python -c "import customtkinter, PIL, cryptography, argon2, pyperclip; print('All libraries installed OK')"
if errorlevel 1 goto pipfail

python build.py
if errorlevel 1 goto buildfail

echo.
echo Done!  Your program is:  %~dp0dist\Nasolt Vault.exe
if not defined NOPAUSE explorer "%~dp0dist"
goto end

:nopython
echo Python was not found.  Install Python 3.10 or newer from https://www.python.org/downloads/
echo On the first installer screen, tick "Add python.exe to PATH", then run this file again.
goto fail
:oldpython
echo Your Python is too old.  Install Python 3.10 or newer from https://www.python.org/downloads/
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
