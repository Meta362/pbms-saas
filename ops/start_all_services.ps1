Write-Host "Starting PBMS SaaS Shared Backend API & 3 Separate Angular Frontends..." -ForegroundColor Cyan

$rootPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendPath = Join-Path $rootPath "backend"
$frontendPath = Join-Path $rootPath "frontend"

# 1. Start Django Shared Backend API on port 8000
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backendPath'; .\.venv\Scripts\python.exe manage.py runserver 8000"

# 2. Start Frontend C: Public SaaS Website on port 4200
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontendPath'; npm run start:public"

# 3. Start Frontend A: Super Admin Portal on port 4201
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontendPath'; npm run start:admin"

# 4. Start Frontend B: Tenant/Staff Workspace on port 4202
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontendPath'; npm run start:tenant"

Write-Host ""
Write-Host "All 4 services have been launched in separate PowerShell windows:" -ForegroundColor Green
Write-Host "  - Shared Backend API & Swagger Docs : http://localhost:8000/api/docs/"
Write-Host "  - Frontend C (Public SaaS Website)  : http://localhost:4200"
Write-Host "  - Frontend A (Super Admin Portal)   : http://localhost:4201"
Write-Host "  - Frontend B (Tenant Workspace)     : http://localhost:4202"
