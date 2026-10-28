# PBMS SaaS — Role-Based Access Control (RBAC) Specification

## 1. Scope Separation
PBMS enforces a strict boundary between **Platform Scope** (`Frontend A`) and **Tenant Scope** (`Frontend B`).
- A Platform Super Admin cannot accidentally mutate tenant operational records through tenant endpoints without an explicit audited support action.
- A Tenant Owner has full administrative authority **only within their own Tenant** and zero access to other tenants or platform settings.

## 2. Platform Roles (`accounts_user.platform_role`)
| Role | Capabilities | Restricted From |
| :--- | :--- | :--- |
| `SUPER_ADMIN` | Approve/suspend tenants, manage subscription plans, reconcile SaaS payments, view platform audit logs, trigger/verify backups. | Bypassing audit logs or modifying finalized tenant customer invoices without trace. |
| `PLATFORM_SUPPORT` | Read-only access to tenant status, subscription health, and audit logs for troubleshooting. | Approving payments, changing plans, or deleting records. |

## 3. Tenant Roles (`tenants_tenantmembership.role`)
| Role | Primary Permissions | Sensitive Operations Allowed |
| :--- | :--- | :--- |
| `TENANT_OWNER` | Full access to all tenant modules, tenant settings, exchange rates, staff invitations, and billing. | Price overrides, invoice voiding, stock adjustments, role delegation. |
| `TENANT_MANAGER` | Operational oversight across sales, production, inventory, and finance reports. | Price overrides (audited), stock adjustments (audited), job reassignment. |
| `SALES_STAFF` | Manage customers, create quotations, convert quotations to sales orders, view order status. | Cannot adjust inventory or void finalized invoices. |
| `DESIGNER` | View assigned sales orders, upload/verify artwork files, transition job stage `PENDING -> PRE_PRESS`. | Cannot view financial reports or modify pricing. |
| `PRODUCTION_STAFF`| View production queue, update job stages (`PRE_PRESS -> PRINTING -> FINISHING -> QC -> COMPLETED`), log material consumption/waste. | Cannot alter order prices or customer invoices. |
| `INVENTORY_STAFF` | Manage suppliers, materials, record `STOCK_IN`, view stock ledger. | Manual negative adjustments require `TENANT_MANAGER` or `TENANT_OWNER`. |
| `FINANCE_STAFF` | Issue customer invoices, record payments, allocate deposits, record expenses, view financial reports. | Invoice voiding requires `TENANT_OWNER` or `TENANT_MANAGER` approval. |