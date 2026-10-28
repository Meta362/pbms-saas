# PBMS SaaS — Testing Strategy & Execution Evidence

## 1. Executed Test Catalog (PostgreSQL 18)
Command: `.\.venv\Scripts\python.exe manage.py test apps.core apps.accounts apps.subscriptions apps.operations -v 2`

| Test Case | Requirement | Status |
| :--- | :--- | :--- |
| `test_health_check_endpoint_returns_200_and_argon2_status` | `REQ-AUTH-01` | **PASSED** |
| `test_password_hasher_uses_argon2id_by_default` | `REQ-AUTH-01` | **PASSED** |
| `test_user_tenant_membership_session_and_audit_constraints` | `REQ-RBAC-01`, `REQ-NFR-01` | **PASSED** |
| `test_login_issues_tokens_and_returns_tenant_memberships` | `REQ-AUTH-02` | **PASSED** |
| `test_refresh_token_rotation_and_reuse_detection_revokes_session` | `REQ-AUTH-02`, `REQ-AUTH-03` | **PASSED** |
| `test_logout_immediately_revokes_session_in_postgres` | `REQ-AUTH-04` | **PASSED** |
| `test_cross_tenant_idor_access_is_strictly_blocked` | `REQ-RBAC-02`, `REQ-RBAC-03` | **PASSED** |
| `test_public_registration_idempotency_and_super_admin_reconciliation_flow` | `REQ-SAAS-01..03` | **PASSED** |
| `test_inventory_ledger_and_negative_stock_prevention` | `REQ-PRINT-04` | **PASSED** |
| `test_quotation_pricing_order_conversion_production_and_invoice_allocations` | `REQ-PRINT-01..05` | **PASSED** |

## 2. Disaster Recovery Drill Evidence
- `ops/backup_postgres.ps1`: Executed `pg_dump -Fc`, encrypted with AES-256-CBC (PBKDF2), and generated SHA-256 digest.
- `ops/verify_restore.ps1`: Verified SHA-256 digest, decrypted archive, restored into temporary database `pbms_restore_verify`, and verified row counts (`PASSED`).

## 3. Frontend Production Builds
- `npm run build:public` (`dist/public-site`) — **PASSED**
- `npm run build:admin` (`dist/super-admin`) — **PASSED**
- `npm run build:tenant` (`dist/tenant-workspace`) — **PASSED**
