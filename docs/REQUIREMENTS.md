# PBMS SaaS — Functional & Non-Functional Requirements

## 1. Identity, Authentication & Session Security (`REQ-AUTH`)
- **REQ-AUTH-01:** Passwords MUST be hashed using `Argon2id` via `django.contrib.auth.hashers.Argon2PasswordHasher`.
- **REQ-AUTH-02:** Authentication MUST issue a short-lived Access JWT (15 minutes) and a Rotating Refresh Token (7 days) tied to a PostgreSQL `AuthSession` (token family).
- **REQ-AUTH-03:** Presenting a previously rotated (used) Refresh Token MUST trigger immediate revocation of the entire token family (`AuthSession.is_revoked = True`) and log a security audit event.
- **REQ-AUTH-04:** Users MUST be able to revoke their current session (logout) or all active sessions. Disabling a user account MUST immediately invalidate all active sessions.

## 2. Authorization & Multi-Tenant Isolation (`REQ-RBAC`)
- **REQ-RBAC-01:** Platform-scoped roles (`SUPER_ADMIN`, `PLATFORM_SUPPORT`) MUST be strictly separated from Tenant-scoped roles (`TENANT_OWNER`, `TENANT_MANAGER`, `SALES_STAFF`, `DESIGNER`, `PRODUCTION_STAFF`, `INVENTORY_STAFF`, `FINANCE_STAFF`).
- **REQ-RBAC-02:** Every API request to tenant-scoped endpoints MUST validate active membership of `request.user` in the target `Tenant` and verify role permissions before querying or mutating records.
- **REQ-RBAC-03:** Cross-tenant access (IDOR) MUST return `403 Forbidden` or `404 Not Found` and be covered by automated negative integration tests.

## 3. SaaS Onboarding, Subscriptions & Billing (`REQ-SAAS`)
- **REQ-SAAS-01:** Prospective printing businesses can register an account and tenant request from the Public Website (`Frontend C`).
- **REQ-SAAS-02:** Subscriptions track `Plan`, `PlanVersion`, billing period, entitlements (max staff, max orders/month, storage quota), and lifecycle states (`TRIALING`, `PENDING_PAYMENT`, `ACTIVE`, `PAST_DUE`, `SUSPENDED`, `CANCELED`).
- **REQ-SAAS-03:** Payment confirmation MUST only occur via verified server-side webhook callbacks (with idempotency keys) or explicit Super Admin reconciliation—never solely from frontend status flags.

## 4. Printing Business Operations (`REQ-PRINT`)
- **REQ-PRINT-01 (Catalog & Pricing):** Tenants manage customers, suppliers, materials, and product/service templates with deterministic pricing formulas:
  `Item Subtotal = (Base Setup Fee + (Unit Rate * Quantity) + Finishing Cost) - Item Discount`.
- **REQ-PRINT-02 (Quotations & Orders):** Approved quotations lock their pricing snapshot and can be converted into a `SalesOrder` with attached artwork file metadata.
- **REQ-PRINT-03 (Production Workflow):** Each `SalesOrderItem` spawns one or more `ProductionJob` records with explicit state transitions (`PENDING -> PRE_PRESS -> PRINTING -> FINISHING -> QC -> COMPLETED`) and actor tracking.
- **REQ-PRINT-04 (Inventory Ledger):** Material stock levels are calculated from `InventoryTransaction` ledger entries. Outbound consumption cannot drive available stock negative unless an explicit manager override policy is recorded.
- **REQ-PRINT-05 (Invoicing & Payments):** Tenants issue customer invoices, record partial/deposit payments, allocate payments against invoices, and track outstanding balances accurately in `USD` and `KHR`.

## 5. Non-Functional, Audit & Disaster Recovery (`REQ-NFR`)
- **REQ-NFR-01 (Audit Trail):** All sensitive mutations (auth failures, token reuse, role changes, tenant suspension, price overrides, invoice voids, backup runs) MUST write an immutable `AuditEvent` record.
- **REQ-NFR-02 (Automated Backup & Restore):** Automated scripts MUST dump PostgreSQL (`pg_dump -Fc`), encrypt the archive, verify integrity (`pg_restore --list`), and support automated test restoration into a temporary verification database (`pbms_restore_verify`).
- **REQ-NFR-03 (Localization):** UI supports Khmer (`km`) and English (`en`) without altering user-entered business data.