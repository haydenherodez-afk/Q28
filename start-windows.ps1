# HericR — zagon na Windows BREZ Dockerja (SQLite baza + dokumenti na disku).
# Potrebuješ: Python 3.11+ (python.org) in Node.js 22+ (nodejs.org).
# Zagon:  v PowerShellu v mapi projekta:   powershell -ExecutionPolicy Bypass -File .\start-windows.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python ni nameščen: https://www.python.org/downloads/ (obkljukaj 'Add to PATH')" }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js ni nameščen: https://nodejs.org/" }

if (-not (Test-Path ".env")) {
    $secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
    "HERICR_SECRET_KEY=$secret`nHERICR_ANTHROPIC_API_KEY=`n" | Out-File -Encoding utf8 ".env"
    Write-Host "Ustvarjena .env (dodaj HERICR_ANTHROPIC_API_KEY za AI funkcije)." -ForegroundColor Yellow
}
Get-Content ".env" | Where-Object { $_ -match "^\s*HERICR_[A-Z_]+=" } | ForEach-Object {
    $k, $v = $_ -split "=", 2; [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), "Process")
}

Write-Host "== Backend ==" -ForegroundColor Cyan
Set-Location "$root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q -r requirements.txt
$env:HERICR_DATABASE_URL = "sqlite:///./data/hericr.db"
$env:HERICR_STORAGE_DIR = "./data/files"
Start-Process -WindowStyle Minimized -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--port","8000"

Write-Host "== Frontend ==" -ForegroundColor Cyan
Set-Location "$root\frontend"
npm ci --no-audit --no-fund
npm run build
$env:HERICR_API_URL = "http://localhost:8000"
Start-Process "http://localhost:3000"
npm run start
