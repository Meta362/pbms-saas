#!/usr/bin/env node
/**
 * PBMS SaaS - Production Runtime Configuration Generator
 *
 * Generates production pbms-runtime-config.js for deployed environments or CI release packaging.
 * Reads values from environment variables or CLI flags, falling back to same-origin relative paths.
 *
 * Supported Environment Variables:
 * - PBMS_ENV: 'production' (default: 'production')
 * - PBMS_API_BASE_URL: e.g. 'https://api.angkorprint.com/api/v1' or '/api/v1'
 * - PBMS_TENANT_WORKSPACE_URL: e.g. 'https://app.angkorprint.com' or '/app'
 * - PBMS_SUPER_ADMIN_URL: e.g. 'https://admin.angkorprint.com' or '/admin'
 * - PBMS_PUBLIC_SITE_URL: e.g. 'https://angkorprint.com' or '/'
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const FRONTEND_ROOT = path.resolve(__dirname, '..');

export function createConfigContent(customValues = {}) {
  const env = customValues.ENV || process.env.PBMS_ENV || 'production';
  const apiBaseUrl = customValues.API_BASE_URL || process.env.PBMS_API_BASE_URL || '/api/v1';
  const tenantWorkspaceUrl = customValues.TENANT_WORKSPACE_URL || process.env.PBMS_TENANT_WORKSPACE_URL || '/app';
  const superAdminUrl = customValues.SUPER_ADMIN_URL || process.env.PBMS_SUPER_ADMIN_URL || '/admin';
  const publicSiteUrl = customValues.PUBLIC_SITE_URL || process.env.PBMS_PUBLIC_SITE_URL || '/';

  return `window.__PBMS_CONFIG__ = {
  ENV: '${env}',
  API_BASE_URL: '${apiBaseUrl}',
  TENANT_WORKSPACE_URL: '${tenantWorkspaceUrl}',
  SUPER_ADMIN_URL: '${superAdminUrl}',
  PUBLIC_SITE_URL: '${publicSiteUrl}'
};
`;
}

export function writeRuntimeConfigToDist(baseDistDir = path.join(FRONTEND_ROOT, 'dist'), customValues = {}) {
  const apps = ['public-site', 'super-admin', 'tenant-workspace'];
  const content = createConfigContent(customValues);
  const writtenPaths = [];

  for (const app of apps) {
    const assetsDir = path.join(baseDistDir, app, 'browser', 'assets');
    if (!fs.existsSync(assetsDir)) {
      fs.mkdirSync(assetsDir, { recursive: true });
    }
    const targetFile = path.join(assetsDir, 'pbms-runtime-config.js');
    fs.writeFileSync(targetFile, content, 'utf-8');
    writtenPaths.push(targetFile);
  }

  return writtenPaths;
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

  console.log(`[generate-runtime-config] Generating production runtime configuration in: ${targetDist}`);
  const written = writeRuntimeConfigToDist(targetDist);
  for (const p of written) {
    console.log(`  - Wrote ${p}`);
  }
  console.log('✅ Production runtime configuration generated successfully.');
}
