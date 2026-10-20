@echo off
rem ============================================================
rem  Nasolt Vault - builds the Setup installer (double-click this file)
rem  Result:  installer\Output\Nasolt_Vault_Setup_2.0.0.exe
rem ============================================================
setlocal
cd /d "%~dp0"
echo.
echo === Nasolt Vault: building the installer ===
echo.

rem Step 1: the program itself (skipped if it is already built)
if exist "dist\Nasolt Vault.exe" goto have_exe
echo Step 1 of 3: building the program first ...
call BUILD_WINDOWS.bat nopause
if errorlevel 1 goto fail
:have_exe
if not exist "dist\Nasolt Vault.exe" goto fail

rem Step 2: find the installer compiler (NSIS), installing it if needed
echo.
echo Step 2 of 3: looking for NSIS (the free installer builder) ...
call :find_nsis
if defined MAKENSIS goto have_nsis
echo NSIS not found - installing it with winget (Windows will ask permission) ...
winget install -e --id NSIS.NSIS --accept-package-agreements --accept-source-agreements
call :find_nsis
if defined MAKENSIS goto have_nsis
echo.
echo Could not install NSIS automatically.
echo Install it by hand from  https://nsis.sourceforge.io/Download  (just click Next), then run this file again.
goto fail

:have_nsis
echo Found: %MAKENSIS%

rem Step 3: compile the installer
echo.
echo Step 3 of 3: building the installer ...
if not exist "installer\Output" mkdir "installer\Output"
pushd installer
"%MAKENSIS%" /V2 NasoltVault.nsi
set "RC=%errorlevel%"
popd
if not "%RC%"=="0" goto fail
if not exist "installer\Output\Nasolt_Vault_Setup_2.0.0.exe" goto fail

echo.
echo ============================================================
echo  DONE.  Your installer is:
echo  %~dp0installer\Output\Nasolt_Vault_Setup_2.0.0.exe
echo ============================================================
explorer "%~dp0installer\Output"
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
