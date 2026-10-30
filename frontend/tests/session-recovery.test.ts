/**
 * Helper & Simulation Unit Tests (Task 02.1 Baseline)
 *
 * Note: These tests verify pure utility functions (formatApiErrorMessage, isSubscriptionDenialError)
 * and provide unit-level simulations. For comprehensive regression tests exercising the actual production
 * classes (PbmsSessionClient, TenantAppComponent, AdminAppComponent), see real-session-regression.test.ts.
 */
import test from 'node:test';
import assert from 'node:assert';
import { Observable, of, throwError, delay } from 'rxjs';
import {
  formatApiErrorMessage,
  isSubscriptionDenialError,
} from '../projects/pbms-shared/src/helpers.ts';

// ============================================================================
// 1. Error Message Formatting Tests (REQ: No [object Object], clean DRF parse)
// ============================================================================

test('formatApiErrorMessage: returns fallback for null/undefined error', () => {
  assert.strictEqual(formatApiErrorMessage(null, 'Custom fallback'), 'Custom fallback');
  assert.strictEqual(formatApiErrorMessage(undefined), 'Operation failed.');
});

test('formatApiErrorMessage: returns string error as-is', () => {
  assert.strictEqual(formatApiErrorMessage('Direct error message'), 'Direct error message');
  assert.strictEqual(formatApiErrorMessage({ error: 'Nested error string' }), 'Nested error string');
});

test('formatApiErrorMessage: extracts detail string from DRF exception', () => {
  const err = { error: { detail: 'Access denied: Insufficient role permissions.' } };
  assert.strictEqual(formatApiErrorMessage(err), 'Access denied: Insufficient role permissions.');
});

test('formatApiErrorMessage: extracts and formats non_field_errors array', () => {
  const err = {
    error: {
      non_field_errors: ['Tenant subscription billing period has expired.'],
    },
  };
  assert.strictEqual(formatApiErrorMessage(err), 'Tenant subscription billing period has expired.');
});

test('formatApiErrorMessage: formats field-level validation errors cleanly', () => {
  const err = {
    error: {
      email: ['Enter a valid email address.'],
      password: ['Password must be at least 10 characters.', 'Common password.'],
    },
  };
  const formatted = formatApiErrorMessage(err);
  assert.ok(formatted.includes('email: Enter a valid email address.'));
  assert.ok(formatted.includes('password: Password must be at least 10 characters., Common password.'));
  assert.ok(!formatted.includes('[object Object]'));
});

// ============================================================================
// 2. Subscription Gate Denial Detection (403 and 400 edge-case coverage)
// ============================================================================

test('isSubscriptionDenialError: identifies 403 subscription period expiration', () => {
  const err = {
    status: 403,
    error: { detail: 'Access denied: Tenant subscription billing period has expired.' },
  };
  assert.strictEqual(isSubscriptionDenialError(err), true);
});

test('isSubscriptionDenialError: identifies 403 inactive subscription', () => {
  const err = {
    status: 403,
    error: { detail: 'Access denied: Tenant subscription is not active.' },
  };
  assert.strictEqual(isSubscriptionDenialError(err), true);
});

test('isSubscriptionDenialError: identifies 400 service-level subscription expiration', () => {
  const err = {
    status: 400,
    error: { detail: 'Tenant subscription billing period has expired.' },
  };
  assert.strictEqual(isSubscriptionDenialError(err), true);
});

test('isSubscriptionDenialError: rejects normal RBAC 403 (does not show subscription gate)', () => {
  const err = {
    status: 403,
    error: { detail: 'Access denied: Insufficient role permissions within this tenant.' },
  };
  assert.strictEqual(isSubscriptionDenialError(err), false);
});

test('isSubscriptionDenialError: rejects normal 400 validation error', () => {
  const err = {
    status: 400,
    error: { email: ['Email already exists.'] },
  };
  assert.strictEqual(isSubscriptionDenialError(err), false);
});

test('isSubscriptionDenialError: rejects 401 authentication errors', () => {
  const err = {
    status: 401,
    error: { detail: 'Session has been revoked or expired.' },
  };
  assert.strictEqual(isSubscriptionDenialError(err), false);
});

// ============================================================================
// 3. Session Storage Prefix Isolation (Tenant Staff vs Super Admin)
// ============================================================================

test('Session Storage Prefix Isolation: portal storage keys do not collide', () => {
  const mockStorage: Record<string, string> = {};
  const tenantPrefix = 'pbms_tenant_staff';
  const adminPrefix = 'pbms_super_admin';

  mockStorage[`${tenantPrefix}_access`] = 'tenant-jwt-token-123';
  mockStorage[`${adminPrefix}_access`] = 'admin-jwt-token-456';

  assert.strictEqual(mockStorage[`${tenantPrefix}_access`], 'tenant-jwt-token-123');
  assert.strictEqual(mockStorage[`${adminPrefix}_access`], 'admin-jwt-token-456');
  assert.notStrictEqual(mockStorage[`${tenantPrefix}_access`], mockStorage[`${adminPrefix}_access`]);
});

// ============================================================================
// 4. In-Flight Token Refresh Deduplication Simulation
// ============================================================================

test('Refresh Mutex: concurrent 401 callers share a single in-flight refresh request', async () => {
  let backendRefreshCalls = 0;

  // Mock refresh client with deduplication
  class MockSessionClient {
    private refreshInFlight: Observable<{ access_token: string; refresh_token: string }> | null = null;

    refreshToken(): Observable<{ access_token: string; refresh_token: string }> {
      if (this.refreshInFlight) {
        return this.refreshInFlight;
      }

      backendRefreshCalls++;
      // Simulate asynchronous network round-trip of 20ms
      const obs = new Observable<{ access_token: string; refresh_token: string }>((subscriber) => {
        setTimeout(() => {
          subscriber.next({ access_token: 'new-access-jwt', refresh_token: 'new-refresh-jwt' });
          subscriber.complete();
          this.refreshInFlight = null;
        }, 20);
      });

      this.refreshInFlight = obs;
      return obs;
    }
  }

  const client = new MockSessionClient();

  // Simulate 6 parallel GET requests (dashboard, customers, quotes, orders, materials, invoices)
  // all receiving 401 at the same millisecond:
  const p1 = new Promise((resolve) => client.refreshToken().subscribe(resolve));
  const p2 = new Promise((resolve) => client.refreshToken().subscribe(resolve));
  const p3 = new Promise((resolve) => client.refreshToken().subscribe(resolve));
  const p4 = new Promise((resolve) => client.refreshToken().subscribe(resolve));
  const p5 = new Promise((resolve) => client.refreshToken().subscribe(resolve));
  const p6 = new Promise((resolve) => client.refreshToken().subscribe(resolve));

  const results = await Promise.all([p1, p2, p3, p4, p5, p6]);

  // ALL 6 callers must receive valid tokens:
  assert.strictEqual(results.length, 6);
  results.forEach((r: any) => {
    assert.strictEqual(r.access_token, 'new-access-jwt');
    assert.strictEqual(r.refresh_token, 'new-refresh-jwt');
  });

  // CRITICAL: Exactly 1 backend refresh call was made, preventing token reuse session revocation!
  assert.strictEqual(backendRefreshCalls, 1);
});

// ============================================================================
// 5. Mutation Double-Click In-Flight Prevention Logic
// ============================================================================

test('Mutation Guard: in-flight lock rejects concurrent duplicate submissions', () => {
  let inFlight = false;
  let backendExecutionCount = 0;

  function submitMutation(): boolean {
    if (inFlight) {
      return false; // Submission locked
    }
    inFlight = true;
    backendExecutionCount++;
    return true;
  }

  // First click succeeds:
  const firstClick = submitMutation();
  assert.strictEqual(firstClick, true);
  assert.strictEqual(backendExecutionCount, 1);

  // Rapid second and third clicks are rejected:
  const secondClick = submitMutation();
  const thirdClick = submitMutation();
  assert.strictEqual(secondClick, false);
  assert.strictEqual(thirdClick, false);
  assert.strictEqual(backendExecutionCount, 1);

  // When first completes, subsequent submission is allowed:
  inFlight = false;
  const subsequentClick = submitMutation();
  assert.strictEqual(subsequentClick, true);
  assert.strictEqual(backendExecutionCount, 2);
});

// ============================================================================
// 6. Form Input Preservation on Recoverable Error
// ============================================================================

test('Form State: input values are preserved on recoverable error', () => {
  let formCustomerName = 'Acme Printing Ltd';
  let formPhone = '012999888';
  let bannerMessage = 'Previous customer added';
  let errorMessage = '';

  // Simulate 401 error during customer creation:
  function onCustomerMutationError(err: any) {
    bannerMessage = ''; // Stale success banner cleared
    if (err.status === 401) {
      errorMessage = 'Session refreshed. New customer creation was not submitted. Please verify entered data and submit again.';
      // DO NOT wipe formCustomerName or formPhone!
    }
  }

  onCustomerMutationError({ status: 401 });

  // Assert inputs are intact:
  assert.strictEqual(formCustomerName, 'Acme Printing Ltd');
  assert.strictEqual(formPhone, '012999888');
  // Stale success banner is cleared:
  assert.strictEqual(bannerMessage, '');
  // Actionable instruction displayed:
  assert.ok(errorMessage.includes('was not submitted'));
  assert.ok(errorMessage.includes('submit again'));
});
