@echo off
rem Imperial Glory 1789 - starts the offline installer install.ps1 from this folder.
rem -ExecutionPolicy Bypass applies to this one script run only; no system setting is changed.
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
