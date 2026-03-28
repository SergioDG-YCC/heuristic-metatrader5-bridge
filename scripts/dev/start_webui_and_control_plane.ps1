# Development startup helper (optional)
# This script starts both the Python backend and the Vite frontend.
# The canonical backend command remains: .venv\Scripts\python.exe apps/control_plane.py
# This script is a CONVENIENCE ONLY. Do not replace the canonical backend startup.

$repo = Split-Path $MyInvocation.MyCommand.Path -Parent
$repo = Split-Path $repo -Parent  # go up from scripts/dev/ to repo root
Set-Location $repo

Write-Host "=== Heuristic MT5 Bridge — Dev Startup ===" -ForegroundColor Cyan
Write-Host "Backend : .venv\Scripts\python.exe apps/control_plane.py" -ForegroundColor Gray
Write-Host "Frontend: apps/webui (Vite on port 5173)" -ForegroundColor Gray
Write-Host ""

# Start the backend in a new terminal window
Write-Host "Starting control plane..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$repo'; .\.venv\Scripts\python.exe apps/control_plane.py"

# Wait a moment
Start-Sleep -Seconds 2

# Start the frontend
Write-Host "Starting WebUI dev server..." -ForegroundColor Green
Set-Location "$repo\apps\webui"

# Install dependencies if needed
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing npm dependencies..." -ForegroundColor Yellow
    npm install
}

npm run dev
