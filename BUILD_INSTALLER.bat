@echo off
call "%~dp0scripts\BUILD_INSTALLER.bat" %*
exit /b %errorlevel%
