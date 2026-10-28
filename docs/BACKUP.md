# PBMS SaaS — Automated Backup & Disaster Recovery Specification

## 1. Recovery Objectives
- **Recovery Point Objective (RPO):** 24 hours (daily automated scheduled backups; on-demand before any schema migration or release).
- **Recovery Time Objective (RTO):** < 30 minutes for local/staging database restoration.

## 2. Backup Architecture (`ops/backup_postgres.ps1`)
1. **Format:** PostgreSQL Custom Format (`pg_dump --format=custom --no-owner --no-acl`) which includes internal compression and table-of-contents metadata.
2. **Encryption at Rest:** Archive is encrypted using AES-256 via OpenSSL/PowerShell cryptographic stream using a passphrase read from an environment variable (`PBMS_BACKUP_PASSPHRASE`), never hardcoded.
3. **Checksum & Manifest:** Every backup generates a `.sha256` hash file and writes a JSON manifest entry recording timestamp, file size, exit code, and SHA-256 digest.
4. **Retention Policy:** Configurable retention (default 30 days) automatically prunes expired local archives only after a new backup and verification succeed.

## 3. Automated Restore Verification Drill (`ops/verify_restore.ps1`)
A backup is only considered valid when restoration is verified:
1. Verify SHA-256 checksum of the backup artifact.
2. Decrypt archive to a temporary stream/file.
3. Inspect archive catalog via `pg_restore --list`.
4. Create a temporary isolated PostgreSQL database (`pbms_restore_verify`).
5. Execute `pg_restore --dbname=pbms_restore_verify --clean --if-exists`.
6. Run verification SQL queries checking core table counts (`accounts_user`, `tenants_tenant`, `core_auditevent`).
7. Drop the temporary `pbms_restore_verify` database and record a `BACKUP_RESTORE_VERIFIED` audit log.