import { Injectable, signal } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, finalize, shareReplay, tap, throwError } from 'rxjs';

export interface PbmsRuntimeConfig {
  ENV?: 'development' | 'production' | 'test';
  API_BASE_URL?: string;
  TENANT_WORKSPACE_URL?: string;
  SUPER_ADMIN_URL?: string;
  PUBLIC_SITE_URL?: string;
}

declare global {
  interface Window {
    __PBMS_CONFIG__?: PbmsRuntimeConfig;
  }
}

export class PbmsConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PbmsConfigurationError';
  }
}

/**
 * Validates and normalizes URL strings for runtime configuration.
 * - Trims whitespace
 * - Disallows dangerous protocol-relative URLs ('//evil.com')
 * - Allows relative paths (e.g. '/api/v1') for same-origin reverse proxies
 * - Validates absolute URLs to strictly allow 'http:' or 'https:'
 * - Removes trailing slashes for consistent endpoint concatenation
 */
export function validateUrl(val: unknown, fieldName: string): string | null {
  if (val === undefined || val === null) {
    return null;
  }
  if (typeof val !== 'string') {
    throw new PbmsConfigurationError(`Configuration Error: "${fieldName}" must be a string.`);
  }
  const clean = val.trim();
  if (clean === '') {
    return null;
  }
  if (clean.startsWith('//')) {
    throw new PbmsConfigurationError(
      `Configuration Error: Protocol-relative URLs are not permitted for "${fieldName}".`
    );
  }
  if (clean.startsWith('/')) {
    if (clean === '/') {
      return '/';
    }
    return clean.replace(/\/+$/, '');
  }
  let parsed: URL;
  try {
    parsed = new URL(clean);
  } catch {
    throw new PbmsConfigurationError(
      `Configuration Error: Invalid URL specified for "${fieldName}" ("${clean}").`
    );
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new PbmsConfigurationError(
      `Configuration Error: "${fieldName}" must use http or https protocol. Received: "${parsed.protocol}".`
    );
  }
  return clean.replace(/\/+$/, '');
}

/**
 * Access the global runtime configuration object if available.
 */
export function getPbmsRuntimeConfig(): PbmsRuntimeConfig {
  if (typeof window !== 'undefined' && window.__PBMS_CONFIG__) {
    return window.__PBMS_CONFIG__;
  }
  return {};
}

/**
 * Tests whether a given hostname is an explicitly recognized local development host.
 */
export function isLocalDevelopmentHostname(host: string | null | undefined): boolean {
  if (!host || typeof host !== 'string') {
    return false;
  }
  const clean = host.toLowerCase().trim();
  return (
    clean === 'localhost' ||
    clean === '127.0.0.1' ||
    clean === '::1' ||
    clean.endsWith('.local')
  );
}

/**
 * Checks whether a URL points to a local address (localhost, 127.0.0.1, ::1, or .local).
 */
export function isLocalhostUrl(urlStr: string): boolean {
  if (!urlStr || typeof urlStr !== 'string') {
    return false;
  }
  const clean = urlStr.trim().toLowerCase();
  if (clean.startsWith('/')) {
    return false; // Relative path on current origin is NOT localhost unless current host is localhost
  }
  try {
    const parsed = new URL(clean);
    return isLocalDevelopmentHostname(parsed.hostname);
  } catch {
    return clean.includes('localhost') || clean.includes('127.0.0.1');
  }
}

/**
 * Detects whether the current runtime environment is considered production.
 *
 * FAIL-CLOSED INVARIANT:
 * A non-local hostname (e.g. app.angkorprint.com, pbms-saas.vercel.app) is ALWAYS
 * considered production and MUST enforce production safety, EVEN IF a stale or
 * accidentally shipped config declares ENV: 'development'.
 */
export function isProductionEnvironment(): boolean {
  const config = getPbmsRuntimeConfig();

  // 1. Explicit production declaration always activates production mode
  if (config.ENV === 'production') {
    return true;
  }

  // 2. In browser environments, check the actual location hostname
  if (typeof window !== 'undefined' && window.location) {
    const host = window.location.hostname;
    if (host && !isLocalDevelopmentHostname(host)) {
      // Non-local host: FAIL-CLOSED -> always production, ignores ENV: 'development'
      return true;
    }
  }

  // 3. For local hostnames or non-browser test runners:
  if (config.ENV === 'development' || config.ENV === 'test') {
    return false;
  }

  // 4. In non-browser environments with no hostname (e.g. Node tests), default to non-production unless ENV=production
  if (typeof window === 'undefined' || !window.location || !window.location.hostname) {
    return false;
  }

  // Default to development on localhost
  return false;
}

/**
 * Resolves the Backend API base URL.
 * - In production: rejects missing configuration AND rejects localhost URLs.
 * - In development: defaults safely to 'http://localhost:8000/api/v1'.
 */
export function getApiBaseUrl(): string {
  const isProd = isProductionEnvironment();
  const raw = getPbmsRuntimeConfig().API_BASE_URL;
  const validated = validateUrl(raw, 'API_BASE_URL');

  if (isProd) {
    if (!validated) {
      throw new PbmsConfigurationError(
        'Missing required production configuration: "API_BASE_URL" is not configured. Please supply a valid production API endpoint via runtime configuration.'
      );
    }
    if (isLocalhostUrl(validated)) {
      throw new PbmsConfigurationError(
        'Invalid production configuration: "API_BASE_URL" cannot point to localhost in a production environment. Please supply a valid production API endpoint.'
      );
    }
    return validated;
  }

  return validated || 'http://localhost:8000/api/v1';
}

export type PbmsPortalType = 'TENANT_WORKSPACE' | 'SUPER_ADMIN' | 'PUBLIC_SITE';

/**
 * Resolves portal URLs for cross-application navigation.
 * - In production: rejects missing configuration AND rejects localhost URLs.
 * - In development: defaults safely to known dev server ports.
 */
export function getPortalUrl(portal: PbmsPortalType): string {
  const isProd = isProductionEnvironment();
  const config = getPbmsRuntimeConfig();
  let raw: unknown;
  let devFallback = '/';

  switch (portal) {
    case 'TENANT_WORKSPACE':
      raw = config.TENANT_WORKSPACE_URL;
      devFallback = 'http://localhost:4202';
      break;
    case 'SUPER_ADMIN':
      raw = config.SUPER_ADMIN_URL;
      devFallback = 'http://localhost:4201';
      break;
    case 'PUBLIC_SITE':
      raw = config.PUBLIC_SITE_URL;
      devFallback = 'http://localhost:4200';
      break;
    default:
      return '/';
  }

  const validated = validateUrl(raw, portal);

  if (isProd) {
    if (!validated) {
      throw new PbmsConfigurationError(
        `Missing required production configuration: "${portal}" URL is not configured.`
      );
    }
    if (isLocalhostUrl(validated)) {
      throw new PbmsConfigurationError(
        `Invalid production configuration: "${portal}" URL cannot point to localhost in a production environment.`
      );
    }
    return validated;
  }

  return validated || devFallback;
}

export const API_BASE_URL = getApiBaseUrl();

export interface PublicPlan {
  id: string;
  code: string;
  name_en: string;
  name_km: string;
  description_en: string;
  description_km: string;
  monthly_price_usd: string;
  annual_price_usd: string;
  max_staff_users: number;
  max_orders_per_month: number;
}

export interface TenantMembershipInfo {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: string;
  base_currency: string;
  khr_exchange_rate: string;
}

export interface TenantMembershipItem {
  id: string;
  tenant_id: string;
  user_id: string;
  email: string;
  full_name: string;
  phone: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TenantContext {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  role: string;
  base_currency: string;
  khr_exchange_rate: string;
  tax_rate_percent: string;
  is_tax_registered?: boolean;
  tax_id_number?: string;
}

export interface TenantSettings {
  id: string;
  name: string;
  slug: string;
  base_currency: string;
  khr_exchange_rate: string;
  tax_rate_percent: string;
  is_tax_registered: boolean;
  tax_id_number: string;
  updated_at: string;
}

export * from './helpers';

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  platform_role: string;
  preferred_language: 'km' | 'en';
  memberships: TenantMembershipInfo[];
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  session_id: string;
  expires_in: number;
  user: UserProfile;
}

export const PBMS_LANG_STORAGE_KEY = 'pbms_lang';

@Injectable({ providedIn: 'root' })
export class PbmsI18nService {
  readonly lang = signal<'km' | 'en'>(this.loadInitialLanguage());

  private getStorage(): Storage | null {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        return window.localStorage;
      }
      if (typeof localStorage !== 'undefined') {
        return localStorage;
      }
    } catch {
      // Defensive fallback for restricted environments
    }
    return null;
  }

  private loadInitialLanguage(): 'km' | 'en' {
    try {
      const storage = this.getStorage();
      if (storage) {
        const stored = storage.getItem(PBMS_LANG_STORAGE_KEY);
        if (stored === 'km' || stored === 'en') {
          return stored;
        }
      }
    } catch {
      // Defensive fallback
    }
    return 'km';
  }

  toggleLanguage(): void {
    const nextLang: 'km' | 'en' = this.lang() === 'km' ? 'en' : 'km';
    this.lang.set(nextLang);
    try {
      const storage = this.getStorage();
      if (storage) {
        storage.setItem(PBMS_LANG_STORAGE_KEY, nextLang);
      }
    } catch {
      // Silently ignore storage errors (quota, restricted storage)
    }
  }

  t(kmText: string, enText: string): string {
    return this.lang() === 'km' ? kmText : enText;
  }
}

@Injectable({ providedIn: 'root' })
export class PbmsSessionClient {
  private readonly refreshRequests = new Map<
    string,
    Observable<{ access_token: string; refresh_token: string }>
  >();

  private readonly http: HttpClient;

  constructor(http: HttpClient) {
    this.http = http;
  }

  login(email: string, password: string, storagePrefix: string): Observable<LoginResponse> {
    return this.http
      .post<LoginResponse>(`${API_BASE_URL}/auth/login/`, { email, password })
      .pipe(
        tap((res) => {
          sessionStorage.setItem(`${storagePrefix}_access`, res.access_token);
          sessionStorage.setItem(`${storagePrefix}_refresh`, res.refresh_token);
          sessionStorage.setItem(`${storagePrefix}_user`, JSON.stringify(res.user));
          if (res.user.memberships.length > 0) {
            sessionStorage.setItem(
              `${storagePrefix}_tenant_id`,
              res.user.memberships[0].tenant_id
            );
          }
        })
      );
  }

  refreshToken(storagePrefix: string): Observable<{ access_token: string; refresh_token: string }> {
    const existing = this.refreshRequests.get(storagePrefix);
    if (existing) {
      return existing;
    }

    const refresh = sessionStorage.getItem(`${storagePrefix}_refresh`) || '';
    if (!refresh) {
      this.clearStorage(storagePrefix);
      return throwError(() => new Error('No refresh token available.'));
    }

    const refresh$ = this.http
      .post<{ access_token: string; refresh_token: string }>(`${API_BASE_URL}/auth/refresh/`, {
        refresh_token: refresh,
      })
      .pipe(
        tap({
          next: (res) => {
            sessionStorage.setItem(`${storagePrefix}_access`, res.access_token);
            sessionStorage.setItem(`${storagePrefix}_refresh`, res.refresh_token);
          },
          error: (err) => {
            if (err?.status === 401 || err?.status === 403 || err?.status === 400) {
              this.clearStorage(storagePrefix);
            }
          },
        }),
        finalize(() => {
          this.refreshRequests.delete(storagePrefix);
        }),
        shareReplay(1)
      );

    this.refreshRequests.set(storagePrefix, refresh$);
    return refresh$;
  }

  logout(storagePrefix: string): Observable<{ status: string }> {
    const headers = this.getHeaders(storagePrefix, false);
    const refresh = sessionStorage.getItem(`${storagePrefix}_refresh`) || '';
    return this.http
      .post<{ status: string }>(
        `${API_BASE_URL}/auth/logout/`,
        { refresh_token: refresh },
        { headers }
      )
      .pipe(
        tap({
          next: () => this.clearStorage(storagePrefix),
          error: () => this.clearStorage(storagePrefix),
        })
      );
  }

  clearStorage(storagePrefix: string): void {
    sessionStorage.removeItem(`${storagePrefix}_access`);
    sessionStorage.removeItem(`${storagePrefix}_refresh`);
    sessionStorage.removeItem(`${storagePrefix}_user`);
    sessionStorage.removeItem(`${storagePrefix}_tenant_id`);
  }

  getStoredUser(storagePrefix: string): UserProfile | null {
    const raw = sessionStorage.getItem(`${storagePrefix}_user`);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as UserProfile;
    } catch {
      return null;
    }
  }

  getActiveTenantId(storagePrefix: string): string {
    return sessionStorage.getItem(`${storagePrefix}_tenant_id`) || '';
  }

  setActiveTenantId(storagePrefix: string, tenantId: string): void {
    sessionStorage.setItem(`${storagePrefix}_tenant_id`, tenantId);
  }

  getHeaders(storagePrefix: string, includeTenant = true): HttpHeaders {
    const access = sessionStorage.getItem(`${storagePrefix}_access`) || '';
    const tenantId = sessionStorage.getItem(`${storagePrefix}_tenant_id`) || '';
    let headers = new HttpHeaders({ 'Content-Type': 'application/json' });
    if (access) {
      headers = headers.set('Authorization', `Bearer ${access}`);
    }
    if (includeTenant && tenantId) {
      headers = headers.set('X-Tenant-ID', tenantId);
    }
    return headers;
  }
}
