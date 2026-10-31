# PBMS SaaS — Master Audit Report & Implementation Roadmap

> **Status:** Read-only audit baseline and proposed roadmap. This document does not authorize implementation, merging, deployment, or production database changes.
>
> **Audit baseline branch:** `feat/task-04-production-settings-hardening-11635122478871391506`  
> **Audit baseline HEAD:** `8a5d14c9d743442f9195e3de3dd324676b086ad1`  
> **Baseline commit:** `fix(billing): prevent unpaid subscription reactivation`  
> **Working tree at last observation:** Clean

## 1. Executive Summary

PBMS SaaS has important foundations: Django REST Framework, PostgreSQL, three Angular applications, authentication/session management, tenant membership and RBAC, subscription/payment models, printing operations, inventory ledger, invoicing, and CI tests.

However, the evidence reviewed does not yet support a conclusion that the system is a complete, production-ready SaaS platform.

Main gaps requiring verification or implementation:

- Production secrets and backup/restore controls do not fully match the documented specification.
- Authentication hardening and tenant-isolation coverage require additional verification.
- SaaS billing, plan entitlements, and subscription lifecycle do not yet show evidence of all expected capabilities.
- Printing workflows do not yet show complete coverage of the domain models and processes described in requirements.
- Some documentation does not align with the code structure observed.
- Production deployment, monitoring, recovery operations, and comprehensive end-to-end evidence remain unverified.

**Conclusion:** Continue with evidence-driven hardening and gap closure before declaring production readiness.

## 2. Audit Scope and Limitations

### Evidence inspected

- `docs/REQUIREMENTS.md`
- `docs/SECURITY.md`
- `docs/ARCHITECTURE.md`
- `docs/BACKUP.md`
- `docs/TESTING.md`
- `docs/RBAC.md`
- Backend app/model/view/test inventory
- Frontend project structure and selected session-related code
- CI workflow and Git/PR state
- Authentication, billing, backup/restore, and selected tenant-authorization implementations

### Evidence limitations

- No complete production deployment review has been performed.
- Fresh execution evidence for all tests and the full disaster-recovery drill has not been established.
- A complete endpoint-by-endpoint authorization matrix has not been verified.
- Comprehensive UI/end-to-end test evidence for every business workflow is not yet available.
- External infrastructure and payment-provider configuration have not been verified.
- “Not found in inspected evidence” does not prove a feature is entirely absent.

## 3. Priority Definitions

- **P0 — Critical foundation:** Could undermine production security, tenant data protection, or data recovery.
- **P1 — Required before production:** Important for secure and reliable SaaS operation.
- **P2 — Core business completeness:** Important for complete printing-business workflows.
- **P3 — Advanced capability:** Advanced analytics, automation, integrations, and scalability enhancements.

Priorities must be updated after verification. Do not classify a feature as a confirmed defect solely because it has not yet been found.

## 4. Master Gap Register

### P0 — Security, data integrity, and recovery

#### SEC-001: JWT signing-key separation

**Evidence:** The JWT service can fall back to Django `SECRET_KEY` if `JWT_SIGNING_KEY` is not configured.

**Risk:** A shared key can complicate secret rotation and containment after compromise.

**Acceptance criteria:**
- Production configuration fails closed if a separate valid JWT signing key is missing.
- No insecure production fallback remains.
- Tests cover missing/invalid secrets and token validation.
- Documentation describes key rotation and deployment configuration.

#### SEC-002: Backup encryption and secret handling

**Evidence:** Backup scripts contain a hardcoded fallback passphrase.

**Risk:** Backup confidentiality depends on a predictable default secret.

**Acceptance criteria:**
- No hardcoded production-capable passphrase exists.
- Backup fails clearly if its required secret is missing.
- The encryption format provides confidentiality and authenticated integrity.
- Encryption secrets are never written to logs or committed to the repository.
- Tests cover missing secrets, corrupted archives, and tampering.

#### SEC-003: Restore verification and disaster-recovery evidence

**Evidence:** The inspected scripts do not yet demonstrate all documented manifest, retention, archive-list validation, and restore-verification behavior.

**Risk:** A backup may exist but fail to restore correctly or fail to meet recovery objectives.

**Acceptance criteria:**
- Each backup has verifiable manifest and integrity metadata.
- Restore scripts check exit codes at every critical step.
- The archive is validated before restoration.
- The verification database is isolated and has safe cleanup safeguards.
- Retention never deletes necessary backups before a new backup is successfully verified.
- Restore-drill evidence records measured recovery behavior.
- No production database is dropped or destructively restored without explicit authorization.

### P1 — Identity, authorization, and SaaS correctness

#### AUTH-001: Authentication abuse protection

**Evidence:** Login and refresh endpoints were found, but throttle configuration was not found in the inspected authentication endpoints.

**Acceptance criteria:**
- Rate limiting covers login, refresh, and recovery workflows as appropriate.
- Account enumeration is mitigated.
- Security events are audited without recording passwords or raw tokens.
- Tests cover repeated failures and rate-limit behavior.

#### AUTH-002: Account recovery and verification

**Evidence:** Password-recovery and email-verification routes were not found in the inspected route inventory.

**Acceptance criteria:**
- A secure password-reset flow exists if email accounts are part of onboarding.
- Reset tokens are one-time and expire; session-revocation behavior is defined.
- Email-verification lifecycle and abuse prevention are implemented where required.
- Tests cover expired/reused tokens and cross-account misuse.

#### AUTH-003: Session-wide revocation

**Evidence:** Refresh rotation and session-revocation foundations have tests; all-session logout and account-disable behavior need confirmation.

**Acceptance criteria:**
- Users can revoke the current session and all active sessions.
- Disabled accounts cannot continue using existing sessions.
- PostgreSQL and concurrent-request tests verify the behavior.

#### TENANT-001: Cross-tenant relationship integrity

**Evidence:** Tenant-scoped query patterns and some cross-tenant IDOR tests exist.

**Acceptance criteria:**
- ForeignKey/OneToOne relationships cannot connect records across tenants without explicit validated authorization.
- API object access, nested relationships, exports, and mutations are scoped to the active tenant.
- Negative tests cover cross-tenant IDs and mismatched related objects.
- Database constraints or service-layer validation are used where appropriate.

#### RBAC-001: Endpoint permission matrix

**Evidence:** Platform and tenant roles exist, but frontend role gating is not a substitute for backend authorization.

**Acceptance criteria:**
- Every endpoint and sensitive action has a documented permission matrix.
- Backend authorization is enforced independently of the frontend.
- `PLATFORM_SUPPORT` cannot perform prohibited mutations.
- Sensitive operations have actor attribution and audit events.

#### SAAS-001: Plan and entitlement completeness

**Evidence:** Plan and some staff/order entitlements exist; `PlanVersion` and storage quota were not found in the inspected model inventory.

**Acceptance criteria:**
- Plan versioning and entitlement changes have deterministic behavior.
- Usage limits are enforced at server/database transaction boundaries.
- Upgrades/downgrades do not corrupt data or subscription state.
- Usage metering and auditability are available.

#### BILLING-001: Subscription lifecycle

**Evidence:** Subscription statuses, payment records, and manual reconciliation exist; full billing lifecycle behavior has not been verified.

**Acceptance criteria:**
- Behavior is defined for trial, activation, renewal, failed payment, grace period, expiration, cancellation, and reactivation.
- Unpaid subscriptions cannot reactivate through direct status changes alone.
- Payment processing has idempotency and concurrency safeguards.
- Webhook verification exists if an external gateway is used.
- USD/KHR records have explicit rounding and exchange-rate snapshot policies.

#### UI-001: Demo credential exposure

**Evidence:** Tenant Workspace UI displays demo credentials and a prefilled password.

**Acceptance criteria:**
- Demo credentials are not displayed in production builds.
- Demo seed data and demo login are separated from production configuration.
- Automated checks confirm production builds contain no demo password or seeded secret.

#### OPS-001: Production observability and deployment

**Evidence:** CI includes backend/frontend checks; deployment infrastructure and operational monitoring have not been verified.

**Acceptance criteria:**
- Production configuration is reproducible.
- Structured logs, health checks, error monitoring, and actionable alerts exist.
- Deployment, migration, and rollback procedures are documented.
- Secrets management and dependency vulnerability checks are in place.
- Staging validation occurs before production release.

### P2 — Printing-business completeness

#### PRINT-001: Product/service catalog and pricing

**Acceptance criteria:**
- Product/service templates and versioned pricing formulas.
- Setup fees, unit rates, finishing, discounts, waste allowances, and approval policy.
- Quote price snapshots remain unchanged when catalog prices later change.
- Decimal arithmetic and currency rounding are correct and tested.

#### PRINT-002: Quotation and sales-order lifecycle

**Acceptance criteria:**
- Quote versions, expiry, approval, rejection, and conversion rules.
- Sales-order items include quantities, prices, specifications, and artwork references.
- Partial fulfilment, cancellation, and controlled order amendments.
- Atomic order-number generation and idempotent conversion.

#### PRINT-003: Artwork and document management

**Acceptance criteria:**
- Private file storage and access authorization.
- File size/type validation and randomized storage identifiers.
- Artwork versions, approval state, and association with orders/jobs.
- Download authorization, retention, and cleanup policies.

#### PRINT-004: Production planning and quality control

**Acceptance criteria:**
- Production routing and stage-transition rules.
- Job assignment, scheduling, and operator attribution.
- QC pass/fail, defects, rework, and completion sign-off.
- Traceable job/material-consumption history.

#### PRINT-005: Inventory and purchasing

**Acceptance criteria:**
- Supplier management, purchase orders, and goods receipts.
- Stock ledger as the authoritative source of stock movement.
- Stock reservation, consumption, waste, offcuts, and adjustments.
- Reconciliation between ledger balance and stored/cached balance.
- Concurrency tests for simultaneous stock movements.

#### PRINT-006: Finance

**Acceptance criteria:**
- Invoice, deposit, partial-payment, and allocation correctness.
- Credit notes, voids, refunds, and approval workflows.
- USD/KHR snapshots, exchange-rate provenance, and rounding rules.
- Financial reports reconcile with source transactions.

### P2/P3 — SaaS operations and advanced capabilities

#### PLATFORM-001: Tenant onboarding and lifecycle

Tenant application review, activation, suspension, reactivation, offboarding, and data-retention policy.

#### PLATFORM-002: Notifications

In-app/email notifications, templates, retry policy, delivery status, and user preferences.

#### PLATFORM-003: Support operations

Support tickets, tenant issue history, controlled support access, and audit trail. Support impersonation must not bypass tenant isolation or sensitive-action approvals.

#### PLATFORM-004: Reporting and analytics

Sales, receivables, inventory valuation, production efficiency, and export capabilities. Reports must be tenant-scoped and use consistent financial definitions.

#### PLATFORM-005: Integration platform

API versioning, webhook delivery/retries, integration credentials, and integration audit trail.

#### PLATFORM-006: Scalability and performance

Query optimization, pagination, caching policy, background jobs, and load/concurrency tests. Optimization choices should be based on measurements.

#### UX-001: Frontend quality

Consistent design system for Public Website, Super Admin, and Tenant Workspace; responsive layouts, accessibility, loading/error/empty states, form validation, and safe session recovery. Frontend role gating must align with backend permissions.

#### QA-001: Comprehensive test coverage

Unit, integration, authorization-matrix, concurrency, security, migration, and end-to-end tests. CI gates must be explicit and prevent regressions from reaching release branches.

## 5. Implementation Roadmap

### Phase 0 — Audit baseline and architecture alignment

**Deliverables:**
- Final Gap Register and requirement-to-code traceability.
- Architecture target and module ownership.
- Security threat model and data classification.
- Test baseline and branch/PR plan.

**Exit criteria:**
- Every P0/P1 gap has evidence, acceptance criteria, and a verification method.
- Architecture documents align with the intended implementation target.
- No code changes occur before implementation authorization.

### Phase 1 — Security and recovery foundations

**Scope:**
- JWT secret separation.
- Backup encryption and secret handling.
- Restore verification, retention, and DR evidence.
- Authentication throttling and session-revocation verification.
- Tenant relationship integrity and endpoint authorization matrix.

**Exit criteria:**
- Critical security tests pass.
- Backup/restore drill runs in an isolated verification environment.
- No unverified production secret fallback remains.
- Cross-tenant negative tests pass.

### Phase 2 — SaaS core

**Scope:**
- Tenant onboarding/lifecycle.
- Staff membership and permission model.
- Plans, versions, entitlements, and usage metering.
- Subscription lifecycle, payment reconciliation, and provider-integration boundaries.
- Audit coverage and administrative operations.

**Exit criteria:**
- Billing state transitions have tests.
- Idempotency and concurrency protections are verified.
- Entitlement limits are enforced in the backend.
- Platform-support permissions have negative tests.

### Phase 3 — Printing-business core

**Scope:**
- Customer/supplier/catalog management.
- Pricing formulas and quote versioning.
- Sales-order items and artwork references.
- Production jobs, routing, QC, and rework.
- Inventory ledger, purchasing, and reconciliation.
- Invoicing, payment allocations, and USD/KHR rules.

**Exit criteria:**
- End-to-end workflow: Customer → Quote → Order → Production → Inventory → Invoice → Payment.
- Financial and stock reconciliation tests pass.
- No cross-tenant relationship violations remain.
- Audit trail covers sensitive financial/stock actions.

### Phase 4 — Platform operations and UX

**Scope:**
- Notifications, support workflows, and reporting.
- Frontend design-system consistency and accessibility.
- Observability, error reporting, monitoring, and operational runbooks.
- Deployment, migrations, rollback, and environment validation.

**Exit criteria:**
- Critical user journeys pass end-to-end tests.
- Production configuration is reproducible.
- Monitoring/alerting and recovery procedures are documented and verified.

### Phase 5 — Reliability, performance, and release readiness

**Scope:**
- Security regression review.
- Load/concurrency tests.
- Dependency and configuration review.
- Backup/restore drill.
- Full regression and migration verification.
- EGM bounded reviews at checkpoints and Jules comprehensive review near completion if available.

**Exit criteria:**
- No unresolved P0 findings.
- P1 findings are resolved or explicitly accepted with documented risk and mitigation.
- Release checklist, test evidence, and rollback plan are complete.
- Release readiness is based on evidence, not feature count alone.

## 6. Engineering Workflow and Change Controls

For each implementation task:

1. Inspect the current branch, working tree, and related code/tests.
2. Define bounded scope and acceptance criteria.
3. Implement the change and relevant tests.
4. Run targeted tests, broader regression tests where feasible, and static checks.
5. Review the full diff for security, migrations, accidental files, and unrelated changes.
6. Report changed files, test commands/results, limitations, and residual risks.
7. Commit/push according to the authorized workflow; never merge a PR or alter production data without explicit authorization.
8. Choose the next task only after reviewing the agent's evidence.

Protect existing drafts and uncommitted changes. Do not use destructive Git commands or run backup/restore scripts against non-isolated databases during audit.

## 7. Definition of Done

A module is not complete merely because its UI exists or its tests pass.

Completion requires:
- Requirements and acceptance criteria are documented.
- Backend authorization and tenant isolation are enforced.
- Data integrity and transaction behavior are tested.
- Error, loading, and edge-case handling are covered.
- Security and audit requirements are addressed.
- Automated tests pass with recorded evidence.
- Relevant documentation matches actual behavior.
- The diff contains no unrelated or unsafe changes.
- Operational behavior is verified when the module affects production reliability.

## 8. Current Audit Conclusion

PBMS SaaS has useful foundations but requires additional verification and implementation before it can be considered a comprehensive production-grade SaaS platform.

The next implementation task should be selected from verified P0 findings, not from cosmetic UI work or a desire to increase the module count quickly.

This report records current evidence and proposed acceptance criteria. It does not claim that unverified features are absent, that production systems are misconfigured, or that all proposed modules must be implemented in one release.
