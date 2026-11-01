import test from 'node:test';
import assert from 'node:assert';
import '@angular/compiler';
import {
  validateUrl,
  getPbmsRuntimeConfig,
  isProductionEnvironment,
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

test('Config Validation: validateUrl accepts valid relative paths for reverse proxies', () => {
  assert.strictEqual(validateUrl('/api/v1', 'API_BASE_URL'), '/api/v1');
  assert.strictEqual(validateUrl('/api/v1/', 'API_BASE_URL'), '/api/v1');
  assert.strictEqual(validateUrl('/app', 'TENANT_WORKSPACE_URL'), '/app');
});

test('Config Validation: validateUrl returns null for null, undefined, or empty strings', () => {
  assert.strictEqual(validateUrl(null, 'API_BASE_URL'), null);
  assert.strictEqual(validateUrl(undefined, 'API_BASE_URL'), null);
  assert.strictEqual(validateUrl('', 'API_BASE_URL'), null);
  assert.strictEqual(validateUrl('   ', 'API_BASE_URL'), null);
});

test('Config Validation: validateUrl rejects protocol-relative URLs (security protection)', () => {
  assert.throws(
    () => validateUrl('//malicious-domain.com/api', 'API_BASE_URL'),
    (err: any) => err instanceof PbmsConfigurationError && err.message.includes('Protocol-relative')
  );
});

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

test('Config Validation: validateUrl rejects malformed URL strings', () => {
  assert.throws(
    () => validateUrl('not a valid url &&&', 'API_BASE_URL'),
    (err: any) => err instanceof PbmsConfigurationError && err.message.includes('Invalid URL')
  );
});

test('Development Fallback: safely defaults to localhost in development / test', () => {
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

test('Production Safety: rejects silent localhost fallback when production configuration is missing', () => {
  setMockWindow({
    __PBMS_CONFIG__: {
      ENV: 'production'
    },
    location: { hostname: 'app.example.com' }
  });

  try {
    assert.strictEqual(isProductionEnvironment(), true);
    // Missing API_BASE_URL in production must throw PbmsConfigurationError
    assert.throws(
      () => getApiBaseUrl(),
      (err: any) => err instanceof PbmsConfigurationError && err.message.includes('Missing required production configuration')
    );
    // Missing portal URLs in production must throw PbmsConfigurationError
    assert.throws(
      () => getPortalUrl('TENANT_WORKSPACE'),
      (err: any) => err instanceof PbmsConfigurationError && err.message.includes('TENANT_WORKSPACE')
    );
    assert.throws(
      () => getPortalUrl('SUPER_ADMIN'),
      (err: any) => err instanceof PbmsConfigurationError && err.message.includes('SUPER_ADMIN')
    );
    assert.throws(
      () => getPortalUrl('PUBLIC_SITE'),
      (err: any) => err instanceof PbmsConfigurationError && err.message.includes('PUBLIC_SITE')
    );
  } finally {
    clearMockWindow();
  }
});

test('Production Safety: accepts valid production URLs when properly supplied', () => {
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

test('Production Safety: automatically detects non-localhost hostname as production if ENV omitted', () => {
  setMockWindow({
    __PBMS_CONFIG__: {},
    location: { hostname: 'pbms.example-cloud.com' }
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
