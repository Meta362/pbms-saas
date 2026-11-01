import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { API_BASE_URL, PbmsI18nService, PublicPlan, getPortalUrl } from '@pbms/shared';

interface RegistrationResult {
  idempotent_replay: boolean;
  tenant_id: string;
  tenant_slug: string;
  tenant_status: string;
  subscription_status: string;
  payment_id: string;
  payment_status: string;
  amount_usd: string;
}

@Component({
  selector: 'pbms-pub-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
})
export class AppComponent implements OnInit {
  readonly i18n = inject(PbmsI18nService);
  private readonly http = inject(HttpClient);

  readonly plans = signal<PublicPlan[]>([]);
  readonly loadingPlans = signal<boolean>(true);
  readonly planError = signal<string>('');

  selectedPlanCode = 'growth';
  billingCycle: 'MONTHLY' | 'ANNUAL' = 'MONTHLY';

  fullName = '';
  phone = '';
  email = '';
  password = '';
  businessName = '';
  businessSlug = '';
  paymentProvider: 'MANUAL_TRANSFER' | 'MOCK_LOCAL' = 'MANUAL_TRANSFER';
  providerReference = 'ABA-KHQR-900100';

  readonly submitting = signal<boolean>(false);
  readonly submitError = signal<string>('');
  readonly registrationResult = signal<RegistrationResult | null>(null);

  get tenantWorkspaceUrl(): string {
    return getPortalUrl('TENANT_WORKSPACE');
  }

  get superAdminUrl(): string {
    return getPortalUrl('SUPER_ADMIN');
  }

  ngOnInit(): void {
    this.fetchPlans();
  }

  fetchPlans(): void {
    this.loadingPlans.set(true);
    this.http.get<PublicPlan[]>(`${API_BASE_URL}/public/plans/`).subscribe({
      next: (data) => {
        this.plans.set(data);
        this.loadingPlans.set(false);
      },
      error: () => {
        this.planError.set(
          `Cannot connect to Backend API (${API_BASE_URL}). Please ensure the Django server is running.`
        );
        this.loadingPlans.set(false);
      },
    });
  }

  selectPlan(code: string): void {
    this.selectedPlanCode = code;
  }

  autoSlug(name: string): void {
    this.businessSlug = name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '');
  }

  submitRegistration(): void {
    this.submitError.set('');
    this.registrationResult.set(null);
    this.submitting.set(true);

    const idempotencyKey = `web-reg-${this.businessSlug}-${Date.now()}`;
    const payload = {
      full_name: this.fullName,
      email: this.email,
      password: this.password,
      phone: this.phone,
      business_name: this.businessName,
      business_slug: this.businessSlug,
      plan_code: this.selectedPlanCode,
      billing_cycle: this.billingCycle,
      payment_provider: this.paymentProvider,
      provider_reference: this.providerReference,
      idempotency_key: idempotencyKey,
    };

    this.http
      .post<RegistrationResult>(`${API_BASE_URL}/public/register-tenant/`, payload)
      .subscribe({
        next: (res) => {
          this.registrationResult.set(res);
          this.submitting.set(false);
        },
        error: (err) => {
          const detail =
            err?.error?.detail ||
            JSON.stringify(err?.error || 'Registration failed. Check inputs and password length (>=10 chars).');
          this.submitError.set(detail);
          this.submitting.set(false);
        },
      });
  }
}