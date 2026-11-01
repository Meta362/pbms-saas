/**
 * PBMS SaaS — Production Runtime Configuration Template
 * 
 * Instructions:
 * 1. For Production Deployment (Docker, Nginx, Kubernetes, Vercel, Firebase):
 *    Deploy this file to your webroot as "assets/pbms-runtime-config.js".
 * 2. Replace the URLs below with your verified production domain endpoints.
 * 3. Never commit real production credentials or internal secrets to this file.
 */
window.__PBMS_CONFIG__ = {
  // Set to 'production' to enforce strict URL validation and disallow localhost fallbacks.
  ENV: 'production',

  // Backend Django REST API Base URL (relative '/api/v1' if reverse-proxied, or full 'https://api.yourdomain.com/api/v1')
  API_BASE_URL: 'https://api.example.com/api/v1',

  // Tenant Workspace application URL (Frontend B)
  TENANT_WORKSPACE_URL: 'https://app.example.com',

  // Super Admin governance console URL (Frontend A)
  SUPER_ADMIN_URL: 'https://admin.example.com',

  // Public Landing and registration website URL (Frontend C)
  PUBLIC_SITE_URL: 'https://example.com'
};

