@echo off
rem ============================================================
rem  Nasolt Vault - builds the Setup installer (double-click this file)
rem  Result:  packaging\windows\artifacts\installer\Nasolt_Vault_Setup_2.0.0.exe
rem ============================================================
setlocal
cd /d "%~dp0..\.."
echo.
echo === Nasolt Vault: building the installer ===
echo.

rem Step 1: always rebuild so the installer cannot package a stale executable.
echo Step 1 of 3: building the program first ...
call "%~dp0BUILD_WINDOWS.bat" nopause
if errorlevel 1 goto fail
:have_exe
if not exist "packaging\windows\artifacts\dist\Nasolt Vault.exe" goto fail

rem Step 2: find the locally installed NSIS compiler.
echo.
echo Step 2 of 3: looking for NSIS (the free installer builder) ...
call :find_nsis
if defined MAKENSIS goto have_nsis
echo.
echo NSIS was not found. Install a reviewed NSIS version, then run this file again.
goto fail

:have_nsis
echo Found: %MAKENSIS%

rem Step 3: compile the installer
echo.
echo Step 3 of 3: building the installer ...
if not exist "packaging\windows\artifacts\installer" mkdir "packaging\windows\artifacts\installer"
pushd packaging\windows
"%MAKENSIS%" /V2 NasoltVault.nsi
set "RC=%errorlevel%"
popd
if not "%RC%"=="0" goto fail
if not exist "packaging\windows\artifacts\installer\Nasolt_Vault_Setup_2.0.0.exe" goto fail

echo.
echo ============================================================
echo  DONE.  Your installer is:
echo  %CD%\packaging\windows\artifacts\installer\Nasolt_Vault_Setup_2.0.0.exe
echo ============================================================
echo  This local installer is unverified and must not be distributed.
pause
exit /b 0

:find_nsis
set "MAKENSIS="
set "C1=%ProgramFiles(x86)%\NSIS\makensis.exe"
set "C2=%ProgramFiles%\NSIS\makensis.exe"
set "C3=%LOCALAPPDATA%\Programs\NSIS\makensis.exe"
if exist "%C1%" set "MAKENSIS=%C1%"
if exist "%C2%" set "MAKENSIS=%C2%"
if exist "%C3%" set "MAKENSIS=%C3%"
exit /b 0

:fail
echo.
echo The installer was NOT built - read the message above this line.
pause
exit /b 1
