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
    mrr_usd?: string;
    total_orders?: number;
    churn_risk_count?: number;
    active_announcements_count?: number;
  };
  recent_audit_events: Array<{
    id: string;
    created_at: string;
    event_type: string;
    target_model: string;
    target_id: string;
  }>;
}

export interface AnnouncementItem {
  id: string;
  title: string;
  message_km: string;
  message_en: string;
  level: 'INFO' | 'WARNING' | 'URGENT';
  is_active: boolean;
  created_by_email: string;
  created_at: string;
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
  email = '';
  password = '';
  readonly errorMsg = signal<string>('');
  readonly actionBanner = signal<string>('');
  readonly reconcilingPaymentId = signal<string | null>(null);
  readonly togglingTenantId = signal<string | null>(null);
  readonly impersonatingTenantId = signal<string | null>(null);
  readonly seedingTenantId = signal<string | null>(null);

  readonly overview = signal<SuperAdminOverview | null>(null);
  readonly tenants = signal<SuperAdminTenantItem[]>([]);
  readonly announcements = signal<AnnouncementItem[]>([]);

  // Announcement Creation Form State
  annTitle = '';
  annMessageKm = '';
  annMessageEn = '';
  annLevel: 'INFO' | 'WARNING' | 'URGENT' = 'INFO';
  readonly isSubmittingAnn = signal<boolean>(false);

  // SuperAdmin USB Hardware Licensing State
  readonly usbStatus = signal<'NOT_ATTACHED' | 'VERIFYING' | 'VERIFIED' | 'INVALID'>('NOT_ATTACHED');
  readonly usbLicense = signal<{ license_id: string; issued_to: string; expires_at: string; permissions: string[] } | null>(null);
  readonly elevatedToken = signal<string | null>(null);
  usbHardwareSerial = 'A4B27F91';
  readonly usbError = signal<string>('');

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
    this.announcements.set([]);
    this.actionBanner.set('');
    this.errorMsg.set(customMsg);
    this.reconcilingPaymentId.set(null);
    this.togglingTenantId.set(null);
    this.impersonatingTenantId.set(null);
    this.seedingTenantId.set(null);
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

    this.loadAnnouncements();
  }

  loadAnnouncements(): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .get<AnnouncementItem[]>(`${API_BASE_URL}/super-admin/announcements/`, { headers })
      .subscribe({
        next: (list) => this.announcements.set(list),
        error: (err) => {
          this.handleReadError(err, 'Failed to load platform announcements.');
        },
      });
  }

  createAnnouncement(): void {
    if (!this.annTitle.trim() || !this.annMessageKm.trim()) {
      this.errorMsg.set('Please provide title and Khmer announcement text.');
      return;
    }
    this.isSubmittingAnn.set(true);
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .post<AnnouncementItem>(
        `${API_BASE_URL}/super-admin/announcements/`,
        {
          title: this.annTitle.trim(),
          message_km: this.annMessageKm.trim(),
          message_en: this.annMessageEn.trim() || this.annTitle.trim(),
          level: this.annLevel,
          is_active: true,
        },
        { headers }
      )
      .subscribe({
        next: () => {
          this.isSubmittingAnn.set(false);
          this.annTitle = '';
          this.annMessageKm = '';
          this.annMessageEn = '';
          this.actionBanner.set('Global broadcast announcement published successfully!');
          this.loadAnnouncements();
          this.loadAll();
        },
        error: (err) => {
          this.isSubmittingAnn.set(false);
          this.handleMutationError(err, 'Create announcement', 'Failed to publish announcement.');
        },
      });
  }

  toggleAnnouncement(ann: AnnouncementItem): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .patch<AnnouncementItem>(
        `${API_BASE_URL}/super-admin/announcements/${ann.id}/`,
        { is_active: !ann.is_active },
        { headers }
      )
      .subscribe({
        next: () => {
          this.actionBanner.set(`Announcement "${ann.title}" active status updated.`);
          this.loadAnnouncements();
          this.loadAll();
        },
        error: (err) => this.handleMutationError(err, 'Toggle announcement', 'Failed to update announcement.'),
      });
  }

  deleteAnnouncement(annId: string): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http.delete(`${API_BASE_URL}/super-admin/announcements/${annId}/`, { headers }).subscribe({
      next: () => {
        this.actionBanner.set('Announcement deleted.');
        this.loadAnnouncements();
        this.loadAll();
      },
      error: (err) => this.handleMutationError(err, 'Delete announcement', 'Failed to delete announcement.'),
    });
  }

  impersonateTenant(tenant: SuperAdminTenantItem): void {
    this.errorMsg.set('');
    if (this.impersonatingTenantId()) return;
    this.impersonatingTenantId.set(tenant.id);
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .post<any>(
        `${API_BASE_URL}/super-admin/tenants/${tenant.id}/impersonate/`,
        {},
        { headers }
      )
      .subscribe({
        next: (res) => {
          this.impersonatingTenantId.set(null);
          localStorage.setItem(
            'pbms_impersonation_session',
            JSON.stringify({
              token: res.access_token,
              tenant_id: res.tenant_id,
              tenant_name: res.tenant_name,
              tenant_slug: res.tenant_slug,
              impersonator_email: res.impersonator_email,
              target_user_email: res.target_user_email,
              expires_in: res.expires_in,
              is_impersonation: true,
            })
          );
          localStorage.setItem('pbms_tenant_workspace_auth_access_token', res.access_token);
          localStorage.setItem('pbms_tenant_workspace_auth_current_tenant_id', res.tenant_id);
          localStorage.setItem(
            'pbms_tenant_workspace_auth_user',
            JSON.stringify({
              id: res.tenant_id,
              email: res.target_user_email,
              platform_role: 'TENANT_STAFF',
              is_platform_staff: false,
            })
          );
          this.actionBanner.set(
            `Support Mode activated for "${res.tenant_name}". Opening Tenant Workspace...`
          );
          setTimeout(() => {
            window.open('http://localhost:4201', '_blank');
          }, 600);
        },
        error: (err) => {
          this.impersonatingTenantId.set(null);
          this.handleMutationError(err, 'Support Impersonation', 'Failed to start Support Mode for tenant.');
        },
      });
  }

  seedPresets(tenant: SuperAdminTenantItem, packType: 'DIGITAL' | 'OFFSET' | 'ALL' = 'ALL'): void {
    this.errorMsg.set('');
    if (this.seedingTenantId()) return;
    this.seedingTenantId.set(tenant.id);
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .post<any>(
        `${API_BASE_URL}/super-admin/tenants/${tenant.id}/seed-presets/`,
        { pack_type: packType },
        { headers }
      )
      .subscribe({
        next: (res) => {
          this.seedingTenantId.set(null);
          this.actionBanner.set(`🌱 ${res.message} (for ${res.tenant_name})`);
        },
        error: (err) => {
          this.seedingTenantId.set(null);
          this.handleMutationError(err, 'Preset seeding', 'Failed to seed master presets.');
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

  onUsbFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files || input.files.length === 0) return;
    const file = input.files[0];
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const licenseData = JSON.parse(reader.result as string);
        this.verifyUsbDongle(licenseData, this.usbHardwareSerial);
      } catch (e: any) {
        this.usbStatus.set('INVALID');
        this.usbError.set('Malformed license.dat file: JSON parsing failed.');
      }
    };
    reader.readAsText(file);
  }

  verifyUsbDongle(licenseData: any, volumeSerial: string): void {
    this.usbStatus.set('VERIFYING');
    this.usbError.set('');
    const headers = this.session.getHeaders(this.STORAGE_KEY, false);
    this.http
      .post<any>(
        `${API_BASE_URL}/super-admin/license/verify/`,
        {
          license_data: licenseData,
          hardware_fingerprint: { volume_serial_number: volumeSerial.trim().toUpperCase() },
        },
        { headers }
      )
      .subscribe({
        next: (res) => {
          this.usbStatus.set('VERIFIED');
          this.usbLicense.set(res);
          this.elevatedToken.set(res.elevated_token);
          this.actionBanner.set(
            `SuperAdmin USB Security Dongle verified! (License: ${res.license_id.slice(0, 12)}...)`
          );
        },
        error: (err) => {
          this.usbStatus.set('INVALID');
          this.elevatedToken.set(null);
          this.usbLicense.set(null);
          this.usbError.set(
            err?.error?.detail || 'USB License verification failed. Unauthorized hardware.'
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