# PBMS SaaS — Agent Instructions

These instructions are intended for Google Jules and other autonomous coding agents working on the PBMS SaaS repository. **You must strictly obey these directives.**

## 1. Domain Knowledge & Documentation
- **Read before modifying:** Read relevant requirements, architecture, database, RBAC, security, API contract, and testing documentation in `docs/` before making any code changes.
- **Documentation as Truth:** Treat the actual code and approved engineering documentation as evidence. If documentation conflicts, report the conflict instead of silently choosing a new architecture.
- **Stay in scope:** Preserve existing changes and avoid unrelated refactoring.

## 2. Architecture & Security Invariants
- **Strict Tenant Isolation:** Keep tenant isolation enforced server-side. Never trust a client-provided tenant ID without membership verification.
- **Core Rules:** Preserve RBAC, authentication/session revocation, audit logging, inventory ledger integrity, non-negative stock, financial accuracy, and subscription entitlement enforcement.
- **Production Data & Contracts:** Never modify production data, weaken security controls, or change API contracts without a requirement and regression tests.

## 3. Database & Testing
- **Concurrency & DB Tests:** Use PostgreSQL for database tests, especially concurrency tests. Do not treat SQLite, mocks, or sequential tests as proof of PostgreSQL concurrency safety.
- **Test Reporting:** Run relevant tests and builds, inspect the final diff, and report exact commands and outcomes. Distinguish between PASS, FAIL, and NOT VERIFIED. Never claim an unexecuted test passed.

## 4. Git & Workflow Safety
- **No Secrets:** Never commit secrets, production credentials, real customer data, or database dumps.
- **Avoid Unnecessary Changes:** Avoid migrations, dependency upgrades, architecture changes, and destructive actions unless explicitly required by the approved task.
- **Pull Requests:** Never merge a Pull Request automatically.
