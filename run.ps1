# Arranca el panel en Windows.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:MTIK_BASE_DIR = $PSScriptRoot
& .\.venv\Scripts\mikrotik-panel.exe
