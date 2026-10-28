# PBMS SaaS — Database Engineering Specification (PostgreSQL 18)

## 1. Core Database Principles
1. **Primary Keys:** UUIDv4 (`uuid.uuid4`) for all externally addressable entities to prevent ID enumeration attacks.
2. **Timestamps:** All tables include `created_at` (`TIMESTAMPTZ`) and `updated_at` (`TIMESTAMPTZ`) in UTC.
3. **Tenant Ownership:** Every tenant-scoped table MUST contain `tenant_id UUID NOT NULL REFERENCES tenants_tenant(id) ON DELETE RESTRICT`.
4. **Monetary Precision:** All currency amounts use `NUMERIC(14, 2)` for USD and `NUMERIC(16, 0)` for KHR. Binary floats (`REAL`/`DOUBLE PRECISION`) are strictly prohibited for money or stock quantities.
5. **Deletion Policy:** Financial records, audit logs, inventory ledger entries, and invoices use `ON DELETE RESTRICT` and immutable status transitions (`VOIDED`, `CANCELED`) rather than physical row deletion.

## 2. Core Entity Schema Overview

### 2.1 Identity & Session Security (`apps.accounts`)
- **`accounts_user`**
  - `id` (UUID, PK), `email` (CITEXT/VARCHAR UNIQUE), `password` (Argon2id hash), `full_name`, `phone`, `is_platform_staff` (BOOL), `platform_role` (`NONE`, `SUPER_ADMIN`, `PLATFORM_SUPPORT`), `is_active` (BOOL), `preferred_language` (`km`, `en`).
- **`accounts_authsession` (PostgreSQL Token Family & Session State)**
  - `id` (UUID, PK - serves as `session_id` / `token_family_id` in JWT claims).
  - `user_id` (UUID, FK -> `accounts_user`, `ON DELETE CASCADE`).
  - `current_refresh_jti_hash` (VARCHAR(64), SHA-256 hash of active refresh token `jti`).
  - `previous_refresh_jti_hash` (VARCHAR(64), nullable, used to detect replay/reuse of rotated tokens).
  - `ip_address` (INET), `user_agent` (TEXT).
  - `is_revoked` (BOOL, default `False`), `revoked_at` (TIMESTAMPTZ), `revoked_reason` (VARCHAR).
  - `expires_at` (TIMESTAMPTZ).
  - **Index:** `(user_id, is_revoked, expires_at)`.

### 2.2 Tenants & Memberships (`apps.tenants`)
- **`tenants_tenant`**
  - `id` (UUID, PK), `name`, `slug` (UNIQUE), `status` (`PENDING_REVIEW`, `ACTIVE`, `SUSPENDED`, `OFFBOARDED`), `base_currency` (`USD`), `khr_exchange_rate` (`NUMERIC(10, 2)`, default `4100.00`), `tax_rate_percent` (`NUMERIC(5, 2)`, default `0.00`).
- **`tenants_tenantmembership`**
  - `id` (UUID, PK), `tenant_id` (FK -> `tenants_tenant`), `user_id` (FK -> `accounts_user`), `role` (VARCHAR: `TENANT_OWNER`, `TENANT_MANAGER`, `SALES_STAFF`, `DESIGNER`, `PRODUCTION_STAFF`, `INVENTORY_STAFF`, `FINANCE_STAFF`), `is_active` (BOOL).
  - **Constraint:** `UNIQUE (tenant_id, user_id)`.

### 2.3 SaaS Plans & Subscriptions (`apps.subscriptions`)
- **`subscriptions_plan`**: `id`, `code` (UNIQUE), `name_en`, `name_km`, `monthly_price_usd`, `annual_price_usd`, `max_staff_users`, `max_orders_per_month`, `is_public`.
- **`subscriptions_tenantsubscription`**: `id`, `tenant_id` (FK), `plan_id` (FK), `status` (`TRIALING`, `PENDING_PAYMENT`, `ACTIVE`, `PAST_DUE`, `SUSPENDED`, `CANCELED`), `current_period_start`, `current_period_end`.
- **`subscriptions_subscriptionpayment`**: `id`, `tenant_id` (FK), `subscription_id` (FK), `amount_usd`, `provider` (`MOCK_LOCAL`, `MANUAL_TRANSFER`), `provider_reference` (UNIQUE when present), `idempotency_key` (UNIQUE), `status` (`PENDING`, `SUCCEEDED`, `FAILED`, `REJECTED`), `verified_by_id` (FK -> `accounts_user`, nullable).

### 2.4 Printing Operations (`apps.catalog`, `apps.sales`, `apps.production`, `apps.inventory`, `apps.finance`)
- **`catalog_material`**: `id`, `tenant_id`, `sku`, `name`, `unit` (`SHEET`, `ROLL`, `SQM`, `LITER`, `PIECE`), `reorder_level`, `current_stock` (`NUMERIC(12, 3)` — updated strictly via atomic ledger service).
  - **Constraint:** `UNIQUE (tenant_id, sku)`, `CHECK (current_stock >= 0)`.
- **`catalog_printingservice`**: `id`, `tenant_id`, `code`, `name`, `base_setup_fee_usd`, `unit_price_usd`, `pricing_unit`.
- **`sales_customer`**: `id`, `tenant_id`, `name`, `phone`, `email`, `company_name`.
- **`sales_quotation` & `sales_quotationitem`**: Tracks item specifications (width, height, GSM, color sides, finishing), calculated subtotal, discount, tax, and locked total in USD & KHR.
- **`sales_salesorder` & `sales_salesorderitem`**: Created from approved quotations or direct entry; stores artwork metadata (`file_name`, `file_hash`, `storage_path`).
- **`production_productionjob`**: `id`, `tenant_id`, `sales_order_item_id`, `stage` (`PENDING`, `PRE_PRESS`, `PRINTING`, `FINISHING`, `QC`, `COMPLETED`), `assigned_to_id`, `planned_labor_cost_usd`, `actual_labor_cost_usd`.
- **`inventory_inventorytransaction` (Immutable Ledger)**:
  - `id`, `tenant_id`, `material_id`, `transaction_type` (`STOCK_IN`, `RESERVATION`, `CONSUMPTION`, `WASTE`, `OFFCUT_RETURN`, `ADJUSTMENT`), `quantity_delta` (`NUMERIC(12, 3)`), `balance_after` (`NUMERIC(12, 3)`), `reference_type`, `reference_id`, `created_by_id`.
- **`finance_invoice` & `finance_paymentallocation`**: Tracks `total_amount_usd`, `paid_amount_usd`, `balance_due_usd`, and status (`ISSUED`, `PARTIALLY_PAID`, `PAID`, `VOIDED`).

### 2.5 Immutable Audit Trail (`apps.core`)
- **`core_auditevent`**: `id`, `created_at`, `actor_user_id`, `tenant_id` (nullable for platform events), `event_type`, `target_model`, `target_id`, `ip_address`, `metadata` (JSONB).