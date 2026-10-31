# PBMS SaaS — Feature & Module Master Matrix

> **Target Standard:** Production-Grade Enterprise Printing SaaS (Exceeding Original Baseline Requirements)  
> **Benchmarked Against:** Modern Printing MIS/ERP (PrintSmith Vision, EFI Pace, Gelato, PrintNode, Katana Cloud Manufacturing) and Enterprise SaaS Management.  
> **Cambodia Context:** Dual-Currency (USD / KHR), National Bank of Cambodia (NBC) Bakong KHQR, General Department of Taxation (GDT) compliant invoicing, Khmer Unicode typography.

---

## Legend & Status Definitions

- **`Existing`**: Fully implemented in code, covered by tests, and working in the active repository.
- **`Incomplete`**: Partially implemented, missing key domain fields, validation rules, or edge-case handling.
- **`Missing`**: Documented in specifications or expected for a production-grade SaaS, but absent from code.
- **`Security/Quality Gap`**: Implementation exists but contains a confirmed defect, bypass risk, hardcoded credential, or architectural fragility.
- **`Planned`**: High-value enterprise capability prioritized in the production roadmap.

---

## 1. SaaS Platform Governance & Administration

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **SuperAdmin USB Flash Security Key** | Standard consumer USB Flash Drive configured as a custom cryptographic dongle with signed `license.dat` bound to drive hardware/volume serial. | Cost-effective physical possession factor | `Existing` | **Completed** |
| **SuperAdmin Portal (Frontend A)** | Central management portal for platform operators. | Multi-tenant SaaS Admin | `Incomplete` | Phase 2 |
| **Tenant Onboarding Review Workflow** | Review new business applications (`PENDING_REVIEW -> ACTIVE/REJECTED`). | Enterprise SaaS Compliance | `Existing` | Phase 2 |
| **Tenant Suspension & Offboarding** | Suspend delinquent tenants, automated lockouts, and audited offboarding. | Strict Data Quarantine | `Incomplete` | Phase 2 |
| **Platform-Wide Audit Trail** | Immutable log of all administrative actions with actor IP, timestamp, and JSON metadata. | SOC2 / ISO 27001 | `Incomplete` | Phase 2 |
| **Platform Health & Readiness Probes** | Deep health checks verifying PostgreSQL, Redis, disk storage, and external connectivity. | Kubernetes / Cloud Standard | `Existing` | **Completed** |
| **Support Impersonation & Audit** | Audited, time-limited tenant support access without password knowledge or isolation bypass. | SOC2 Compliant Impersonation | `Missing` | Phase 4 |

---

## 2. Identity, Access Management (IAM) & Security

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Argon2id Password Security** | OWASP-recommended memory-hard hashing via `Argon2id` (min 10 chars). | OWASP Top 10 | `Existing` | Verified |
| **Token Family & Refresh Rotation** | Short-lived Access JWTs (15m) + Rotating Refresh JWTs (7d) with reuse revocation. | RFC 6749 / OAuth2 BCP | `Existing` | Verified |
| **JWT Secret Separation (SEC-001)** | Dedicated `JWT_SIGNING_KEY` separate from Django `SECRET_KEY` with production fail-closed validation. | Zero Shared Secrets | `Security/Quality Gap` | **Phase 1A** |
| **Auth Abuse & Rate Limiting (AUTH-001)** | Scoped rate limits on login, token refresh, and registration endpoints. | OWASP Anti-Brute-Force | `Existing` | **Completed** |
| **Global Session Revocation (AUTH-003)** | Revoke all active sessions upon password reset, account lockout, or user request. | NIST SP 800-63B | `Incomplete` | **Phase 1C** |
| **Self-Service Account Recovery (AUTH-002)** | Secure, expiring one-time password reset via email and invite acceptance. | Standard IAM Flow | `Missing` | Phase 2 |
| **Strict Multi-Tenant Isolation** | Server-enforced tenancy via validated `X-Tenant-ID` header; zero cross-tenant IDOR leakage. | Multi-Tenant Architecture | `Existing` | Maintained |
| **Role-Based Access Control (RBAC)** | Platform roles (`SUPER_ADMIN`, `SUPPORT`) separate from Tenant roles (`OWNER`, `MANAGER`, `SALES`, etc.). | Enterprise RBAC | `Incomplete` | Phase 2 |
| **Demo Credential Hygiene (UI-001)** | Removal of hardcoded passwords and demo user credentials from production builds. | OWASP ASVS | `Security/Quality Gap` | **Phase 1A** |

---

## 3. Subscription Management, Billing & Monetization

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Tiered Subscription Plans** | Configurable pricing tiers (Starter, Growth, Enterprise) with monthly/annual billing. | Modern SaaS Pricing | `Existing` | Maintained |
| **Plan Versioning & Entitlements (SAAS-001)**| Immutable plan versions so catalog price changes do not corrupt active subscriptions. | Stripe / Recurly standard | `Missing` | Phase 2 |
| **Atomic Usage Metering** | Enforce staff seat caps and monthly order limits under PostgreSQL row locks. | Usage-based billing | `Incomplete` | Phase 2 |
| **Storage Quota Management** | Disk / Cloud storage quotas per plan tier with automated limit gating. | S3/GCS Tenant Quotas | `Missing` | Phase 3 |
| **Manual Bank / ABA Reconciliation** | SuperAdmin verifies bank wire slips and manual payments with idempotency keys. | Localized Cambodia Banking | `Existing` | Maintained |
| **Bakong KHQR Payment Gateway (OpenAPI)**| Automated NBC Bakong KHQR dynamic QR generation and real-time webhook confirmation. | National Cambodia Payments | `Planned` | Phase 2 |
| **Automated Subscription Lifecycle** | Automated transitions: `ACTIVE -> PAST_DUE -> SUSPENDED` via scheduled jobs. | Billing Lifecycle Engine | `Incomplete` | Phase 2 |

---

## 4. Printing Business ERP: Estimating, Catalog & Quotations

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Product & Service Catalog (PRINT-001)**| Pre-configured printing service templates (Offset, Digital, Large Format, Sublimation). | PrintSmith Vision | `Missing` | Phase 3 |
| **Dynamic Cost & Pricing Formulas** | Formula engine: `Setup Fee + (Unit Rate * Qty) + Finishing + Waste Margin - Discount`. | Printing MIS Estimating | `Incomplete` | Phase 3 |
| **Multi-Line Item Quotations (PRINT-002)** | Quotations with multiple line items, different dimensions, paper stock, and finishing options. | Modern ERP Invoicing | `Missing` | Phase 3 |
| **Quote Number Sequence Generator (DOM-002)**| Atomic, gapless tenant quotation numbering (`QT-0001`) resistant to deletions and concurrency. | PostgreSQL Sequence Pattern | `Security/Quality Gap` | **Phase 2A** |
| **Quote Versioning & History** | Revision tracking (`QT-0001-A`, `QT-0001-B`) with customer lock upon approval. | Enterprise Estimating | `Planned` | Phase 3 |
| **Customer Online Quote Approval** | Public or magic-link portal allowing customers to digitally approve or reject quotations. | Modern Web-to-Print | `Planned` | Phase 4 |

---

## 5. Printing Business ERP: Sales Orders & Artwork Management

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Quotation-to-Order Conversion** | 1-click atomic conversion of approved quotes into confirmed sales orders. | ERP Workflow Automation | `Existing` | Maintained |
| **Multi-Item Sales Orders** | Orders tracking multiple custom print jobs, individual deliverables, and packaging. | Manufacturing Order Standard| `Missing` | Phase 3 |
| **Order Number Generation (DOM-002)** | Atomic, gapless tenant order numbering (`SO-0001`) preventing collisions. | Database Sequences | `Security/Quality Gap` | **Phase 2A** |
| **Artwork Vault & File Management (PRINT-003)**| Secure private file storage with UUID keys, MIME verification, and virus scanning. | Enterprise File Asset Vault | `Missing` | Phase 3 |
| **Pre-Press Preflight Checklist** | Validation of color space (CMYK vs RGB), resolution (300 DPI), bleed (3mm), and trim marks. | Pre-Press Industry Standard | `Planned` | Phase 3 |
| **Artwork Approval & Proofing** | Digital soft-proofing workflow with customer electronic sign-off and version stamp. | Web-to-Print Proofing | `Planned` | Phase 4 |

---

## 6. Printing Business ERP: Production Scheduling & Quality Control

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Standard Stage Transitions** | Structured routing: `PENDING -> PRE_PRESS -> PRINTING -> FINISHING -> QC -> COMPLETED`. | Printing Shop Floor Flow | `Existing` | Maintained |
| **Work Center & Machine Allocation** | Routing jobs to specific offset presses, digital copiers, plotters, or cutting tables. | Shop Floor Scheduling | `Missing` | Phase 3 |
| **Operator Assignment & Tracking** | Assign individual operators with time tracking (start, pause, complete) and labor hours. | MES (Mfg Execution System) | `Incomplete` | Phase 3 |
| **Defect Tracking & Rework Logging** | Record production defects (color mismatch, cutting error), scrap quantity, and rework orders. | ISO 9001 Quality Control | `Missing` | Phase 3 |
| **Job Ticket / Production Router Slip** | Printable PDF job ticket with barcode/QR code for press operators and bindery workers. | Traditional Print Shop Workhorse | `Planned` | Phase 3 |

---

## 7. Inventory & Supply Chain Management

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Immutable Stock Ledger (PRINT-004)** | Append-only double-entry inventory ledger with transaction type, delta, and post-balance. | Financial-grade Stock Ledger| `Existing` | Maintained |
| **Non-Negative Stock Constraints** | Database-level check constraints preventing accidental negative physical stock balances. | PostgreSQL CHECK Constraint | `Existing` | Maintained |
| **Material Catalog & Reorder Levels** | Tracking paper sheets, roll media, laminates, inks, and plates with reorder alerts. | Raw Materials Inventory | `Incomplete` | Phase 3 |
| **Supplier / Vendor Profiles (PRINT-005)**| Supplier address, payment terms, currency, and paper mill contact details. | Procurement Management | `Missing` | Phase 3 |
| **Purchase Orders & Goods Receipt** | PO generation, partial receiving, stock-in posting, and bill matching. | ERP Supply Chain | `Missing` | Phase 3 |
| **Offcut & Reusable Waste Reclaiming** | Re-entry of reusable paper trims and offcuts back into inventory at discounted valuation. | Eco-Printing Optimization | `Incomplete` | Phase 3 |

---

## 8. Finance, Accounting & Invoicing (Cambodia Dual-Currency)

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Dual-Currency USD/KHR Engine (DOM-01)** | Deterministic USD arithmetic with rounding to nearest 100 Riel (KHR) using snapshot rates. | National Bank of Cambodia Std| `Existing` | Maintained |
| **Customer Invoicing & Balances** | Invoices generated from sales orders tracking total, paid, and balance due. | Commercial Invoicing | `Existing` | Maintained |
| **Deposit & Milestone Allocations** | Split payments, initial 50% production deposit, and balance upon pickup/delivery. | Custom Manufacturing Billing| `Existing` | Maintained |
| **Invoice Voiding & Credit Notes (PRINT-006)**| Audited voiding workflow, credit notes, and customer account refunds. | GAAP / IFRS Accounting | `Missing` | Phase 3 |
| **GDT-Compliant Tax Invoice Templates** | Dual-language Khmer/English tax invoices with VAT TIN, sequential numbering, and official format. | Cambodia GDT Prakas | `Planned` | Phase 4 |
| **Expense & Vendor Payment Tracking** | Recording operational expenses, paper purchases, equipment maintenance, and utility bills. | Small Business Accounting | `Planned` | Phase 4 |
| **Financial Reporting** | Accounts Receivable Aging, Daily Cash Book, P&L Summary, and Tax Summary reports. | Enterprise Financial Reports| `Missing` | Phase 4 |

---

## 9. Customer Relationship Management (CRM)

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Customer Master Database** | Customer names, corporate accounts, telephone, email, delivery addresses. | Standard CRM | `Existing` | Maintained |
| **Customer Credit Limit & Terms** | Max credit limits, payment grace periods (e.g., Net 30), and credit hold automation. | B2B Commercial Credit | `Missing` | Phase 3 |
| **Customer Interaction History** | Central log of quotes requested, orders completed, payment history, and proof approvals. | 360-Degree Customer View | `Missing` | Phase 4 |
| **Customer Self-Service Portal** | Client portal to view order status, download tax invoices, and re-order previous jobs. | Web-to-Print Portal | `Planned` | Phase 4 |

---

## 10. Localization & Cambodian Business Compliance

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Bilingual UI (Khmer & English)** | Seamless language toggle without translating user business records. | National Localization | `Incomplete` | Phase 4 |
| **UTF-8 Template Encoding Repair (I18N-001)**| Eliminate corrupted question marks (`?????????`) in Angular templates; implement clean translation files. | Quality Standard | `Security/Quality Gap` | **Phase 1A** |
| **Khmer Unicode Typography** | Proper rendering of Khmer vowels, subscripts (ជើង), and numbers in UI and generated PDFs. | Unicode Consortium | `Planned` | Phase 4 |
| **Official Exchange Rate Integration** | Configurable daily exchange rates with NBC reference rate comparison. | NBC Regulatory Practice | `Incomplete` | Phase 3 |

---

## 11. Infrastructure, Observability & Disaster Recovery

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Automated Encrypted Backups (SEC-002)**| `pg_dump -Fc` encrypted with AES-256 (AEAD/GCM or HMAC) with no hardcoded fallback passphrases. | SOC2 / ISO 27001 Backup | `Existing` | **Completed** |
| **Automated Restore Drills (SEC-003)**| Isolated verification restore into `pbms_restore_verify` with manifest logging and catalog checks. | Disaster Recovery Best Practice| `Existing` | **Completed** |
| **Production Containerization & Orchestration**| Production Dockerfiles, docker-compose, and Nginx reverse proxy configuration. | 12-Factor App Standards | `Missing` | Phase 4 |
| **Structured Logging & Telemetry** | Centralized JSON logging, request tracing, and exception tracking (Sentry/OpenTelemetry). | Cloud Observability Standard| `Missing` | Phase 4 |
| **Comprehensive CI Regression Suite** | PostgreSQL integration tests, concurrency tests, frontend unit tests, and security scans. | DevSecOps Pipeline | `Incomplete` | Maintained |

---

## 12. Smart Frontend & Interactive User Experience (Smart UI / UX)

| Module / Feature | Description | Benchmark / Standard | Status | Target Phase |
| :--- | :--- | :--- | :---: | :---: |
| **Drag-and-Drop Production Kanban** | Interactive Kanban board to drag and drop job cards across stages (`PENDING -> PRE_PRESS -> PRINTING -> FINISHING -> QC -> COMPLETED`) with immediate backend sync. | Trello / Jira / Katana MRP | `Existing` | **Completed** |
| **Smart Customizable Dashboard Widgets** | Modular drag-and-drop dashboard where users/managers can reorder, reposition, expand, and collapse metric cards and charts. | Modern SaaS Dashboard (Linear/Datadog) | `Existing` | **Completed** |
| **Layout Preference Persistence** | Automatically saves user's card layout and widget arrangement to local storage and user profile. | Personalized UX Standard | `Planned` | **Phase 4** |
| **Custom Bespoke Printing SVG Icons** | Custom-generated vector SVG icon set for printing machinery (Offset Press, Digital Copier, Guillotine, Roll, CMYK, KHQR). | Custom Tailored Branding | `Planned (Optional)` | **Phase 4** |
| **Optimistic Updates & Touch Support** | High-performance drag-and-drop with tactile feedback, mobile/tablet touch support, and graceful error rollback. | Angular CDK Drag & Drop | `Planned` | **Phase 3/4** |


