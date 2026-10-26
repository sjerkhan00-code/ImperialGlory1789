@echo off
rem Imperial Glory 1789 - removes the mod (ImperialGlory_ModNations.exe, Data2.pak) and restores the backups.
rem -ExecutionPolicy Bypass applies to this one script run only; no system setting is changed.
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Uninstall %*
echo.
pause
