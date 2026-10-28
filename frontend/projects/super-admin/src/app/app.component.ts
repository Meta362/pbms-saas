import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { API_BASE_URL, PbmsI18nService, PbmsSessionClient, UserProfile } from '@pbms/shared';

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

  readonly overview = signal<SuperAdminOverview | null>(null);
  readonly tenants = signal<SuperAdminTenantItem[]>([]);

  ngOnInit(): void {
    const existing = this.session.getStoredUser(this.STORAGE_KEY);
    if (existing && existing.platform_role === 'SUPER_ADMIN') {
      this.user.set(existing);
      this.loadAll();
    }
  }

  login(): void {
    this.errorMsg.set('');
    this.session.login(this.email, this.password, this.STORAGE_KEY).subscribe({
      next: (res) => {
        if (res.user.platform_role !== 'SUPER_ADMIN') {
          this.session.clearStorage(this.STORAGE_KEY);
          this.errorMsg.set('Access Denied: This account does not have SUPER_ADMIN privileges.');
          return;
        }
        this.user.set(res.user);
        this.loadAll();
      },
      error: (err) => {
        this.errorMsg.set(err?.error?.detail || 'Login failed. Verify backend server is running.');
      },
    });
  }

  logout(): void {
    this.session.logout(this.STORAGE_KEY).subscribe(() => {
      this.user.set(null);
      this.overview.set(null);
      this.tenants.set([]);
    });
  }

  loadAll(): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .get<SuperAdminOverview>(`${API_BASE_URL}/super-admin/overview/`, { headers })
      .subscribe({
        next: (data) => this.overview.set(data),
        error: () => this.logout(),
      });

    this.http
      .get<SuperAdminTenantItem[]>(`${API_BASE_URL}/super-admin/tenants/`, { headers })
      .subscribe({
        next: (list) => this.tenants.set(list),
      });
  }

  reconcilePayment(paymentId: string, action: 'APPROVE' | 'REJECT'): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .post(
        `${API_BASE_URL}/super-admin/payments/${paymentId}/reconcile/`,
        { action, notes: `Reconciled via Super Admin Portal (${action})` },
        { headers }
      )
      .subscribe({
        next: () => {
          this.actionBanner.set(`Payment reconciled (${action}) and Tenant activated!`);
          this.loadAll();
        },
      });
  }

  toggleTenantStatus(tenantId: string, action: 'SUSPEND' | 'ACTIVATE'): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .post(
        `${API_BASE_URL}/super-admin/tenants/${tenantId}/status/`,
        { action, reason: `Super Admin manual ${action}` },
        { headers }
      )
      .subscribe({
        next: () => {
          this.actionBanner.set(`Tenant status updated (${action}).`);
          this.loadAll();
        },
      });
  }
}