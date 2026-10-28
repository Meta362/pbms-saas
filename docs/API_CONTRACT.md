# PBMS SaaS — Authoritative REST API Contract

Base URL (Local Dev): `http://localhost:8000/api/v1`
Interactive OpenAPI / Swagger UI: `http://localhost:8000/api/docs/`

## 1. Operational Health
- `GET /api/v1/health/` (Public) — Returns service health and Argon2id verification flag.

## 2. Authentication & Session Security (`apps.accounts`)
- `POST /api/v1/auth/login/` — Issues short-lived Access JWT (15m) + Rotating Refresh Token (7d) + PostgreSQL `AuthSession`.
- `POST /api/v1/auth/refresh/` — Atomically rotates refresh token; revokes entire session family if token reuse is detected.
- `POST /api/v1/auth/logout/` — Immediately revokes active PostgreSQL `AuthSession`.
- `GET /api/v1/auth/me/` — Returns current user profile and active tenant memberships.
- `GET /api/v1/tenant/context/` — Verifies `X-Tenant-ID` membership and returns tenant currency/tax settings.

## 3. Public SaaS Website & Super Admin Governance (`apps.subscriptions`)
- `GET /api/v1/public/plans/` (Frontend C) — Public subscription plans.
- `POST /api/v1/public/register-tenant/` (Frontend C) — Idempotent tenant registration & checkout initiation.
- `GET /api/v1/super-admin/overview/` (Frontend A - `SUPER_ADMIN` only) — Platform metrics, revenue, and recent audit events.
- `GET /api/v1/super-admin/tenants/` (Frontend A - `SUPER_ADMIN` only) — Tenant directory and payment status.
- `POST /api/v1/super-admin/payments/<uuid:payment_id>/reconcile/` (Frontend A) — Approve/reject subscription payment and activate tenant.
- `POST /api/v1/super-admin/tenants/<uuid:tenant_id>/status/` (Frontend A) — Suspend or reactivate a tenant.

## 4. Printing Business Operations (`apps.operations` — Frontend B, requires `X-Tenant-ID`)
- `GET /api/v1/tenant/dashboard/` — Tenant operational KPIs and financial summary.
- `GET / POST /api/v1/tenant/customers/` — Tenant customer directory.
- `GET / POST /api/v1/tenant/materials/` — Printing material catalog & stock balances.
- `GET / POST /api/v1/tenant/inventory-movements/` — Immutable inventory stock ledger transactions.
- `GET / POST /api/v1/tenant/quotations/` — Deterministic USD/KHR printing quotations.
- `POST /api/v1/tenant/quotations/<uuid:quotation_id>/convert/` — Converts quote into Sales Order, Production Job, and Customer Invoice.
- `GET /api/v1/tenant/orders/` — Sales orders and linked production job / invoice status.
- `POST /api/v1/tenant/production-jobs/<uuid:job_id>/stage/` — Transitions press workflow stage (`PENDING -> PRE_PRESS -> PRINTING -> FINISHING -> QC -> COMPLETED`).
- `GET /api/v1/tenant/invoices/` — Customer invoices.
- `POST /api/v1/tenant/invoices/<uuid:invoice_id>/payments/` — Allocates customer deposit or final balance payment.
