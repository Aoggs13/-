@echo off
if not exist "%~dp0Optimize.ps1" (
  echo Optimize.ps1 tabylmady. ZIP-ti aldymen ash: ong batyrma - Extract All, sodan keyin qaita bas.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Optimize.ps1"
