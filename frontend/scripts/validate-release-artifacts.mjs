#!/usr/bin/env node
/**
 * PBMS SaaS - Production Release Artifact Validator
 *
 * Verifies that production build artifacts (dist/ outputs) satisfy the production runtime contract:
 * 1. Runtime config asset file exists and is non-empty.
 * 2. Does NOT contain unconfigured development settings (e.g. ENV: 'development').
 * 3. Does NOT contain loopback/development URLs (localhost, 127.0.0.1, 0.0.0.0, ::1, *.local).
 * 4. URLs must be valid HTTPS endpoints or valid relative paths.
 * 5. Fails closed with non-zero exit code if validation fails.
 */

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const FRONTEND_ROOT = path.resolve(__dirname, '..');

export const REQUIRED_APPS = ['public-site', 'super-admin', 'tenant-workspace'];
export const RELATIVE_ASSET_PATH = path.join('browser', 'assets', 'pbms-runtime-config.js');

const FORBIDDEN_HOST_PATTERNS = [
  /localhost/i,
  /127\.0\.0\.1/,
  /0\.0\.0\.0/,
  /::1/,
  /\.local(?::\d+)?(?:\/|$)/i
];

/**
 * Validates a single pbms-runtime-config.js file.
 * Returns an array of error messages (empty if valid).
 */
export function validateRuntimeConfigFile(filePath, appName = 'app') {
  const errors = [];

  if (!fs.existsSync(filePath)) {
    return [`[${appName}] Missing required runtime configuration file: ${filePath}`];
  }

  const fileContent = fs.readFileSync(filePath, 'utf-8');
  if (!fileContent.trim()) {
    return [`[${appName}] Runtime configuration file is empty: ${filePath}`];
  }

  // Parse using a safe vm sandbox
  const sandbox = { window: {} };
  vm.createContext(sandbox);

  try {
    vm.runInContext(fileContent, sandbox, { filename: filePath, timeout: 1000 });
  } catch (err) {
    return [`[${appName}] Failed to execute runtime config script: ${err.message}`];
  }

  const config = sandbox.window?.__PBMS_CONFIG__;
  if (!config || typeof config !== 'object') {
    return [`[${appName}] window.__PBMS_CONFIG__ is not defined or not an object in: ${filePath}`];
  }

  // 1. Check ENV
  if (config.ENV !== 'production') {
    errors.push(
      `[${appName}] ENV must be explicitly set to 'production' for release builds. Found: '${config.ENV}'`
    );
  }

  // 2. Validate URL fields
  const urlFields = [
    { key: 'API_BASE_URL', required: true },
    { key: 'TENANT_WORKSPACE_URL', required: true },
    { key: 'SUPER_ADMIN_URL', required: true },
    { key: 'PUBLIC_SITE_URL', required: true }
  ];

  for (const { key, required } of urlFields) {
    const val = config[key];
    if (!val || typeof val !== 'string' || !val.trim()) {
      if (required) {
        errors.push(`[${appName}] Missing required configuration key '${key}'`);
      }
      continue;
    }

    const trimmed = val.trim();

    // Check for forbidden loopback addresses
    for (const pattern of FORBIDDEN_HOST_PATTERNS) {
      if (pattern.test(trimmed)) {
        errors.push(
          `[${appName}] Key '${key}' contains forbidden localhost/loopback address: "${trimmed}"`
        );
        break;
      }
    }

    // Must be either an https:// absolute URL or a valid relative path starting with '/'
    const isRelative = trimmed.startsWith('/');
    const isHttps = /^https:\/\/[^/]+/i.test(trimmed);

    if (!isRelative && !isHttps) {
      errors.push(
        `[${appName}] Key '${key}' must be an HTTPS absolute URL or a relative path ('/path'). Found: "${trimmed}"`
      );
    }
  }

  return errors;
}

/**
 * Validates the release artifacts across all applications in a specified base dist directory.
 */
export function validateDistArtifacts(baseDistDir = path.join(FRONTEND_ROOT, 'dist')) {
  const allErrors = [];

  for (const app of REQUIRED_APPS) {
    const configPath = path.join(baseDistDir, app, RELATIVE_ASSET_PATH);
    const errors = validateRuntimeConfigFile(configPath, app);
    allErrors.push(...errors);
  }

  return allErrors;
}

// CLI Execution entrypoint
const isMainModule = Boolean(
  process.argv[1] &&
  !process.argv[1].includes('test') &&
  path.resolve(process.argv[1]).toLowerCase() === path.resolve(fileURLToPath(import.meta.url)).toLowerCase()
);
if (isMainModule) {
  const targetDist = process.argv[2]
    ? path.resolve(process.cwd(), process.argv[2])
    : path.join(FRONTEND_ROOT, 'dist');

  console.log(`[validate-release-artifacts] Checking production artifacts in: ${targetDist}`);

  const errors = validateDistArtifacts(targetDist);

  if (errors.length > 0) {
    console.error('\n❌ Production Runtime Asset Contract Violation:');
    for (const error of errors) {
      console.error(`  - ${error}`);
    }
    console.error('\nProduction artifacts must NOT ship with development configuration or localhost URLs.');
    console.error('Use scripts/generate-runtime-config.mjs or inject production configuration before release.\n');
    process.exit(1);
  }

  console.log('✅ All production runtime configuration assets passed contract verification.');
  process.exit(0);
}
