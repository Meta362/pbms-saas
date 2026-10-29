import { Injectable, signal } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, finalize, shareReplay, tap, throwError } from 'rxjs';

export const API_BASE_URL = 'http://localhost:8000/api/v1';

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
