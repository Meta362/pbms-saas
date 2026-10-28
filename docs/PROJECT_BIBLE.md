# PBMS SaaS — Project Bible

## 1. Vision & Scope
Printing Business Management System (PBMS) is a multi-tenant, production-oriented B2B SaaS platform tailored for printing businesses in Cambodia and Southeast Asia. It manages the entire printing lifecycle from customer quotation and artwork submission to production workflow, material inventory ledger, delivery, and invoicing.

## 2. Core Architectural Invariants (Locked)
1. **Three Separate Frontends (`Angular + Tailwind CSS`):**
   - **Frontend A (`super-admin`):** Platform operator portal (Port `4201` in local dev).
   - **Frontend B (`tenant-workspace`):** Printing business & staff operational portal (Port `4202` in local dev).
   - **Frontend C (`public-site`):** Marketing, pricing, registration, and subscription checkout portal (Port `4200` in local dev).
2. **One Shared Authoritative Backend (`Django + DRF + PostgreSQL`):**
   - Enforces all authentication, RBAC, tenant isolation, business rules, and audit logging.
3. **Security First:**
   - Password hashing via `Argon2id`.
   - Short-lived Access JWTs + Rotating Refresh Tokens with Reuse Detection backed by PostgreSQL session families.
   - Strict server-side tenant context resolution; zero trust in client-supplied tenant identifiers without membership verification.
4. **Financial & Inventory Integrity:**
   - All monetary calculations use fixed-point `DECIMAL(14, 2)` (USD base) and explicit KHR exchange-rate rounding rules.
   - Material stock is governed strictly by an immutable Inventory Ledger; direct arbitrary edits to quantity on hand are forbidden.

## 3. Terminology & Domain Glossary
- **Platform Operator (Super Admin):** The owner/administrator of the PBMS SaaS platform.
- **Tenant:** An individual printing business subscribed to PBMS.
- **Tenant Membership:** The association binding a User to a specific Tenant with assigned Tenant Roles.
- **Quotation:** A formal price estimate for printing items with defined specifications, quantities, and discounts.
- **Sales Order:** A confirmed customer order (converted from an approved Quotation or created directly) ready for production and billing.
- **Production Job:** A trackable work order moving through printing stages (`PRE_PRESS`, `PRINTING`, `FINISHING`, `QC`, `COMPLETED`).
- **Inventory Ledger Entry:** An immutable record of material movement (`STOCK_IN`, `RESERVATION`, `CONSUMPTION`, `WASTE`, `OFFCUT_RETURN`, `ADJUSTMENT`).

## 4. Decision Governance Log
| ID | Decision Summary | Status | Rationale |
| :--- | :--- | :--- | :--- |
| `ARCH-01` | Monorepo with `backend/`, `frontend/`, `docs/`, `ops/` | **Approved** | Simplifies atomic commits and shared contracts across 3 frontends and 1 API. |
| `SEC-01` | Server-side Tenant Membership verification via `X-Tenant-ID` header | **Approved** | Works seamlessly on local ports (`4200-4202`) while enforcing strict DB membership checks. |
| `DOM-01` | Base Currency `USD` (`0.01`) + Display/Secondary `KHR` (nearest `100` Riel) | **Approved** | Matches standard Cambodian commercial printing business practices. |
| `DOM-02` | Clearly-labeled Mock Payment + Manual Bank/KHQR Transfer verification for MVP | **Approved** | Enables end-to-end subscription lifecycle testing before commercial bank gateway contracts. |
| `LIC-01` | Optional USB Hardware License Mechanism | **Deferred** | Deferred until core SaaS MVP is complete and explicitly requested. |