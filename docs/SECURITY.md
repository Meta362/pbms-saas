# PBMS SaaS — Security Architecture & Controls

## 1. Password Security (`REQ-AUTH-01`)
- **Algorithm:** `Argon2id` (`django.contrib.auth.hashers.Argon2PasswordHasher` powered by `argon2-cffi`).
- **Policy:** Minimum 10 characters, checked against common password lists and user attribute similarity.
- **Protection:** Login and password recovery endpoints are rate-limited (`ScopedRateThrottle`) to mitigate credential stuffing and brute-force attacks.

## 2. JWT & PostgreSQL Session State (`REQ-AUTH-02`, `REQ-AUTH-03`, `REQ-AUTH-04`)
- **Access Token:** Short-lived (15 minutes), stateless JWT containing `user_id`, `session_id` (`AuthSession.id`), `jti`, and `exp`.
- **Refresh Token Rotation:**
  1. On login, an `AuthSession` row is created in PostgreSQL storing the SHA-256 hash of the initial Refresh Token's `jti` (`current_refresh_jti_hash`).
  2. On `/api/v1/auth/refresh/`, the server locks the `AuthSession` row (`SELECT ... FOR UPDATE` inside `transaction.atomic()`).
  3. If the incoming token's `jti` hash matches `current_refresh_jti_hash`:
     - `previous_refresh_jti_hash` is set to `current_refresh_jti_hash`.
     - A new Refresh Token and Access Token are generated; `current_refresh_jti_hash` is updated to the new `jti` hash.
  4. **Reuse Detection:** If the incoming token's `jti` hash matches `previous_refresh_jti_hash` (or does not match `current_refresh_jti_hash` for an active session):
     - The server immediately sets `AuthSession.is_revoked = True`, `revoked_reason = 'REFRESH_TOKEN_REUSE_DETECTED'`.
     - Writes a `CRITICAL` `AuditEvent` record.
     - Returns `401 Unauthorized`.
- **Immediate Session Revocation:** Every authenticated API request verifies that the session/user is active, and logout/disablement marks `AuthSession.is_revoked = True`.

## 3. Tenant Isolation & IDOR Prevention (`REQ-RBAC-02`, `REQ-RBAC-03`)
- Client-supplied `tenant_id` values in JSON payloads are ignored/stripped by serializers.
- Tenant context is resolved exclusively from the `X-Tenant-ID` request header validated against an active `TenantMembership` for `request.user`.
- Object-level queries always scope via `.filter(tenant=request.tenant)`.

## 4. Secrets, CORS & File Upload Controls
- Zero secrets in source code; all sensitive keys are read from environment variables.
- CORS is restricted strictly to configured origins (`CORS_ALLOWED_ORIGINS`).
- Uploaded artwork metadata validates file extensions, MIME types, and maximum file size, storing files outside public executable paths with randomized UUID filenames.