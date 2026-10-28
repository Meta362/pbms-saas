# PBMS SaaS — System Architecture

## 1. High-Level Topology

```text
+------------------------+   +------------------------+   +------------------------+
|  Frontend A (Angular)  |   |  Frontend B (Angular)  |   |  Frontend C (Angular)  |
|   Super Admin Portal   |   |    Tenant Workspace    |   |   Public SaaS Website  |
|   http://localhost:4201|   |   http://localhost:4202|   |   http://localhost:4200|
+-----------+------------+   +-----------+------------+   +-----------+------------+
            |                            |                            |
            +----------------------------+----------------------------+
                                         |
                               HTTPS / REST JSON API
                         (Authorization: Bearer <AccessJWT>)
                              (X-Tenant-ID: <UUID>)
                                         |
                                         v
                    +-----------------------------------------+
                    |     Shared Authoritative Backend API    |
                    |       Django 5.2 LTS + DRF + Python     |
                    |          http://localhost:8000          |
                    |-----------------------------------------|
                    | - apps.core (Health, Audit, Exceptions) |
                    | - apps.accounts (Users, AuthSessions)   |
                    | - apps.tenants (Tenants, Memberships)   |
                    | - apps.subscriptions (Plans, Billing)   |
                    | - apps.catalog (Materials, Products)    |
                    | - apps.sales (Customers, Quotes, Orders)|
                    | - apps.production (Jobs, Stages)        |
                    | - apps.inventory (Stock Ledger)         |
                    | - apps.finance (Invoices, Payments)     |
                    +--------------------+--------------------+
                                         |
                                         v
                    +-----------------------------------------+
                    |         PostgreSQL 18 Database          |
                    | - ACID Transactions & Constraints       |
                    | - Token Family & Session State          |
                    | - Immutable Inventory & Audit Ledgers   |
                    +--------------------+--------------------+
                                         |
                                         v
                    +-----------------------------------------+
                    |   Automated Backup & Restore Verifier   |
                    |   ops/backup_postgres.ps1               |
                    |   ops/verify_restore.ps1                |
                    +-----------------------------------------+