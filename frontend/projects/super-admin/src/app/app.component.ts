import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { API_BASE_URL, PbmsI18nService, PbmsSessionClient, UserProfile, formatApiErrorMessage } from '@pbms/shared';

interface SuperAdminOverview {
  metrics: {
    total_tenants: number;
    active_tenants: number;
    pending_tenants: number;
    pending_payments: number;
    total_revenue_usd: string;
  };
  recent_audit_events: Array<{
    id: string;
    created_at: string;
    event_type: string;
    target_model: string;
    target_id: string;
  }>;
}

interface SuperAdminTenantItem {
  id: string;
  name: string;
  slug: string;
  status: string;
  email: string;
  phone: string;
  created_at: string;
  subscription: {
    plan_code: string;
    plan_name_en: string;
    status: string;
    billing_cycle: string;
  } | null;
  latest_payment: {
    id: string;
    amount_usd: string;
    status: string;
    provider: string;
    provider_reference: string;
  } | null;
}

@Component({
  selector: 'pbms-admin-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
})
export class AppComponent implements OnInit {
  private readonly STORAGE_KEY = 'pbms_super_admin';
  readonly i18n = inject(PbmsI18nService);
  private readonly session = inject(PbmsSessionClient);
  private readonly http = inject(HttpClient);

  readonly user = signal<UserProfile | null>(null);
  email = 'admin@pbms.local';
  password = 'Admin@PBMS2026';
  readonly errorMsg = signal<string>('');
  readonly actionBanner = signal<string>('');
  readonly reconcilingPaymentId = signal<string | null>(null);
  readonly togglingTenantId = signal<string | null>(null);

  readonly overview = signal<SuperAdminOverview | null>(null);
  readonly tenants = signal<SuperAdminTenantItem[]>([]);

  get isSuperAdmin(): boolean {
    return this.user()?.platform_role === 'SUPER_ADMIN';
  }

  ngOnInit(): void {
    const existing = this.session.getStoredUser(this.STORAGE_KEY);
    if (
      existing &&
      (existing.platform_role === 'SUPER_ADMIN' ||
        existing.platform_role === 'PLATFORM_SUPPORT')
    ) {
      this.user.set(existing);
      this.loadAll();
    }
  }

  private handleReadError(err: any, fallbackMessage: string): void {
    if (err?.status === 401) {
      this.session.refreshToken(this.STORAGE_KEY).subscribe({
        next: () => {
          this.loadAll();
        },
        error: () => {
          this.logout('Session expired. Please sign in again.');
        },
      });
      return;
    }
    this.errorMsg.set(formatApiErrorMessage(err, fallbackMessage));
  }

  private handleMutationError(err: any, mutationName: string, fallbackMessage: string): void {
    this.actionBanner.set('');
    if (err?.status === 401) {
      this.session.refreshToken(this.STORAGE_KEY).subscribe({
        next: () => {
          this.errorMsg.set(
            `Session refreshed. ${mutationName} was not submitted. Please try again.`
          );
          this.loadAll();
        },
        error: () => {
          this.logout('Session expired. Please sign in again.');
        },
      });
      return;
    }
    this.errorMsg.set(formatApiErrorMessage(err, fallbackMessage));
  }

  login(): void {
    this.errorMsg.set('');
    this.session.login(this.email, this.password, this.STORAGE_KEY).subscribe({
      next: (res) => {
        if (
          res.user.platform_role !== 'SUPER_ADMIN' &&
          res.user.platform_role !== 'PLATFORM_SUPPORT'
        ) {
          this.session.clearStorage(this.STORAGE_KEY);
          this.errorMsg.set(
            'Access Denied: This account does not have platform administration or support privileges.'
          );
          return;
        }
        this.user.set(res.user);
        this.loadAll();
      },
      error: (err) => {
        this.errorMsg.set(
          formatApiErrorMessage(
            err,
            'Login failed. Verify backend server is running.'
          )
        );
      },
    });
  }

  logout(customMsg = ''): void {
    this.session.logout(this.STORAGE_KEY).subscribe({
      next: () => this.resetState(customMsg),
      error: () => this.resetState(customMsg),
    });
  }

  private resetState(customMsg = ''): void {
    this.user.set(null);
    this.overview.set(null);
    this.tenants.set([]);
    this.actionBanner.set('');
    this.errorMsg.set(customMsg);
    this.reconcilingPaymentId.set(null);
    this.togglingTenantId.set(null);
  }

  loadAll(): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .get<SuperAdminOverview>(`${API_BASE_URL}/super-admin/overview/`, { headers })
      .subscribe({
        next: (data) => this.overview.set(data),
        error: (err) => {
          this.handleReadError(err, 'Failed to load platform overview.');
        },
      });

    this.http
      .get<SuperAdminTenantItem[]>(`${API_BASE_URL}/super-admin/tenants/`, { headers })
      .subscribe({
        next: (list) => this.tenants.set(list),
        error: (err) => {
          this.handleReadError(err, 'Failed to load tenant directory.');
        },
      });
  }

  reconcilePayment(paymentId: string, action: 'APPROVE' | 'REJECT'): void {
    this.errorMsg.set('');
    if (this.reconcilingPaymentId()) return;
    this.reconcilingPaymentId.set(paymentId);
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .post(
        `${API_BASE_URL}/super-admin/payments/${paymentId}/reconcile/`,
        { action, notes: `Reconciled via Super Admin Portal (${action})` },
        { headers }
      )
      .subscribe({
        next: () => {
          this.reconcilingPaymentId.set(null);
          this.actionBanner.set(`Payment reconciled (${action}) and Tenant activated!`);
          this.loadAll();
        },
        error: (err) => {
          this.reconcilingPaymentId.set(null);
          this.handleMutationError(
            err,
            'Payment reconciliation',
            'Payment reconciliation failed.'
          );
        },
      });
  }

  toggleTenantStatus(tenantId: string, action: 'SUSPEND' | 'ACTIVATE'): void {
    this.errorMsg.set('');
    if (this.togglingTenantId()) return;
    this.togglingTenantId.set(tenantId);
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .post(
        `${API_BASE_URL}/super-admin/tenants/${tenantId}/status/`,
        { action, reason: `Super Admin manual ${action}` },
        { headers }
      )
      .subscribe({
        next: () => {
          this.togglingTenantId.set(null);
          this.actionBanner.set(`Tenant status updated (${action}).`);
          this.loadAll();
        },
        error: (err) => {
          this.togglingTenantId.set(null);
          this.handleMutationError(
            err,
            'Tenant status update',
            'Tenant status update failed.'
          );
        },
      });
  }
}