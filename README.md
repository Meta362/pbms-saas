# Printing Business Management System (PBMS) — Multi-Tenant SaaS

Production-oriented B2B Printing Business Management System SaaS built with **Three Independent Angular + Tailwind CSS Frontends** and **One Shared Authoritative Django REST Framework + PostgreSQL Backend API**.

---

## 1. Architecture & Applications Overview

| Application | Path | Local Port | Purpose |
| :--- | :--- | :--- | :--- |
| **Shared Backend API** | `backend/` | `8000` | Django 5.2 + DRF + PostgreSQL 18 API (`/api/v1/`, Swagger: `/api/docs/`) |
| **Frontend C (Public Site)** | `frontend/projects/public-site` | `4200` | Marketing, subscription plan comparison, and idempotent tenant registration |
| **Frontend A (Super Admin)** | `frontend/projects/super-admin` | `4201` | Platform KPIs, tenant review, payment reconciliation, and immutable audit logs |
| **Frontend B (Tenant Workspace)**| `frontend/projects/tenant-workspace` | `4202` | Printing business operations: Customers, Quotations, Orders, Production Jobs, Stock Ledger, Invoices |
| **Shared Frontend Library** | `frontend/projects/pbms-shared` | N/A | Shared TypeScript contracts, JWT session/refresh client, `X-Tenant-ID` headers, and Khmer/English i18n |

---

## 2. Core Security & Domain Invariants (DO NOT BYPASS WHEN UPSCALING)

1. **Password Hashing:** `Argon2id` (`Argon2PasswordHasher`) is mandatory (`REQ-AUTH-01`).
2. **Session & JWT Rotation:** Access tokens (15m) and Rotating Refresh tokens (7d) are backed by PostgreSQL `accounts_authsession`. Reusing a rotated refresh token immediately revokes the entire session family (`REQ-AUTH-02`, `REQ-AUTH-03`, `REQ-AUTH-04`).
3. **Strict Multi-Tenant Isolation:** Tenant endpoints in `Frontend B` require `HasActiveTenantMembership` which resolves `request.tenant` strictly from the `X-Tenant-ID` header validated against `tenants_tenantmembership` in PostgreSQL (`REQ-RBAC-02`, `REQ-RBAC-03`).
4. **Financial & Inventory Integrity:**
   - All monetary fields use fixed-point `Decimal` (`USD` 2 decimals, `KHR` rounded to nearest `100` Riel).
   - Material stock (`operations_material.current_stock`) MUST only be mutated through `record_inventory_movement()` which writes an immutable `InventoryTransaction` ledger entry and prevents negative stock.

---

## 3. Quick Start (Windows PowerShell)

### Start All 4 Services
```powershell
powershell -ExecutionPolicy Bypass -File .\ops\start_all_services.ps1
Demo Credentials (Seeded via python manage.py seed_pbms_demo)
Super Admin Portal (http://localhost:4201):
Email: admin@pbms.local
Password: Admin@PBMS2026
Tenant Workspace (http://localhost:4202 — Angkor Printing House):
Email: owner@angkorprint.com
Password: Owner@PBMS2026
Run Backend Tests (PostgreSQL)
code
Powershell
Set-Location backend
.\.venv\Scripts\python.exe manage.py test apps.core apps.accounts apps.subscriptions apps.operations -v 2
Build All 3 Frontends
code
Powershell
Set-Location frontend
npm run build:all
Run Encrypted Backup & Restore Verification Drill
code
Powershell
powershell -ExecutionPolicy Bypass -File .\ops\backup_postgres.ps1
powershell -ExecutionPolicy Bypass -File .\ops\verify_restore.ps1
4. Canonical Engineering Documentation (docs/)
docs/PROJECT_BIBLE.md — Vision, terminology, and locked architectural decisions.
docs/REQUIREMENTS.md — Functional and non-functional requirements catalog.
docs/ARCHITECTURE.md — System topology and tenant resolution flow.
docs/DATABASE.md — PostgreSQL schema, constraints, and ledger rules.
docs/RBAC.md — Platform vs. Tenant role matrix.
docs/SECURITY.md — Threat controls, Argon2id, and token reuse detection.
docs/API_CONTRACT.md — REST API endpoint catalog.
docs/BACKUP.md — AES-256 backup and restore verification specification.
docs/TESTING.md — Executed test catalog and verification evidence.
