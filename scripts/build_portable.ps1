# Build a copy-to-USB folder at dist\GIT-TechBench-Portable
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$python = Join-Path $PWD ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Create and populate .venv first (pip install -r requirements.txt)."
}

& $python -m pip install -q "pyinstaller>=6.0"
& $python -m PyInstaller --noconfirm --clean techbench.spec

$dest = Join-Path $PWD "dist\GIT-TechBench-Portable"
if (-not (Test-Path $dest)) {
    Write-Error "PyInstaller did not create $dest"
}

$launcher = @"
@echo off
cd /d "%~dp0"
start "" "TechBench.exe"
"@
Set-Content -Path (Join-Path $dest "Launch-TechBench.bat") -Value $launcher -Encoding ASCII

$readme = @"
GIT TechBench — portable USB copy
=================================

No install on the PC. Copy this whole folder to a flash drive and double-click
TechBench.exe (or Launch-TechBench.bat).

This folder keeps:
  config\techbench.ini   technician settings
  database\              session history
  reports\               PDF/JSON and camera captures
  logs\                  app log

Windows may still prompt SmartScreen the first time. That is not an install.
SFC / DISM / Check Disk still need administrator rights on the machine under test.

Do not copy only TechBench.exe — the _internal folder must travel with it.
"@
Set-Content -Path (Join-Path $dest "README.txt") -Value $readme -Encoding UTF8

Write-Host "Portable folder: $dest"
Write-Host "Copy that folder to a USB stick and run TechBench.exe"
