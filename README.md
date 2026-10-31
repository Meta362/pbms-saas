# 🖨️ PBMS SaaS — Printing Business Management System (2026 Edition)

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Django](https://img.shields.io/badge/Django-5.2-092E20?logo=django)
![Angular](https://img.shields.io/badge/Angular-19-DD0031?logo=angular)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)
![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.4-38B2AC?logo=tailwind-css)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)
![License](https://img.shields.io/badge/License-Proprietary-red)

A production-grade, multi-tenant B2B Printing SaaS engineered specifically for print houses, commercial offset presses, and digital print shops in Cambodia. Built with **Three Independent Angular 19 Standalone Frontends** and **One Shared Authoritative Django REST Framework + PostgreSQL Backend API**.

---

## 🏗️ 1. Architecture & Port Topology

| Portal / Service | Path | Local Port | Key Capabilities |
| :--- | :--- | :---: | :--- |
| **Shared Backend API** | `backend/` | `8000` | Django 5.2 + DRF + PostgreSQL API (`/api/v1/`, Swagger: `/api/schema/swagger-ui/`) |
| **Frontend C (Public SaaS Site)** | `frontend/projects/public-site` | `4200` | Marketing landing, 4-tier pricing (Solo, Starter, Growth, Enterprise), and onboarding |
| **Frontend A (Super Admin)** | `frontend/projects/super-admin` | `4201` | Platform KPIs, KHQR payment reconciliation, tenant provisioning, and preset seeders |
| **Frontend B (Tenant Workspace)** | `frontend/projects/tenant-workspace` | `4202` | Production Kanban board, multi-item quotes, GDT Tax Invoices, Bakong KHQR, Stock Ledger |
| **Shared Frontend Core** | `frontend/projects/pbms-shared` | N/A | TypeScript contracts, JWT auto-refresh interceptor, `X-Tenant-ID` resolver, Khmer/English i18n |

---

## 🌟 2. Core Printing & Enterprise Capabilities

* **🇰🇭 NBC Bakong KHQR Payment (CAM-001):** Native EMVCo-compliant KHQR dynamic generation in both USD and KHR for instant mobile banking checkout.
* **📜 Dual Tax Regime (GDT VAT 10% vs. Family Shop 0%):**
  * **Family Print Shop (អាជីវកម្មគ្រួសារ):** Locked at 0.00% VAT, outputs General Commercial Cash Receipts.
  * **VAT Registered Enterprise (រោងពុម្ពចុះបញ្ជី):** Official GDT Tax Invoices with VATTIN and monthly VAT Sales Journal (CSV UTF-8 BOM).
* **🎛️ Drag-and-Drop Production Kanban Board:** Real-time job state transitions (`PENDING` ➔ `PRE_PRESS` ➔ `PRINTING` ➔ `FINISHING` ➔ `QC` ➔ `COMPLETED`).
* **📐 Sheet Imposition & Cut Optimizer (PROD-001):** Combinatorial cut calculator for parent sheets (790x1090mm, 650x900mm) with gripper and bleed margins.
* **🛡️ Concurrent Active Session Limiting:** Prevents unauthorized account-sharing on smaller tiers (auto-revokes oldest session when limit exceeded).
* **📦 Double-Entry Stock Ledger:** Immutable PostgreSQL ledger with strict non-negative constraints (`chk_material_stock_non_negative`).

---

## 🚀 3. Quick Start

### ជម្រើសទី ១: Double-Click Launcher (Windows)
គ្រាន់តែចុច **Double-click** លើ file **[`start-pbms.bat`](start-pbms.bat)** នៅក្នុង Root Directory វានឹងបើកដំណើរការ Server ទាំង ៤ ដោយស្វ័យប្រវត្តិ!

### ជម្រើសទី ២: Docker Compose (100% Offline University Demo)
```bash
docker compose up -d
```

### ជម្រើសទី ៣: Manual Local Startup

**Backend Server (Port 8000):**
```powershell
backend\.venv\Scripts\python.exe backend\manage.py seed_pbms_demo
backend\.venv\Scripts\python.exe backend\manage.py runserver 0.0.0.0:8000
```

**Frontend Applications:**
```powershell
Set-Location frontend
npm run start:tenant   # Tenant Workspace on http://localhost:4202
npm run start:public   # Public SaaS Website on http://localhost:4200
npm run start:admin    # Super Admin on http://localhost:4201
```

---

## 🔑 4. Demo Accounts & Credentials

*(Seeded automatically via `python manage.py seed_pbms_demo`)*

| Portal | URL | Email | Password |
| :--- | :--- | :--- | :--- |
| **Tenant Workspace** | [http://localhost:4202](http://localhost:4202) | `owner@angkorprint.com` | `Password-2026!` |
| **Super Admin Console** | [http://localhost:4201](http://localhost:4201) | `admin@pbms.local` | `Password-2026!` |
| **Public Landing** | [http://localhost:4200](http://localhost:4200) | *(Public Access)* | *(No auth required)* |

> ⚡ **Tip:** ផ្ទាំង Login ទាំងសងខាងមានប៊ូតុង **"1-Click Instant Demo Login"** គ្រាន់តែចុចលើឈ្មោះគណនីគឺ Login ចូលភ្លាមៗដោយពុំបាច់វាយពាក្យសម្ងាត់ឡើយ!

---

## 🧪 5. Testing & Verification

### Run Backend PostgreSQL Test Suite (73 Tests)
```powershell
backend\.venv\Scripts\python.exe backend\manage.py test apps.core apps.accounts apps.subscriptions apps.operations apps.tenants
```

### Run Frontend Unit & Regression Suite (44 Tests)
```powershell
Set-Location frontend
npm run test
```

### Build All 3 Production Bundles
```powershell
Set-Location frontend
npm run build:all
```

---

## 📚 6. Engineering Documentation (`docs/`)

* [docs/DEPLOYMENT_GUIDE_FREE.md](docs/DEPLOYMENT_GUIDE_FREE.md) — ការណែនាំ Deploy លើ Cloud ចំណាយ $0 (Neon + Render + Vercel) & Google Cloud Credit $10
* [docs/CURRENT_SYSTEM_CAPABILITIES_KM.md](docs/CURRENT_SYSTEM_CAPABILITIES_KM.md) — របាយការណ៍លម្អិតអំពីសមត្ថភាពប្រព័ន្ធទាំងមូលជាភាសាខ្មែរ
* [docs/PROJECT_BIBLE.md](docs/PROJECT_BIBLE.md) — គោលការណ៍ស្ថាបត្យកម្ម និង Invariants
* [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) — បញ្ជីតម្រូវការមុខងារ និងសុវត្ថិភាព
* [docs/DATABASE.md](docs/DATABASE.md) — PostgreSQL Schema, Check Constraints & Stock Ledger
* [docs/SECURITY.md](docs/SECURITY.md) — Argon2id, JWT Rotation, Audit Trails & USB Dongle / TOTP
