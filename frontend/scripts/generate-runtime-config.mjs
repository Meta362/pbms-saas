#!/usr/bin/env node
/**
 * PBMS SaaS - Production Runtime Configuration Generator
 *
 * Generates production pbms-runtime-config.js for deployed environments or CI release packaging.
 * Reads values from environment variables or custom objects.
 *
 * Security & Reliability Invariants:
 * 1. Safe JSON serialization (prevents JavaScript injection / escaping bugs).
 * 2. Enforces ENV === 'production' for release builds.
 * 3. Validates all required URL fields before writing (no partial file writes).
 * 4. Atomic file writing with rollback on failure.
 * 5. Path traversal boundary check on base output directory.
 * 6. Redaction of sensitive credentials/tokens in error messages.
 *
 * Supported Environment Variables:
 * - PBMS_ENV: Must be 'production' (default: 'production')
 * - PBMS_API_BASE_URL: e.g. 'https://api.angkorprint.com/api/v1' or '/api/v1' (for same-origin API gateway)
 * - PBMS_TENANT_WORKSPACE_URL: e.g. 'https://app.angkorprint.com' (or '/app' if explicit relative routing configured)
 * - PBMS_SUPER_ADMIN_URL: e.g. 'https://admin.angkorprint.com' (or '/admin' if explicit relative routing configured)
 * - PBMS_PUBLIC_SITE_URL: e.g. 'https://angkorprint.com' (or '/' if explicit relative routing configured)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
export const FRONTEND_ROOT = path.resolve(__dirname, '..');
export const REQUIRED_APPS = ['public-site', 'super-admin', 'tenant-workspace'];

// Loopback and local patterns that must be rejected in production
const FORBIDDEN_HOST_PATTERNS = [
  /^localhost$/i,
  /^127(?:\.[0-9]+){1,3}$/,
  /^0\.0\.0\.0$/,
  /^::1$/,
  /^\[::1\]$/,
  /\.local$/i
];

/**
 * Redacts potential credentials from URLs or strings before logging.
 */
export function redactValue(val) {
  if (typeof val !== 'string') return String(val);
  try {
    const parsed = new URL(val);
    if (parsed.username) parsed.username = '***';
    if (parsed.password) parsed.password = '***';
    return parsed.toString();
  } catch {
    return val.length > 40 ? val.slice(0, 15) + '...[REDACTED]' : val;
  }
}

/**
 * Checks whether a hostname is a loopback or local host.
 */
export function isLocalOrLoopbackHost(hostname) {
  if (!hostname) return false;
  const clean = hostname.trim().toLowerCase().replace(/^\[|\]$/g, '');
  for (const pattern of FORBIDDEN_HOST_PATTERNS) {
    if (pattern.test(clean)) return true;
  }
  return false;
}

/**
 * Validates a URL field for production release.
 * - Allows HTTPS absolute URLs (rejects credentials, embedded userinfo, loopback hosts).
 * - Allows relative paths (must start with single '/', reject '//' protocol-relative and '/\\').
 */
export function validateProductionUrl(val, fieldName) {
  if (val === undefined || val === null || typeof val !== 'string') {
    throw new Error(`[generate-runtime-config] Field '${fieldName}' must be a non-empty string.`);
  }

  const trimmed = val.trim();
  if (trimmed === '') {
    throw new Error(`[generate-runtime-config] Field '${fieldName}' cannot be empty.`);
  }

  // Reject protocol-relative and backslash obfuscation
  if (trimmed.startsWith('//') || trimmed.startsWith('/\\') || trimmed.startsWith('\\')) {
    throw new Error(
      `[generate-runtime-config] Field '${fieldName}' contains invalid protocol-relative or backslash path: "${redactValue(trimmed)}"`
    );
  }

  // Relative path check
  if (trimmed.startsWith('/')) {
    // Relative paths cannot contain control characters, newlines, quotes, or backslashes
    if (/[\s\r\n"'\\<>]/.test(trimmed)) {
      throw new Error(`[generate-runtime-config] Field '${fieldName}' contains invalid characters in relative path: "${redactValue(trimmed)}"`);
    }
    // Remove trailing slash except for root '/'
    return trimmed.length > 1 && trimmed.endsWith('/') ? trimmed.replace(/\/+$/, '') : trimmed;
  }

  // Absolute URL check
  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch (err) {
    throw new Error(`[generate-runtime-config] Field '${fieldName}' is not a valid URL: "${redactValue(trimmed)}"`);
  }

  if (parsed.protocol !== 'https:') {
    throw new Error(
      `[generate-runtime-config] Field '${fieldName}' must use 'https:' protocol in production. Received: "${parsed.protocol}"`
    );
  }

  // Reject embedded credentials
  if (parsed.username || parsed.password) {
    throw new Error(
      `[generate-runtime-config] Field '${fieldName}' must not contain user credentials (username/password in URL).`
    );
  }

  // Reject loopback hosts
  if (isLocalOrLoopbackHost(parsed.hostname)) {
    throw new Error(
      `[generate-runtime-config] Field '${fieldName}' cannot point to loopback/localhost in production: "${redactValue(trimmed)}"`
    );
  }

  // Normalized HTTPS URL without trailing slash
  const pathname = parsed.pathname.length > 1 && parsed.pathname.endsWith('/')
    ? parsed.pathname.replace(/\/+$/, '')
    : parsed.pathname;

  return `${parsed.protocol}//${parsed.host}${pathname === '/' ? '' : pathname}${parsed.search}`;
}

/**
 * Validates the full configuration object before code generation.
 */
export function validateAndNormalizeConfig(customValues = {}) {
  const env = customValues.ENV !== undefined ? customValues.ENV : (process.env.PBMS_ENV || 'production');
  if (env !== 'production') {
    throw new Error(
      `[generate-runtime-config] Release generator strictly requires ENV === 'production'. Received: '${env}'`
    );
  }

  // Read raw fields with defaults
  const rawApi = customValues.API_BASE_URL !== undefined
    ? customValues.API_BASE_URL
    : (process.env.PBMS_API_BASE_URL || '/api/v1');

  const rawTenant = customValues.TENANT_WORKSPACE_URL !== undefined
    ? customValues.TENANT_WORKSPACE_URL
    : (process.env.PBMS_TENANT_WORKSPACE_URL || '/app');

  const rawSuperAdmin = customValues.SUPER_ADMIN_URL !== undefined
    ? customValues.SUPER_ADMIN_URL
    : (process.env.PBMS_SUPER_ADMIN_URL || '/admin');

  const rawPublic = customValues.PUBLIC_SITE_URL !== undefined
    ? customValues.PUBLIC_SITE_URL
    : (process.env.PBMS_PUBLIC_SITE_URL || '/');

  const normalized = {
    ENV: 'production',
    API_BASE_URL: validateProductionUrl(rawApi, 'API_BASE_URL'),
    TENANT_WORKSPACE_URL: validateProductionUrl(rawTenant, 'TENANT_WORKSPACE_URL'),
    SUPER_ADMIN_URL: validateProductionUrl(rawSuperAdmin, 'SUPER_ADMIN_URL'),
    PUBLIC_SITE_URL: validateProductionUrl(rawPublic, 'PUBLIC_SITE_URL')
  };

  return normalized;
}

/**
 * Creates deterministic, safe JavaScript using JSON serialization.
 */
export function createConfigContent(customValues = {}) {
  const config = validateAndNormalizeConfig(customValues);
  return `window.__PBMS_CONFIG__ = Object.freeze(${JSON.stringify(config, null, 2)});\n`;
}

/**
 * Resolves and validates that the output directory stays within permitted path boundaries.
 */
export function resolveSafeDistDir(baseDistDir) {
  const resolved = path.resolve(baseDistDir);
  // Ensure the target is a subdirectory of FRONTEND_ROOT or within cwd
  const allowedRoots = [FRONTEND_ROOT, process.cwd()];
  const isInside = allowedRoots.some(root => {
    const rel = path.relative(path.resolve(root), resolved);
    return !rel.startsWith('..') && !path.isAbsolute(rel);
  });

  if (!isInside && process.env.PBMS_ALLOW_EXTERNAL_DIST !== 'true') {
    throw new Error(
      `[generate-runtime-config] Path traversal detected: output directory "${resolved}" is outside project root.`
    );
  }

  return resolved;
}

/**
 * Writes the configuration atomically to all required apps.
 * If any application fails, rolls back previously written files.
 */
export function writeRuntimeConfigToDist(baseDistDir = path.join(FRONTEND_ROOT, 'dist'), customValues = {}) {
  const safeDist = resolveSafeDistDir(baseDistDir);
  const content = createConfigContent(customValues);
  const writtenPaths = [];
  const tempFiles = [];

  try {
    // 1. Stage all writes to temporary files first
    for (const app of REQUIRED_APPS) {
      const assetsDir = path.join(safeDist, app, 'browser', 'assets');
      if (!fs.existsSync(assetsDir)) {
        fs.mkdirSync(assetsDir, { recursive: true });
      }
      const targetFile = path.join(assetsDir, 'pbms-runtime-config.js');
      const tempFile = path.join(assetsDir, `pbms-runtime-config.tmp.${process.pid}.${Date.now()}`);

      fs.writeFileSync(tempFile, content, 'utf-8');
      tempFiles.push({ tempFile, targetFile });
    }

    // 2. Commit all files atomically
    for (const { tempFile, targetFile } of tempFiles) {
      fs.renameSync(tempFile, targetFile);
      writtenPaths.push(targetFile);
    }

    return writtenPaths;
  } catch (err) {
    // Rollback any temporary files or partially committed files
    for (const { tempFile, targetFile } of tempFiles) {
      try {
        if (fs.existsSync(tempFile)) fs.unlinkSync(tempFile);
      } catch (_) {}
    }
    for (const written of writtenPaths) {
      try {
        if (fs.existsSync(written)) fs.unlinkSync(written);
      } catch (_) {}
    }
    throw new Error(`[generate-runtime-config] Failed to write release configuration: ${err.message}`);
  }
}

// CLI Execution entrypoint
const isMainModule = Boolean(
  process.argv[1] &&
  !process.argv[1].includes('test') &&
  path.resolve(process.argv[1]).toLowerCase() === path.resolve(fileURLToPath(import.meta.url)).toLowerCase()
);

if (isMainModule) {
  try {
    const targetDist = process.argv[2]
      ? path.resolve(process.cwd(), process.argv[2])
      : path.join(FRONTEND_ROOT, 'dist');

    console.log(`[generate-runtime-config] Generating secure production runtime configuration in: ${targetDist}`);
    const written = writeRuntimeConfigToDist(targetDist);
    for (const p of written) {
      console.log(`  - Wrote ${p}`);
    }
    console.log('✅ Secure production runtime configuration generated successfully.');
    process.exit(0);
  } catch (err) {
    console.error(`\n❌ [generate-runtime-config] Error: ${err.message}\n`);
    process.exit(1);
  }
}
