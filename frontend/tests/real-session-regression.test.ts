import test from 'node:test';
import assert from 'node:assert';
import '@angular/compiler';
import { Injector, runInInjectionContext } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of, throwError, delay, Subject } from 'rxjs';
import {
  API_BASE_URL,
  PBMS_LANG_STORAGE_KEY,
  PbmsI18nService,
  PbmsSessionClient,
  UserProfile,
} from '../projects/pbms-shared/src/public-api';
import {
  formatApiErrorMessage,
  isSubscriptionDenialError,
} from '../projects/pbms-shared/src/helpers';
import { AppComponent as TenantAppComponent } from '../projects/tenant-workspace/src/app/app.component';
import { AppComponent as AdminAppComponent } from '../projects/super-admin/src/app/app.component';

// ============================================================================
// Environment Shim: SessionStorage in Node.js
// ============================================================================
function setupMockSessionStorage(): void {
  const store = new Map<string, string>();
  globalThis.sessionStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => store.set(k, String(v)),
    removeItem: (k: string) => store.delete(k),
    clear: () => store.clear(),
    get length() {
      return store.size;
    },
    key: (i: number) => Array.from(store.keys())[i] ?? null,
  };
}

setupMockSessionStorage();

// ============================================================================
// SECTION A: Real PbmsSessionClient Tests
// ============================================================================

test('Scenario A1: Real PbmsSessionClient deduplicates concurrent 401 refresh calls', async () => {
  sessionStorage.clear();
  const prefix = 'pbms_tenant_staff';
  sessionStorage.setItem(`${prefix}_access`, 'old-access-jwt');
  sessionStorage.setItem(`${prefix}_refresh`, 'valid-refresh-jwt');

  let refreshCallCount = 0;
  let lastRequestBody: any = null;
  let lastRequestUrl = '';

  const mockHttp = {
    post: (url: string, body: any) => {
      lastRequestUrl = url;
      lastRequestBody = body;
      if (url.includes('/auth/refresh/')) {
        refreshCallCount++;
        // Simulate asynchronous network flight of 25ms
        return of({
          access_token: 'new-access-jwt-123',
          refresh_token: 'new-refresh-jwt-456',
        }).pipe(delay(25));
      }
      return of({});
    },
  } as unknown as HttpClient;

  const client = new PbmsSessionClient(mockHttp);

  // Invoke real refreshToken() concurrently from 6 callers
  const p1 = new Promise((resolve, reject) => client.refreshToken(prefix).subscribe({ next: resolve, error: reject }));
  const p2 = new Promise((resolve, reject) => client.refreshToken(prefix).subscribe({ next: resolve, error: reject }));
  const p3 = new Promise((resolve, reject) => client.refreshToken(prefix).subscribe({ next: resolve, error: reject }));
  const p4 = new Promise((resolve, reject) => client.refreshToken(prefix).subscribe({ next: resolve, error: reject }));
  const p5 = new Promise((resolve, reject) => client.refreshToken(prefix).subscribe({ next: resolve, error: reject }));
  const p6 = new Promise((resolve, reject) => client.refreshToken(prefix).subscribe({ next: resolve, error: reject }));

  const results = await Promise.all([p1, p2, p3, p4, p5, p6]);

  // 1. All 6 callers must receive the exact new tokens
  assert.strictEqual(results.length, 6);
  for (const res of results as any[]) {
    assert.strictEqual(res.access_token, 'new-access-jwt-123');
    assert.strictEqual(res.refresh_token, 'new-refresh-jwt-456');
  }

  // 2. CRITICAL: Exactly 1 HTTP POST to the backend refresh endpoint
  assert.strictEqual(refreshCallCount, 1);
  assert.strictEqual(lastRequestUrl, `${API_BASE_URL}/auth/refresh/`);
  assert.deepStrictEqual(lastRequestBody, { refresh_token: 'valid-refresh-jwt' });

  // 3. Storage updated with new tokens
  assert.strictEqual(sessionStorage.getItem(`${prefix}_access`), 'new-access-jwt-123');
  assert.strictEqual(sessionStorage.getItem(`${prefix}_refresh`), 'new-refresh-jwt-456');

  // 4. In-flight map cleaned up: a subsequent call starts a fresh request
  const p7 = new Promise((resolve, reject) => client.refreshToken(prefix).subscribe({ next: resolve, error: reject }));
  await p7;
  assert.strictEqual(refreshCallCount, 2);
});

test('Scenario A2: Portal Storage Isolation across Tenant and Super Admin', () => {
  sessionStorage.clear();
  const tenantPrefix = 'pbms_tenant_staff';
  const adminPrefix = 'pbms_super_admin';

  sessionStorage.setItem(`${tenantPrefix}_access`, 'tenant-jwt-token');
  sessionStorage.setItem(`${tenantPrefix}_refresh`, 'tenant-refresh-token');
  sessionStorage.setItem(`${adminPrefix}_access`, 'admin-jwt-token');
  sessionStorage.setItem(`${adminPrefix}_refresh`, 'admin-refresh-token');

  const mockHttp = { post: () => of({ access_token: 'new-t', refresh_token: 'new-r' }) } as unknown as HttpClient;
  const client = new PbmsSessionClient(mockHttp);

  // Clearing tenant storage must NOT affect super admin storage
  client.clearStorage(tenantPrefix);
  assert.strictEqual(sessionStorage.getItem(`${tenantPrefix}_access`), null);
  assert.strictEqual(sessionStorage.getItem(`${tenantPrefix}_refresh`), null);
  assert.strictEqual(sessionStorage.getItem(`${adminPrefix}_access`), 'admin-jwt-token');
  assert.strictEqual(sessionStorage.getItem(`${adminPrefix}_refresh`), 'admin-refresh-token');
});

test('Scenario A3: Authentication Rejection (401, 403, 400) clears storage', async () => {
  sessionStorage.clear();
  const prefix = 'pbms_tenant_staff';

  const testRejection = async (statusCode: number) => {
    sessionStorage.setItem(`${prefix}_access`, 'token-to-purge');
    sessionStorage.setItem(`${prefix}_refresh`, 'refresh-to-purge');

    const mockHttp = {
      post: () => throwError(() => ({ status: statusCode, error: { detail: 'Token invalid' } })),
    } as unknown as HttpClient;

    const client = new PbmsSessionClient(mockHttp);

    try {
      await new Promise((resolve, reject) => client.refreshToken(prefix).subscribe({ next: resolve, error: reject }));
      assert.fail(`Expected HTTP ${statusCode} to throw`);
    } catch (err: any) {
      assert.strictEqual(err.status, statusCode);
    }

    // Storage must be cleared on authentication rejection
    assert.strictEqual(sessionStorage.getItem(`${prefix}_access`), null);
    assert.strictEqual(sessionStorage.getItem(`${prefix}_refresh`), null);
  };

  await testRejection(401);
  await testRejection(403);
  await testRejection(400);
});

test('Scenario A4: Transient Failures (Network drop status 0, 500) preserve storage', async () => {
  sessionStorage.clear();
  const prefix = 'pbms_tenant_staff';

  const testTransient = async (statusCode: number) => {
    sessionStorage.setItem(`${prefix}_access`, 'preserved-access-token');
    sessionStorage.setItem(`${prefix}_refresh`, 'preserved-refresh-token');

    const mockHttp = {
      post: () => throwError(() => ({ status: statusCode, message: 'Network disconnected' })),
    } as unknown as HttpClient;

    const client = new PbmsSessionClient(mockHttp);

    try {
      await new Promise((resolve, reject) => client.refreshToken(prefix).subscribe({ next: resolve, error: reject }));
      assert.fail(`Expected HTTP ${statusCode} to throw`);
    } catch (err: any) {
      assert.strictEqual(err.status, statusCode);
    }

    // Storage must NOT be deleted on transient network / server errors
    assert.strictEqual(sessionStorage.getItem(`${prefix}_access`), 'preserved-access-token');
    assert.strictEqual(sessionStorage.getItem(`${prefix}_refresh`), 'preserved-refresh-token');
  };

  await testTransient(0);
  await testTransient(500);
  await testTransient(502);
});

test('Scenario A5 & A6: Logout contract passes refresh_token and clears storage', async () => {
  sessionStorage.clear();
  const prefix = 'pbms_tenant_staff';
  sessionStorage.setItem(`${prefix}_access`, 'access-123');
  sessionStorage.setItem(`${prefix}_refresh`, 'refresh-456');

  let logoutBody: any = null;
  const mockHttp = {
    post: (_url: string, body: any) => {
      logoutBody = body;
      return of({ status: 'revoked' });
    },
  } as unknown as HttpClient;

  const client = new PbmsSessionClient(mockHttp);
  await new Promise((resolve) => client.logout(prefix).subscribe({ next: resolve, error: resolve }));

  assert.deepStrictEqual(logoutBody, { refresh_token: 'refresh-456' });
  assert.strictEqual(sessionStorage.getItem(`${prefix}_access`), null);
  assert.strictEqual(sessionStorage.getItem(`${prefix}_refresh`), null);
});

// ============================================================================
// SECTION B: Real Tenant Workspace Component Mutation Behavior
// ============================================================================

function createTenantWorkspaceHarness(options: {
  httpPostHandler?: (url: string, body: any) => Observable<any>;
  httpGetHandler?: (url: string) => Observable<any>;
  refreshTokenHandler?: () => Observable<any>;
}) {
  const mockHttp = {
    post: options.httpPostHandler ?? (() => of({})),
    get: options.httpGetHandler ?? (() => of([])),
    patch: () => of({}),
  } as unknown as HttpClient;

  const sessionClient = new PbmsSessionClient(mockHttp);
  if (options.refreshTokenHandler) {
    sessionClient.refreshToken = options.refreshTokenHandler as any;
  }

  const injector = Injector.create({
    providers: [
      { provide: PbmsI18nService, useClass: PbmsI18nService },
      { provide: PbmsSessionClient, useValue: sessionClient },
      { provide: HttpClient, useValue: mockHttp },
    ],
  });

  const component = runInInjectionContext(injector, () => new TenantAppComponent());
  return { component, sessionClient };
}

test('Scenario B1: Customer creation 401 recovers without auto-replay & preserves form input', () => {
  sessionStorage.clear();
  let customerPostCalls = 0;
  let refreshCalls = 0;

  const { component } = createTenantWorkspaceHarness({
    httpPostHandler: (url: string) => {
      if (url.includes('/tenant/customers/')) {
        customerPostCalls++;
        return throwError(() => ({ status: 401, error: { detail: 'Token expired' } }));
      }
      return of({});
    },
    refreshTokenHandler: () => {
      refreshCalls++;
      return of({ access_token: 'refreshed-access', refresh_token: 'refreshed-refresh' });
    },
  });

  // Pre-condition: populate form and set a stale banner
  component.custName = 'Sokha Printing Shop';
  component.custCompany = 'Sokha Group';
  component.custPhone = '012999888';
  component.bannerMsg.set('Previous customer created successfully');

  // Trigger real mutation method
  component.createCustomer();

  // Assertions:
  // 1. Customer endpoint called exactly once (NO blind automatic replay)
  assert.strictEqual(customerPostCalls, 1);
  // 2. Refresh was initiated
  assert.strictEqual(refreshCalls, 1);
  // 3. User form input is preserved
  assert.strictEqual(component.custName, 'Sokha Printing Shop');
  assert.strictEqual(component.custCompany, 'Sokha Group');
  assert.strictEqual(component.custPhone, '012999888');
  // 4. Stale success banner cleared
  assert.strictEqual(component.bannerMsg(), '');
  // 5. Actionable guidance displayed to user
  assert.ok(component.errorMsg().includes('Session refreshed'));
  assert.ok(component.errorMsg().includes('was not submitted'));
  assert.ok(component.errorMsg().includes('submit again'));
  // 6. In-flight guard released
  assert.strictEqual(component.submittingCustomer(), false);
});

test('Scenario B2: Double-click mutation prevention locks in-flight submissions', () => {
  let customerPostCalls = 0;
  const pendingSubject = new Subject<any>();

  const { component } = createTenantWorkspaceHarness({
    httpPostHandler: (url: string) => {
      if (url.includes('/tenant/customers/')) {
        customerPostCalls++;
        return pendingSubject.asObservable();
      }
      return of({});
    },
  });

  component.custName = 'Acme Printing';
  component.custPhone = '011222333';

  // First click: initiates request
  component.createCustomer();
  assert.strictEqual(customerPostCalls, 1);
  assert.strictEqual(component.submittingCustomer(), true);

  // Rapid second and third clicks: MUST BE REJECTED by in-flight guard
  component.createCustomer();
  component.createCustomer();
  assert.strictEqual(customerPostCalls, 1);

  // Resolve pending request
  pendingSubject.next({ id: 'c-1', name: 'Acme Printing' });
  pendingSubject.complete();

  // Guard must be released
  assert.strictEqual(component.submittingCustomer(), false);
  assert.strictEqual(component.bannerMsg(), 'Customer added successfully.');

  // Subsequent deliberate click now allowed
  component.createCustomer();
  assert.strictEqual(customerPostCalls, 2);
});

test('Scenario B3: Successful mutation clears inputs and displays banner', () => {
  const { component } = createTenantWorkspaceHarness({
    httpPostHandler: (url: string) => of({ id: 'c-100', name: 'Sokha' }),
  });

  component.custName = 'Sokha';
  component.custCompany = 'Sokha Co';
  component.custPhone = '099112233';

  component.createCustomer();

  assert.strictEqual(component.custName, '');
  assert.strictEqual(component.custCompany, '');
  assert.strictEqual(component.custPhone, '');
  assert.strictEqual(component.bannerMsg(), 'Customer added successfully.');
  assert.strictEqual(component.submittingCustomer(), false);
});

test('Scenario B4: Mutation 401 with failed refresh logs out cleanly', () => {
  const { component } = createTenantWorkspaceHarness({
    httpPostHandler: () => throwError(() => ({ status: 401 })),
    refreshTokenHandler: () => throwError(() => ({ status: 401, error: { detail: 'Session expired' } })),
  });

  component.user.set({
    id: 'u-1',
    email: 'test@shop.com',
    full_name: 'Test User',
    platform_role: 'TENANT_USER',
    preferred_language: 'km',
    memberships: [],
  });

  component.createCustomer();

  // User session cleared
  assert.strictEqual(component.user(), null);
  assert.strictEqual(component.errorMsg(), 'Session expired. Please sign in again.');
  assert.strictEqual(component.submittingCustomer(), false);
  assert.strictEqual(component.bannerMsg(), '');
});

// ============================================================================
// SECTION C: Real Super Admin Mutation & In-Flight Guard
// ============================================================================

test('Scenario C1: Super Admin toggleTenantStatus double-click lock and 401 recovery', () => {
  let statusCalls = 0;
  let refreshCalls = 0;

  const mockHttp = {
    post: (url: string) => {
      if (url.includes('/super-admin/tenants/')) {
        statusCalls++;
        return throwError(() => ({ status: 401, error: { detail: 'Admin token expired' } }));
      }
      return of({});
    },
    get: () => of({}),
  } as unknown as HttpClient;

  const sessionClient = new PbmsSessionClient(mockHttp);
  sessionClient.refreshToken = (() => {
    refreshCalls++;
    return of({ access_token: 'admin-refreshed', refresh_token: 'admin-refresh' });
  }) as any;

  const injector = Injector.create({
    providers: [
      { provide: PbmsI18nService, useClass: PbmsI18nService },
      { provide: PbmsSessionClient, useValue: sessionClient },
      { provide: HttpClient, useValue: mockHttp },
    ],
  });

  const adminComp = runInInjectionContext(injector, () => new AdminAppComponent());
  adminComp.user.set({
    id: 'admin-1',
    email: 'admin@pbms.local',
    full_name: 'Platform Admin',
    platform_role: 'SUPER_ADMIN',
    preferred_language: 'en',
    memberships: [],
  });

  // Call mutation
  adminComp.toggleTenantStatus('tenant-uuid-1', 'SUSPEND');

  // Assertions:
  assert.strictEqual(statusCalls, 1);
  assert.strictEqual(refreshCalls, 1);
  assert.ok(adminComp.errorMsg().includes('Session refreshed. Tenant status update was not submitted'));
  assert.strictEqual(adminComp.togglingTenantId(), null);
});

// ============================================================================
// SECTION D: Read Recovery & Error Distinction Invariants
// ============================================================================

test('Scenario D1: Read recovery on fetchTenantContextAndLoad', () => {
  let contextCalls = 0;
  let refreshCalls = 0;

  const { component } = createTenantWorkspaceHarness({
    httpGetHandler: (url: string) => {
      if (url.includes('/tenant/context/')) {
        contextCalls++;
        if (contextCalls === 1) {
          return throwError(() => ({ status: 401 }));
        }
        return of({
          tenant_id: 't-123',
          tenant_name: 'Sokha Color Printing',
          tenant_slug: 'sokha-color',
          role: 'TENANT_OWNER',
          base_currency: 'USD',
          khr_exchange_rate: '4100.00',
          tax_rate_percent: '10.00',
        });
      }
      return of([]);
    },
    refreshTokenHandler: () => {
      refreshCalls++;
      return of({ access_token: 'new-acc', refresh_token: 'new-ref' });
    },
  });

  component.fetchTenantContextAndLoad();

  // Verified:
  assert.strictEqual(refreshCalls, 1);
  assert.strictEqual(contextCalls, 2);
  assert.strictEqual(component.currentRole(), 'TENANT_OWNER');
  assert.strictEqual(component.isOwner(), true);
  assert.strictEqual(component.activeTenantName(), 'Sokha Color Printing');
});

test('Scenario D2: Error Distinctions (RBAC 403 vs Subscription 403/400 vs Network 0)', () => {
  let refreshCalls = 0;
  const { component } = createTenantWorkspaceHarness({
    refreshTokenHandler: () => {
      refreshCalls++;
      return of({});
    },
  });

  // 1. Ordinary RBAC 403 -> errorMsg set, NO refresh, NO subscription banner
  (component as any).handleReadError(
    { status: 403, error: { detail: 'Access denied: Insufficient role permissions.' } },
    'Fallback'
  );
  assert.strictEqual(refreshCalls, 0);
  assert.strictEqual(component.subscriptionGateError(), '');
  assert.strictEqual(component.errorMsg(), 'Access denied: Insufficient role permissions.');

  // 2. Subscription 403 -> subscriptionGateError set, NO refresh
  (component as any).handleReadError(
    { status: 403, error: { detail: 'Access denied: Tenant subscription billing period has expired.' } },
    'Fallback'
  );
  assert.strictEqual(refreshCalls, 0);
  assert.ok(component.subscriptionGateError().includes('subscription billing period has expired'));

  // 3. Subscription 400 service-level -> subscriptionGateError set
  (component as any).handleReadError(
    { status: 400, error: { detail: 'Tenant subscription billing period has expired.' } },
    'Fallback'
  );
  assert.ok(component.subscriptionGateError().includes('subscription billing period has expired'));

  // 4. Transient status 0 network error -> errorMsg set, NO logout, NO refresh
  (component as any).handleReadError(
    { status: 0, message: 'Http failure response for (unknown url): 0 Unknown Error' },
    'Network failure'
  );
  assert.strictEqual(refreshCalls, 0);
  assert.ok(component.errorMsg().includes('Http failure response'));
});

// ============================================================================
// SECTION E: Pure Helper Tests (formatApiErrorMessage & isSubscriptionDenialError)
// ============================================================================

test('Scenario E1: formatApiErrorMessage formatting', () => {
  assert.strictEqual(formatApiErrorMessage(null, 'Fallback'), 'Fallback');
  assert.strictEqual(formatApiErrorMessage('Direct error'), 'Direct error');
  assert.strictEqual(formatApiErrorMessage({ error: { detail: 'DRF Detail' } }), 'DRF Detail');
  assert.strictEqual(
    formatApiErrorMessage({ error: { email: ['Invalid email'], phone: ['Required'] } }),
    'email: Invalid email | phone: Required'
  );
  assert.strictEqual(
    formatApiErrorMessage({ error: { non_field_errors: ['Non-field error string'] } }),
    'Non-field error string'
  );
});

test('Scenario E2: isSubscriptionDenialError detection', () => {
  assert.strictEqual(isSubscriptionDenialError({ status: 403, error: { detail: 'subscription expired' } }), true);
  assert.strictEqual(isSubscriptionDenialError({ status: 400, error: { detail: 'subscription billing period has expired' } }), true);
  assert.strictEqual(isSubscriptionDenialError({ status: 403, error: { detail: 'unauthorized role' } }), false);
  assert.strictEqual(isSubscriptionDenialError({ status: 401, error: { detail: 'expired token' } }), false);
});

// ============================================================================
// SECTION F: PbmsI18nService Language Preference Persistence (Task 03D)
// ============================================================================

function createMockStorage(initial?: Record<string, string>, shouldThrow = false) {
  const store = new Map<string, string>(Object.entries(initial ?? {}));
  return {
    store,
    storage: {
      getItem: (k: string) => {
        if (shouldThrow) throw new Error('SecurityError: Access is denied');
        return store.get(k) ?? null;
      },
      setItem: (k: string, v: string) => {
        if (shouldThrow) throw new Error('QuotaExceededError');
        store.set(k, String(v));
      },
      removeItem: (k: string) => {
        if (shouldThrow) throw new Error('SecurityError');
        store.delete(k);
      },
      clear: () => store.clear(),
      get length() {
        return store.size;
      },
      key: (i: number) => Array.from(store.keys())[i] ?? null,
    } as Storage,
  };
}

test('Scenario F1: Default Khmer when no preference exists', () => {
  const { storage } = createMockStorage();
  const originalWindow = (globalThis as any).window;
  (globalThis as any).window = { localStorage: storage };

  try {
    const service = new PbmsI18nService();
    assert.strictEqual(service.lang(), 'km');
    assert.strictEqual(service.t('សួស្ដី', 'Hello'), 'សួស្ដី');
  } finally {
    (globalThis as any).window = originalWindow;
  }
});

test('Scenario F2: Restoring English from valid persisted preference', () => {
  const { storage } = createMockStorage({ [PBMS_LANG_STORAGE_KEY]: 'en' });
  const originalWindow = (globalThis as any).window;
  (globalThis as any).window = { localStorage: storage };

  try {
    const service = new PbmsI18nService();
    assert.strictEqual(service.lang(), 'en');
    assert.strictEqual(service.t('សួស្ដី', 'Hello'), 'Hello');
  } finally {
    (globalThis as any).window = originalWindow;
  }
});

test('Scenario F3: Ignoring invalid stored values and falling back to Khmer', () => {
  for (const invalid of ['fr', 'zh', 'invalid', 'null', '']) {
    const { storage } = createMockStorage({ [PBMS_LANG_STORAGE_KEY]: invalid });
    const originalWindow = (globalThis as any).window;
    (globalThis as any).window = { localStorage: storage };

    try {
      const service = new PbmsI18nService();
      assert.strictEqual(service.lang(), 'km', `Expected fallback to 'km' for stored value '${invalid}'`);
    } finally {
      (globalThis as any).window = originalWindow;
    }
  }
});

test('Scenario F4: Persisting a language toggle', () => {
  const { storage, store } = createMockStorage();
  const originalWindow = (globalThis as any).window;
  (globalThis as any).window = { localStorage: storage };

  try {
    const service = new PbmsI18nService();
    assert.strictEqual(service.lang(), 'km');

    // Toggle 1: km -> en
    service.toggleLanguage();
    assert.strictEqual(service.lang(), 'en');
    assert.strictEqual(store.get(PBMS_LANG_STORAGE_KEY), 'en');
    assert.strictEqual(service.t('សម្រង់តម្លៃ', 'Quotations'), 'Quotations');

    // Toggle 2: en -> km
    service.toggleLanguage();
    assert.strictEqual(service.lang(), 'km');
    assert.strictEqual(store.get(PBMS_LANG_STORAGE_KEY), 'km');
    assert.strictEqual(service.t('សម្រង់តម្លៃ', 'Quotations'), 'សម្រង់តម្លៃ');
  } finally {
    (globalThis as any).window = originalWindow;
  }
});

test('Scenario F5: Safe fallback to Khmer when localStorage throws', () => {
  const { storage } = createMockStorage({}, true); // throws on access
  const originalWindow = (globalThis as any).window;
  (globalThis as any).window = { localStorage: storage };

  try {
    const service = new PbmsI18nService();
    assert.strictEqual(service.lang(), 'km');

    // toggle should not throw even if setItem throws
    assert.doesNotThrow(() => service.toggleLanguage());
    assert.strictEqual(service.lang(), 'en');
  } finally {
    (globalThis as any).window = originalWindow;
  }
});
