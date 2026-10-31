@echo off
title PBMS SaaS - Startup Launcher
echo ========================================================
echo   PBMS SaaS (Printing Business Management System)
echo ========================================================
echo.

echo [1/2] Starting Backend API Server (Port 8000)...
start "PBMS Backend (Port 8000)" cmd /k "cd /d c:\Projects\pbms-saas && backend\.venv\Scripts\python.exe backend\manage.py runserver 0.0.0.0:8000"

echo [2/2] Starting Frontend Workspaces...
start "PBMS Tenant Workspace (Port 4202)" cmd /k "cd /d c:\Projects\pbms-saas\frontend && npm run start:tenant"
start "PBMS Public Site (Port 4200)" cmd /k "cd /d c:\Projects\pbms-saas\frontend && npm run start:public"
start "PBMS Super Admin (Port 4201)" cmd /k "cd /d c:\Projects\pbms-saas\frontend && npm run start:admin"

echo.
echo ========================================================
echo   All 4 Services are launching!
echo   - Backend API:       http://localhost:8000
echo   - Public Site:       http://localhost:4200
echo   - Super Admin:       http://localhost:4201
echo   - Tenant Workspace:  http://localhost:4202
echo ========================================================
echo.
pause
