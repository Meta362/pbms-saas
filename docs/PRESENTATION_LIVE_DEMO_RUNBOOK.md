# PBMS SaaS — Live Demo Runbook (Official Presentation Manual)
**Document Version:** 1.0.0  
**Target Presentation Date:** Friday, 6 November 2026  
**Audience:** Technical Evaluation Committee, SaaS Stakeholders, Academic/Industry Reviewers  
**Author:** PBMS SaaS Core Engineering Team  

---

## 1. Executive Summary & Objective

This runbook provides a **repeatable, bulletproof, zero-internet-dependent** procedure for conducting a **7 to 10-minute live demonstration** of the **Printing Business Management System (PBMS) SaaS** platform.

PBMS SaaS is a multi-tenant B2B ERP platform engineered specifically for printing and packaging businesses in Cambodia and Southeast Asia. The architecture consists of:
- **Shared Authoritative Backend:** Django 5.2 LTS REST Framework + PostgreSQL 18.
- **Frontend A (Super Admin Portal):** Platform operations, tenant governance, and system broadcasting (`http://localhost:4201`).
- **Frontend B (Tenant Workspace):** Printing operations, smart estimation, production Kanban, inventory ledger, and GDT/NBC tax/payment compliance (`http://localhost:4202`).
- **Frontend C (Public Landing Site):** Bilingual SaaS marketing, plan selection, and self-service registration (`http://localhost:4200`).

---

## 2. Machine & Software Prerequisites

The presentation runs **100% locally on Windows** without requiring external internet or third-party cloud services:

| Component | Verified Requirement | Installed & Verified |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11 64-bit | Yes |
| **Node.js** | Node.js `>= 20` (Verified on `v22.22.3`) | Yes |
| **NPM** | NPM `>= 10` (Verified on `11.4.1`) | Yes |
| **Python** | Python `>= 3.12` (Verified on `3.13.2`) with virtual environment at `backend/.venv` | Yes |
| **Database** | PostgreSQL 16/18 running locally on port `5432` (`postgresql-x64-18` service) | Yes (Running) |
| **Web Browser** | Google Chrome or Microsoft Edge (Incognito / InPrivate profile recommended) | Yes |

---

## 3. Pre-Demo Environment & Database Checklist (T - 15 Minutes)

Run the following checks in PowerShell before the presentation starts:

### Step 3.1: Verify PostgreSQL Service
```powershell
Get-Service -Name *postgres*
```
*Expected Output:* `Status: Running` for `postgresql-x64-18`.

### Step 3.2: Verify Configuration & Apply Pending Migrations
```powershell
cd C:\Projects\pbms-saas\backend
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate
```
*Expected Output:* `System check identified no issues (0 silenced).` and `No migrations to apply.`

### Step 3.3: Seed Pristine Demo Accounts and Operations Data
```powershell
.\.venv\Scripts\python.exe manage.py seed_pbms_demo
```
*Expected Output:*
```text
Successfully seeded PBMS demo data (Super Admin, Angkor Printing House, Mekong Offset Press).
```

### Step 3.4: Verify Port Availability
Ensure ports 8000, 4200, 4201, and 4202 are not occupied by stale background processes:
```powershell
Get-NetTCPConnection -LocalPort 8000,4200,4201,4202 -ErrorAction SilentlyContinue
```
*(If occupied, restart PowerShell or terminate the lingering Node/Python PID).*

---

## 4. Launching the Platform

### Single Command Launch (Recommended)
Open a new PowerShell terminal at the repository root and run:
```powershell
cd C:\Projects\pbms-saas
.\ops\start_all_services.ps1
```
This automatically launches **4 distinct background windows**:
1. **Django REST Backend API:** `http://localhost:8000/api/v1/` (Swagger docs at `/api/docs/`)
2. **Frontend C (Public Landing Site):** `http://localhost:4200`
3. **Frontend A (Super Admin Portal):** `http://localhost:4201`
4. **Frontend B (Tenant Workspace):** `http://localhost:4202`

### Browser Setup
Open your browser in **Incognito Mode** (`Ctrl + Shift + N`) and arrange 3 tabs side-by-side:
- **Tab 1:** `http://localhost:4200` (Public Marketing & Signup)
- **Tab 2:** `http://localhost:4201` (Super Admin Governance)
- **Tab 3:** `http://localhost:4202` (Tenant Printing Operations)

---

## 5. Demo Accounts Cheat Sheet

| Role | Portal | Email | Password | Key Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **Super Admin** | `http://localhost:4201` | `admin@pbms.local` | `Password-2026!` | Tenant review, plan reconciliations, impersonation, global broadcasts |
| **Tenant Owner** | `http://localhost:4202` | `owner@angkorprint.com` | `Password-2026!` | Multi-item quotes, order conversion, inventory ledger, KHQR, GDT reports |
| **Prospective Tenant** | `http://localhost:4200` | Any test email | Any test password | Self-service registration & plan checkout |

*(Note: Quick Demo 1-click buttons are built into both the Super Admin and Tenant Workspace login screens for rapid, typo-free presentation access).*

---

## 6. Minute-by-Minute Live Demo Script (Total: 8 Minutes)

### Phase 1: SaaS Value Proposition & Public Self-Service (0:00 - 1:30)
- **Action:** Go to `http://localhost:4200`.
- **Showcase:**
  - Modern Khmer/English typography and restrained Light Glassmorphism UI.
  - Dual-currency subscription tiers tailored for Cambodia (Solo, Starter, Growth).
  - Language toggle (Khmer / English) in top navigation.
  - Click **ចុះឈ្មោះអាជីវកម្ម (Register Business)**: Enter business name `Banteay Srei Press`, select Starter Plan, and submit with ABA reference `ABA-LIVE-DEMO-01`.
- **Talking Points (Khmer/English):**
  > "PBMS គឺជាប្រព័ន្ធ SaaS B2B ដំបូងបង្អស់នៅកម្ពុជា ដែលរចនាឡើងផ្តោតលើតម្រូវការជាក់ស្តែងរបស់រោងពុម្ព។ អតិថិជនអាចចុះឈ្មោះដោយស្វ័យប្រវត្តិតាមរយៈ Public Site ជ្រើសរើសគម្រោងជាប្រាក់ដុល្លារ ឬប្រាក់រៀល និងទូទាត់តាម KHQR/ABA។"

### Phase 2: Super Admin Governance & Platform Impersonation (1:30 - 3:00)
- **Action:** Switch to `http://localhost:4201`.
- **Showcase:**
  - Click **Quick Demo (Admin)** button to sign in as `admin@pbms.local`.
  - Review Platform Dashboard: Total Tenants, MRR, Platform Health (`PostgreSQL 18 Connected`, `Health Status: OK`).
  - View **Tenant Directory**: See the newly registered `Banteay Srei Press` in `PENDING_REVIEW` and approve payment.
  - Demonstrate **Platform Impersonation (Support Mode)** on `Angkor Printing House`:
    - Click **Support Impersonation**.
    - Automatically opens `http://localhost:4202/?impersonation=...` in a new tab with an amber Support Mode banner.
- **Talking Points (Khmer/English):**
  > "Super Admin មាន Dashboard ត្រួតពិនិត្យ Tenant ទាំងអស់ ទូទាត់ការបង់ប្រាក់ Subscription និងមានមុខងារ Support Impersonation ដែលអនុញ្ញាតឱ្យក្រុមការងារបច្ចេកទេសចូលជួយដោះស្រាយបញ្ហារបស់រោងពុម្ពបានភ្លាមៗដោយមាន Audit Log ពេញលេញ។"

### Phase 3: Printing Operations & Smart Estimating (3:00 - 5:00)
- **Action:** Switch to `http://localhost:4202` (sign in as `owner@angkorprint.com` using Quick Demo button).
- **Showcase:**
  - **Tab 2 (Quotations & Pricing):**
    - Show Multi-Item Quotation Builder (`QT-0001` for Brown Aroma Cafe).
    - Add Line 1: `Name Cards 350gsm` (Quantity: 1,000, Laminate: Matt, Foil: Gold).
    - Add Line 2: `Menu Flyers A4` (Quantity: 500).
    - Observe automatic real-time calculation: Subtotal USD, Exchange Rate (4,100 KHR), VAT 10%, Total USD & KHR.
  - Click **បំប្លែងទៅជាការបញ្ជាទិញ (Convert to Order & Jobs)**:
    - Atomically converts Quotation -> Sales Order (`SO-0001`), Customer Invoice (`INV-0001`), and Production Work Job (`JOB-0001`).
- **Talking Points (Khmer/English):**
  > "ផ្នែកលក់ និងការគណនាតម្លៃ (Estimating) គាំទ្រ Multi-item line items ជាមួយ finishing costs ច្បាស់លាស់។ ដោយចុចត្រឹមមួយ click សម្រង់តម្លៃនឹងត្រូវបំប្លែងដោយស្វ័យប្រវត្តិទៅជា Sales Order, Work Job និង Invoice ក្នុងពេលតែមួយ។"

### Phase 4: Production Kanban & Inventory Non-Negative Ledger (5:00 - 6:30)
- **Action:** Navigate to **Tab 3 (Sales Orders & Production)** and **Tab 4 (Materials)**.
- **Showcase:**
  - Interactive **6-Stage Production Kanban Board**:
    - `PENDING` -> `PRE_PRESS` -> `PRINTING` -> `FINISHING` -> `QUALITY_CHECK` -> `COMPLETED`.
    - Drag card `JOB-0001` from `PENDING` to `PRE_PRESS` and then to `PRINTING`.
  - **Tab 4 (Materials):**
    - Show paper stock ledger (`Art Card 300gsm` - 1,500 sheets on hand).
    - Record consumption of 200 sheets for `JOB-0001`.
    - Highlight PostgreSQL database constraint: inventory stock can never go negative.
- **Talking Points (Khmer/English):**
  > "កាតការងារផលិតកម្មត្រូវបានតាមដានតាមរយៈ Kanban Board ដែលអាចអូសទម្លាក់ (Drag and Drop) បានយ៉ាងរលូន។ រាល់ការប្រើប្រាស់ក្រដាសត្រូវបានកត់ត្រាក្នុង Immutable Inventory Ledger ដែលធានាស្តុកមិនអាចអវិជ្ជមាន (Non-negative Stock Constraint)។"

### Phase 5: National Bank of Cambodia Bakong KHQR & GDT Tax Invoice (6:30 - 8:00)
- **Action:** Navigate to **Tab 5 (Invoices)** and **Tab 8 (Tools & Reports)**.
- **Showcase:**
  - Click **KHQR (Bakong)** on Invoice `INV-0001`:
    - Renders official **NBC Bakong EMVCo QR Code** with dynamic CRC16 checksum.
    - Toggle between USD and KHR. Show deep link button and copy payload button.
  - Click **GDT Tax Invoice (វិក្កយបត្រអាករ)**:
    - Opens official General Department of Taxation (GDT) format invoice with VATTIN, 10% VAT breakdown, and dual authorized signature blocks ready for browser printing.
  - **Tab 8 (Tools & Reports):**
    - Open **Sheet Imposition Calculator**: Select preset `790 x 1090 mm` press sheet -> `A4` size. Visualizes 2D cut nesting layout and calculates sheet yield with gripper and bleed margins.
    - Export **GDT VAT Sales Journal** to CSV.
- **Talking Points (Khmer/English):**
  > "ដើម្បីស្របតាមច្បាប់ហិរញ្ញវត្ថុកម្ពុជា PBMS គាំទ្រការទូទាត់តាមរយៈ KHQR របស់ធនាគារជាតិនៃកម្ពុជា (NBC) និងការចេញវិក្កយបត្រអាករផ្លូវការរបស់អគ្គនាយកដ្ឋានពន្ធដារ (GDT) ព្រមទាំងការនាំចេញសៀវភៅទិនានុប្បវត្តិលក់ប្រចាំខែ (VAT Sales Journal)។"

---

## 7. Emergency Rollback & Failure Recovery Procedures

| Symptom | Probable Cause | Instant Recovery Action |
| :--- | :--- | :--- |
| **Backend API returns 500 / Network Error** | Python server terminated or unapplied migration | In terminal: run `cd C:\Projects\pbms-saas\backend; .\.venv\Scripts\python.exe manage.py runserver 8000` |
| **Database connection refused** | PostgreSQL service stopped | Run PowerShell as Admin: `Start-Service postgresql-x64-18` |
| **Angular displays blank screen / 401 Unauthorized** | Stale tokens in browser storage | Press `Ctrl + Shift + R` to hard reload, or click **Quick Demo** button to refresh session tokens cleanly |
| **Port occupied error on startup** | Previous Node/Angular process still bound to port | Run: `Get-Process node, python -ErrorAction SilentlyContinue \| Stop-Process -Force` then re-run `.\ops\start_all_services.ps1` |

---

## 8. Presentation Boundaries & Honest Disclosures

During the Q&A session, maintain absolute technical integrity by adhering to verified project truths:

1. **Payment Gateway Integration:**
   - *Truth:* Subscriptions and customer invoices utilize manual wire verification and dynamic **NBC Bakong KHQR** generation. Live automatic webhook settlement callbacks with ABA PayWay require an active commercial merchant contract.
2. **Infrastructure Architecture:**
   - *Truth:* The platform is architected for low-cost, multi-tenant deployment using PostgreSQL row-level tenant isolation, discrete containerized services, and Angular frontend distributions. Heavy multi-cluster Kubernetes orchestration is a Phase 4 milestone.
3. **Imposition Engine:**
   - *Truth:* The imposition calculator is a specialized orthogonal grid nesting solver for commercial paper cutting (A3, A4, A5, Business Cards). It is not an arbitrary polygonal irregular CAD nesting engine.
