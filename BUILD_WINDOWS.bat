@echo off
call "%~dp0scripts\BUILD_WINDOWS.bat" %*
exit /b %errorlevel%
