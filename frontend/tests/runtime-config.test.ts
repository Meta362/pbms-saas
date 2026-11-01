import test from 'node:test';
import assert from 'node:assert';
import '@angular/compiler';
import {
  validateUrl,
  getPbmsRuntimeConfig,
  isProductionEnvironment,
  isLocalDevelopmentHostname,
  isLocalhostUrl,
  getApiBaseUrl,
  getPortalUrl,
  PbmsConfigurationError,
  PbmsRuntimeConfig
} from '../projects/pbms-shared/src/public-api.ts';

function setMockWindow(mockWin: any) {
  (global as any).window = mockWin;
}

function clearMockWindow() {
  delete (global as any).window;
}

// 1. URL Validation & Whitespace Normalization
test('Config Validation: validateUrl trims whitespace and trailing slashes', () => {
  assert.strictEqual(
    validateUrl('  https://api.example.com/api/v1///  ', 'API_BASE_URL'),
    'https://api.example.com/api/v1'
  );
  assert.strictEqual(
    validateUrl('  http://localhost:8000/api/v1/  ', 'API_BASE_URL'),
    'http://localhost:8000/api/v1'
  );
  assert.strictEqual(
    validateUrl('  https://app.example.com/  ', 'TENANT_WORKSPACE_URL'),
    'https://app.example.com'
  );
});

// 2. Relative Path Support for Reverse Proxy
test('Config Validation: validateUrl accepts valid relative paths for reverse proxies', () => {
  assert.strictEqual(validateUrl('/api/v1', 'API_BASE_URL'), '/api/v1');
  assert.strictEqual(validateUrl('/api/v1/', 'API_BASE_URL'), '/api/v1');
  assert.strictEqual(validateUrl('/app', 'TENANT_WORKSPACE_URL'), '/app');
});

// 3. Null / Undefined / Empty Handling
test('Config Validation: validateUrl returns null for null, undefined, or empty strings', () => {
  assert.strictEqual(validateUrl(null, 'API_BASE_URL'), null);
  assert.strictEqual(validateUrl(undefined, 'API_BASE_URL'), null);
  assert.strictEqual(validateUrl('', 'API_BASE_URL'), null);
  assert.strictEqual(validateUrl('   ', 'API_BASE_URL'), null);
});

// 4. Protocol-Relative URL Rejection
test('Config Validation: validateUrl rejects protocol-relative URLs (security protection)', () => {
  assert.throws(
    () => validateUrl('//malicious-domain.com/api', 'API_BASE_URL'),
    (err: any) => err instanceof PbmsConfigurationError && err.message.includes('Protocol-relative')
  );
});

// 5. Unsupported Protocol Rejection
test('Config Validation: validateUrl rejects unsupported protocols (e.g. ftp, javascript, file)', () => {
  assert.throws(
    () => validateUrl('javascript:alert(1)', 'API_BASE_URL'),
    (err: any) => err instanceof PbmsConfigurationError
  );
  assert.throws(
    () => validateUrl('ftp://files.example.com', 'API_BASE_URL'),
    (err: any) => err instanceof PbmsConfigurationError && err.message.includes('must use http or https')
  );
  assert.throws(
    () => validateUrl('file:///etc/passwd', 'API_BASE_URL'),
    (err: any) => err instanceof PbmsConfigurationError
  );
});

// 6. Malformed URL Rejection
test('Config Validation: validateUrl rejects malformed URL strings', () => {
  assert.throws(
    () => validateUrl('not a valid url &&&', 'API_BASE_URL'),
    (err: any) => err instanceof PbmsConfigurationError && err.message.includes('Invalid URL')
  );
});

// 7. Local Development Hostname Classification
test('Hostname Classification: correctly identifies local development hosts', () => {
  assert.strictEqual(isLocalDevelopmentHostname('localhost'), true);
  assert.strictEqual(isLocalDevelopmentHostname('127.0.0.1'), true);
  assert.strictEqual(isLocalDevelopmentHostname('::1'), true);
  assert.strictEqual(isLocalDevelopmentHostname('pbms.local'), true);
  assert.strictEqual(isLocalDevelopmentHostname('app.angkorprint.com'), false);
  assert.strictEqual(isLocalDevelopmentHostname('pbms-saas.vercel.app'), false);
});

// 8. Localhost URL Detection
test('Localhost URL Detection: identifies localhost endpoints', () => {
  assert.strictEqual(isLocalhostUrl('http://localhost:8000/api/v1'), true);
  assert.strictEqual(isLocalhostUrl('http://127.0.0.1:8000/api/v1'), true);
  assert.strictEqual(isLocalhostUrl('http://pbms.local:8000/api/v1'), true);
  assert.strictEqual(isLocalhostUrl('https://api.angkorprint.com/api/v1'), false);
  assert.strictEqual(isLocalhostUrl('/api/v1'), false); // Relative paths are same-origin
});

// 9. Local Development Fallback
test('Development Fallback: safely defaults to localhost in development on local hostname', () => {
  setMockWindow({
    __PBMS_CONFIG__: {
      ENV: 'development'
    },
    location: { hostname: 'localhost' }
  });

  try {
    assert.strictEqual(isProductionEnvironment(), false);
    assert.strictEqual(getApiBaseUrl(), 'http://localhost:8000/api/v1');
    assert.strictEqual(getPortalUrl('TENANT_WORKSPACE'), 'http://localhost:4202');
    assert.strictEqual(getPortalUrl('SUPER_ADMIN'), 'http://localhost:4201');
    assert.strictEqual(getPortalUrl('PUBLIC_SITE'), 'http://localhost:4200');
  } finally {
    clearMockWindow();
  }
});

// 10. Fail-Closed Invariant: Stale ENV: 'development' on Production Host
test('Fail-Closed Invariant: Non-local hostname with ENV: "development" is strictly treated as production and blocks localhost fallback', () => {
  setMockWindow({
    __PBMS_CONFIG__: {
      ENV: 'development',
      API_BASE_URL: 'http://localhost:8000/api/v1',
      TENANT_WORKSPACE_URL: 'http://localhost:4202',
      SUPER_ADMIN_URL: 'http://localhost:4201',
      PUBLIC_SITE_URL: 'http://localhost:4200'
    },
    location: { hostname: 'app.angkorprint.com' }
  });

  try {
    // MUST be detected as production despite ENV: 'development'
    assert.strictEqual(isProductionEnvironment(), true);

    // MUST reject localhost API_BASE_URL
    assert.throws(
      () => getApiBaseUrl(),
      (err: any) => err instanceof PbmsConfigurationError && err.message.includes('cannot point to localhost')
    );

    // MUST reject localhost portal URLs
    assert.throws(
      () => getPortalUrl('TENANT_WORKSPACE'),
      (err: any) => err instanceof PbmsConfigurationError && err.message.includes('cannot point to localhost')
    );
  } finally {
    clearMockWindow();
  }
});

// 11. Production Safety: Missing Configuration on Non-Local Host
test('Production Safety: Missing configuration on non-local host rejects silent fallback', () => {
  setMockWindow({
    __PBMS_CONFIG__: {},
    location: { hostname: 'app.angkorprint.com' }
  });

  try {
    assert.strictEqual(isProductionEnvironment(), true);
    assert.throws(
      () => getApiBaseUrl(),
      (err: any) => err instanceof PbmsConfigurationError && err.message.includes('Missing required production configuration')
    );
    assert.throws(
      () => getPortalUrl('TENANT_WORKSPACE'),
      (err: any) => err instanceof PbmsConfigurationError && err.message.includes('Missing required production configuration')
    );
  } finally {
    clearMockWindow();
  }
});

// 12. Production Safety: Explicit ENV: 'production' on Localhost Enforces Production Guard
test('Production Safety: Explicit ENV: "production" enforces production validation even on localhost', () => {
  setMockWindow({
    __PBMS_CONFIG__: {
      ENV: 'production'
    },
    location: { hostname: 'localhost' }
  });

  try {
    assert.strictEqual(isProductionEnvironment(), true);
    assert.throws(
      () => getApiBaseUrl(),
      (err: any) => err instanceof PbmsConfigurationError
    );
  } finally {
    clearMockWindow();
  }
});

// 13. Production Safety: Valid Production URLs Accepted
test('Production Safety: Accepts valid production HTTPS URLs on non-local host', () => {
  setMockWindow({
    __PBMS_CONFIG__: {
      ENV: 'production',
      API_BASE_URL: 'https://api.myprintshop.com/api/v1/',
      TENANT_WORKSPACE_URL: 'https://workspace.myprintshop.com/',
      SUPER_ADMIN_URL: 'https://admin.myprintshop.com/',
      PUBLIC_SITE_URL: 'https://myprintshop.com/'
    },
    location: { hostname: 'workspace.myprintshop.com' }
  });

  try {
    assert.strictEqual(isProductionEnvironment(), true);
    assert.strictEqual(getApiBaseUrl(), 'https://api.myprintshop.com/api/v1');
    assert.strictEqual(getPortalUrl('TENANT_WORKSPACE'), 'https://workspace.myprintshop.com');
    assert.strictEqual(getPortalUrl('SUPER_ADMIN'), 'https://admin.myprintshop.com');
    assert.strictEqual(getPortalUrl('PUBLIC_SITE'), 'https://myprintshop.com');
  } finally {
    clearMockWindow();
  }
});

// 14. Production Safety: Valid Same-Origin Relative Paths Accepted
test('Production Safety: Accepts valid relative paths for reverse-proxied production deployment', () => {
  setMockWindow({
    __PBMS_CONFIG__: {
      ENV: 'production',
      API_BASE_URL: '/api/v1',
      TENANT_WORKSPACE_URL: '/app',
      SUPER_ADMIN_URL: '/admin',
      PUBLIC_SITE_URL: '/'
    },
    location: { hostname: 'pbms.example.com' }
  });

  try {
    assert.strictEqual(isProductionEnvironment(), true);
    assert.strictEqual(getApiBaseUrl(), '/api/v1');
    assert.strictEqual(getPortalUrl('TENANT_WORKSPACE'), '/app');
    assert.strictEqual(getPortalUrl('SUPER_ADMIN'), '/admin');
    assert.strictEqual(getPortalUrl('PUBLIC_SITE'), '/');
  } finally {
    clearMockWindow();
  }
});
