@echo off
if not exist "%~dp0Restore.ps1" (
  echo Restore.ps1 tabylmady. ZIP-ti aldymen ash: ong batyrma - Extract All, sodan keyin qaita bas.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Restore.ps1"
