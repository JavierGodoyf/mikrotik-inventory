# Instalador nativo para Windows (PowerShell 5.1+).
# Para Docker no hace falta: usa docker compose.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$candidates = @(
    @{ Exe = "py";      Args = @("-3.12") },
    @{ Exe = "py";      Args = @("-3") },
    @{ Exe = "python";  Args = @() },
    @{ Exe = "python3"; Args = @() }
)

$chosen = $null
$version = $null
foreach ($c in $candidates) {
    if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
    $probe = @()
    $probe += $c.Args
    $probe += @("-c", "import sys; print('%d.%d' % sys.version_info[:2])")
    $version = (& $c.Exe @probe 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $version) { continue }
    $parts = $version.Trim().Split(".")
    if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 10)) {
        $chosen = $c
        break
    }
}

if (-not $chosen) {
    Write-Error "No encuentro Python 3.10 o superior. Instalalo desde https://python.org"
    exit 1
}
Write-Host "Usando Python $version"

$venv = @()
$venv += $chosen.Args
$venv += @("-m", "venv", ".venv")
& $chosen.Exe @venv
if ($LASTEXITCODE -ne 0) { exit 1 }

& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -e .
if ($LASTEXITCODE -ne 0) { exit 1 }

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
New-Item -ItemType Directory -Force -Path "data" | Out-Null
& .\.venv\Scripts\python.exe -c "from app.db import init_db; init_db()"

Write-Host ""
Write-Host "Instalado. Arranca el panel con: .\run.ps1"
Write-Host "CLI: .\.venv\Scripts\mikrotik-inventory.exe --help"
