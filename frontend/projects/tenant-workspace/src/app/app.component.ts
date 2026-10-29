import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import {
  API_BASE_URL,
  PbmsI18nService,
  PbmsSessionClient,
  TenantContext,
  TenantMembershipItem,
  UserProfile,
  formatApiErrorMessage,
  isSubscriptionDenialError,
} from '@pbms/shared';

export type WorkspaceTab =
  | 'DASHBOARD'
  | 'QUOTATIONS'
  | 'PRODUCTION'
  | 'INVENTORY'
  | 'INVOICES'
  | 'MEMBERSHIPS';

@Component({
  selector: 'pbms-tenant-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
})
export class AppComponent implements OnInit {
  private readonly STORAGE_KEY = 'pbms_tenant_staff';
  readonly i18n = inject(PbmsI18nService);
  private readonly session = inject(PbmsSessionClient);
  private readonly http = inject(HttpClient);

  readonly user = signal<UserProfile | null>(null);
  readonly tenantContext = signal<TenantContext | null>(null);
  readonly activeTenantName = signal<string>('');
  email = 'owner@angkorprint.com';
  password = 'Owner@PBMS2026';

  activeTab: WorkspaceTab = 'DASHBOARD';
  readonly stages = ['PENDING', 'PRE_PRESS', 'PRINTING', 'FINISHING', 'QC', 'COMPLETED'];
  readonly staffRoles = [
    'TENANT_OWNER',
    'TENANT_MANAGER',
    'SALES_STAFF',
    'DESIGNER',
    'PRODUCTION_STAFF',
    'INVENTORY_STAFF',
    'FINANCE_STAFF',
  ];

  readonly errorMsg = signal<string>('');
  readonly bannerMsg = signal<string>('');
  readonly subscriptionGateError = signal<string>('');

  readonly dashboard = signal<any | null>(null);
  readonly customers = signal<any[]>([]);
  readonly quotations = signal<any[]>([]);
  readonly orders = signal<any[]>([]);
  readonly materials = signal<any[]>([]);
  readonly invoices = signal<any[]>([]);
  readonly memberships = signal<TenantMembershipItem[]>([]);

  // Form bindings - Customer
  custName = '';
  custCompany = '';
  custPhone = '';

  // Form bindings - Quotation
  quoteCustomerId = '';
  quoteTitle = '1,000 Business Cards (2-Side Matte)';
  quoteSpec = '300gsm Art Card, 90x54mm';
  quoteQty = 1000;
  quoteUnitPrice = '0.0350';
  quoteSetup = '5.00';
  quoteFinishing = '10.00';
  quoteDiscount = '0.00';

  // Form bindings - Inventory movement
  moveMaterialId = '';
  moveType = 'CONSUMPTION';
  moveQty = '50.000';
  moveNote = 'Press run consumption';

  // Form bindings - Invoices
  paymentAmounts: Record<string, string> = {};

  // Form bindings - Staff Memberships
  staffEmail = '';
  staffFullName = '';
  staffPhone = '';
  staffPassword = '';
  staffRole = 'SALES_STAFF';
  readonly submittingStaff = signal<boolean>(false);
  readonly updatingStaffId = signal<string | null>(null);
  readonly staffActionError = signal<string>('');

  // Mutation in-flight signals for idempotency and duplicate click prevention
  readonly submittingCustomer = signal<boolean>(false);
  readonly submittingQuote = signal<boolean>(false);
  readonly convertingQuoteId = signal<string | null>(null);
  readonly updatingJobId = signal<string | null>(null);
  readonly submittingMovement = signal<boolean>(false);
  readonly payingInvoiceId = signal<string | null>(null);

  readonly currentRole = computed<string>(() => {
    const ctx = this.tenantContext();
    if (ctx?.role) return ctx.role;
    const u = this.user();
    if (u && u.memberships.length > 0) return u.memberships[0].role;
    return '';
  });

  readonly isOwner = computed<boolean>(() => this.currentRole() === 'TENANT_OWNER');
  readonly isManager = computed<boolean>(() => this.currentRole() === 'TENANT_MANAGER');
  readonly isSales = computed<boolean>(() => this.currentRole() === 'SALES_STAFF');
  readonly isDesigner = computed<boolean>(() => this.currentRole() === 'DESIGNER');
  readonly isProduction = computed<boolean>(() => this.currentRole() === 'PRODUCTION_STAFF');
  readonly isInventory = computed<boolean>(() => this.currentRole() === 'INVENTORY_STAFF');
  readonly isFinance = computed<boolean>(() => this.currentRole() === 'FINANCE_STAFF');

  ngOnInit(): void {
    const existing = this.session.getStoredUser(this.STORAGE_KEY);
    if (existing && existing.memberships.length > 0) {
      this.user.set(existing);
      this.activeTenantName.set(existing.memberships[0].tenant_name);
      this.fetchTenantContextAndLoad();
    }
  }

  canAccessTab(tab: WorkspaceTab): boolean {
    const role = this.currentRole();
    switch (tab) {
      case 'DASHBOARD':
        return role !== 'DESIGNER';
      case 'QUOTATIONS':
        return (
          role === 'TENANT_OWNER' ||
          role === 'TENANT_MANAGER' ||
          role === 'SALES_STAFF' ||
          role === 'FINANCE_STAFF'
        );
      case 'PRODUCTION':
        return true; // all staff can view production
      case 'INVENTORY':
        return (
          role === 'TENANT_OWNER' ||
          role === 'TENANT_MANAGER' ||
          role === 'INVENTORY_STAFF' ||
          role === 'PRODUCTION_STAFF' ||
          role === 'SALES_STAFF'
        );
      case 'INVOICES':
        return (
          role === 'TENANT_OWNER' ||
          role === 'TENANT_MANAGER' ||
          role === 'FINANCE_STAFF' ||
          role === 'SALES_STAFF'
        );
      case 'MEMBERSHIPS':
        return role === 'TENANT_OWNER';
      default:
        return false;
    }
  }

  canMutateQuotes(): boolean {
    const role = this.currentRole();
    return role === 'TENANT_OWNER' || role === 'TENANT_MANAGER' || role === 'SALES_STAFF';
  }

  canMutateStock(): boolean {
    const role = this.currentRole();
    return (
      role === 'TENANT_OWNER' ||
      role === 'TENANT_MANAGER' ||
      role === 'INVENTORY_STAFF' ||
      role === 'PRODUCTION_STAFF'
    );
  }

  canMutateInvoices(): boolean {
    const role = this.currentRole();
    return role === 'TENANT_OWNER' || role === 'TENANT_MANAGER' || role === 'FINANCE_STAFF';
  }

  canTransitionStage(jobStage: string, targetStage: string): boolean {
    const role = this.currentRole();
    if (role === 'TENANT_OWNER' || role === 'TENANT_MANAGER') return true;
    if (role === 'DESIGNER') {
      return jobStage === 'PENDING' && targetStage === 'PRE_PRESS';
    }
    if (role === 'PRODUCTION_STAFF') {
      return targetStage !== 'PENDING';
    }
    return false;
  }

  private handleReadError(err: any, fallbackMessage: string, retryFn?: () => void): void {
    if (err?.status === 401) {
      this.session.refreshToken(this.STORAGE_KEY).subscribe({
        next: () => {
          if (retryFn) {
            retryFn();
          } else {
            this.loadWorkspaceData(false);
          }
        },
        error: () => {
          this.logout('Session expired. Please sign in again.');
        },
      });
      return;
    }

    if (isSubscriptionDenialError(err)) {
      const msg = formatApiErrorMessage(err, 'Tenant subscription billing period has expired.');
      this.subscriptionGateError.set(msg);
      return;
    }

    const message = formatApiErrorMessage(err, fallbackMessage);
    this.errorMsg.set(message);
  }

  private handleMutationError(
    err: any,
    mutationName: string,
    fallbackMessage: string,
    onSuccessRefresh?: () => void
  ): void {
    this.bannerMsg.set(''); // Prevent stale success message on error
    if (err?.status === 401) {
      this.session.refreshToken(this.STORAGE_KEY).subscribe({
        next: () => {
          this.errorMsg.set(
            `Session refreshed. ${mutationName} was not submitted. Please verify entered data and submit again.`
          );
          if (onSuccessRefresh) {
            onSuccessRefresh();
          } else {
            this.loadWorkspaceData(false);
          }
        },
        error: () => {
          this.logout('Session expired. Please sign in again.');
        },
      });
      return;
    }

    if (isSubscriptionDenialError(err)) {
      const msg = formatApiErrorMessage(err, 'Tenant subscription billing period has expired.');
      this.subscriptionGateError.set(msg);
      return;
    }

    const message = formatApiErrorMessage(err, fallbackMessage);
    this.errorMsg.set(message);
  }

  login(): void {
    this.errorMsg.set('');
    this.subscriptionGateError.set('');
    this.session.login(this.email, this.password, this.STORAGE_KEY).subscribe({
      next: (res) => {
        if (res.user.memberships.length === 0) {
          this.session.clearStorage(this.STORAGE_KEY);
          this.errorMsg.set(
            'Your tenant account is awaiting Super Admin payment verification (PENDING_REVIEW).'
          );
          return;
        }
        this.user.set(res.user);
        this.activeTenantName.set(res.user.memberships[0].tenant_name);
        this.fetchTenantContextAndLoad();
      },
      error: (err) => {
        this.errorMsg.set(formatApiErrorMessage(err, 'Login failed. Check email and password.'));
      },
    });
  }

  logout(customErrorMsg = ''): void {
    this.session.logout(this.STORAGE_KEY).subscribe({
      next: () => {
        this.resetState(customErrorMsg);
      },
      error: () => {
        this.resetState(customErrorMsg);
      },
    });
  }

  private resetState(customErrorMsg = ''): void {
    this.user.set(null);
    this.tenantContext.set(null);
    this.dashboard.set(null);
    this.customers.set([]);
    this.quotations.set([]);
    this.orders.set([]);
    this.materials.set([]);
    this.invoices.set([]);
    this.memberships.set([]);
    this.subscriptionGateError.set('');
    this.bannerMsg.set('');
    this.errorMsg.set(customErrorMsg);
    this.submittingCustomer.set(false);
    this.submittingQuote.set(false);
    this.convertingQuoteId.set(null);
    this.updatingJobId.set(null);
    this.submittingMovement.set(false);
    this.payingInvoiceId.set(null);
    this.submittingStaff.set(false);
    this.updatingStaffId.set(null);
  }

  fetchTenantContextAndLoad(): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http.get<TenantContext>(`${API_BASE_URL}/tenant/context/`, { headers }).subscribe({
      next: (ctx) => {
        this.tenantContext.set(ctx);
        if (ctx.tenant_name) this.activeTenantName.set(ctx.tenant_name);
        // Default active tab to first permitted tab
        if (!this.canAccessTab(this.activeTab)) {
          this.activeTab = this.canAccessTab('DASHBOARD') ? 'DASHBOARD' : 'PRODUCTION';
        }
        this.loadWorkspaceData();
      },
      error: (err) => {
        this.handleReadError(err, 'Failed to verify tenant workspace context.', () => {
          this.fetchTenantContextAndLoad();
        });
      },
    });
  }

  loadWorkspaceData(clearMessages = true): void {
    if (clearMessages) {
      this.errorMsg.set('');
      this.subscriptionGateError.set('');
    }
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);

    if (this.canAccessTab('DASHBOARD')) {
      this.http.get(`${API_BASE_URL}/tenant/dashboard/`, { headers }).subscribe({
        next: (d) => this.dashboard.set(d),
        error: (err) => this.handleReadError(err, 'Failed to load dashboard metrics.'),
      });
      this.http.get<any[]>(`${API_BASE_URL}/tenant/customers/`, { headers }).subscribe({
        next: (list) => {
          this.customers.set(list);
          if (list.length > 0 && !this.quoteCustomerId) {
            this.quoteCustomerId = list[0].id;
          }
        },
        error: (err) => this.handleReadError(err, 'Failed to load customers.'),
      });
    }

    if (this.canAccessTab('QUOTATIONS')) {
      this.http.get<any[]>(`${API_BASE_URL}/tenant/quotations/`, { headers }).subscribe({
        next: (list) => this.quotations.set(list),
        error: (err) => this.handleReadError(err, 'Failed to load quotations.'),
      });
    }

    if (this.canAccessTab('PRODUCTION')) {
      this.http.get<any[]>(`${API_BASE_URL}/tenant/orders/`, { headers }).subscribe({
        next: (list) => this.orders.set(list),
        error: (err) => this.handleReadError(err, 'Failed to load production orders.'),
      });
    }

    if (this.canAccessTab('INVENTORY')) {
      this.http.get<any[]>(`${API_BASE_URL}/tenant/materials/`, { headers }).subscribe({
        next: (list) => {
          this.materials.set(list);
          if (list.length > 0 && !this.moveMaterialId) {
            this.moveMaterialId = list[0].id;
          }
        },
        error: (err) => this.handleReadError(err, 'Failed to load inventory materials.'),
      });
    }

    if (this.canAccessTab('INVOICES')) {
      this.http.get<any[]>(`${API_BASE_URL}/tenant/invoices/`, { headers }).subscribe({
        next: (list) => {
          this.invoices.set(list);
          list.forEach((inv) => {
            if (!this.paymentAmounts[inv.id]) {
              this.paymentAmounts[inv.id] = inv.balance_due_usd;
            }
          });
        },
        error: (err) => this.handleReadError(err, 'Failed to load customer invoices.'),
      });
    }

    if (this.canAccessTab('MEMBERSHIPS')) {
      this.loadMemberships();
    }
  }

  loadMemberships(): void {
    if (!this.canAccessTab('MEMBERSHIPS')) return;
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http.get<TenantMembershipItem[]>(`${API_BASE_URL}/tenant/memberships/`, { headers }).subscribe({
      next: (list) => this.memberships.set(list),
      error: (err) => this.handleReadError(err, 'Failed to load staff memberships.'),
    });
  }

  createStaffMember(): void {
    this.staffActionError.set('');
    if (this.submittingStaff()) return;

    if (!this.staffEmail || !this.staffFullName || !this.staffPassword) {
      this.staffActionError.set('Email, full name, and password are required.');
      return;
    }
    if (this.staffPassword.length < 10) {
      this.staffActionError.set('Staff password must be at least 10 characters.');
      return;
    }

    this.submittingStaff.set(true);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    const payload = {
      email: this.staffEmail.trim().toLowerCase(),
      full_name: this.staffFullName.trim(),
      phone: this.staffPhone.trim(),
      password: this.staffPassword,
      role: this.staffRole,
      preferred_language: 'km',
    };

    this.http
      .post<TenantMembershipItem>(`${API_BASE_URL}/tenant/memberships/`, payload, { headers })
      .subscribe({
        next: (created) => {
          this.submittingStaff.set(false);
          this.staffEmail = '';
          this.staffFullName = '';
          this.staffPhone = '';
          this.staffPassword = '';
          this.bannerMsg.set(`Staff member ${created.full_name} (${created.email}) added successfully.`);
          this.loadMemberships();
        },
        error: (err) => {
          this.submittingStaff.set(false);
          if (err?.status === 401) {
            this.handleMutationError(err, 'Staff member creation', 'Failed to add staff member.');
          } else {
            this.staffActionError.set(
              formatApiErrorMessage(err, 'Failed to add staff member. Check inputs or plan staff limit.')
            );
          }
        },
      });
  }

  updateStaffRole(membershipId: string, newRole: string): void {
    this.staffActionError.set('');
    if (this.updatingStaffId()) return;
    this.updatingStaffId.set(membershipId);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http
      .patch<TenantMembershipItem>(
        `${API_BASE_URL}/tenant/memberships/${membershipId}/`,
        { role: newRole },
        { headers }
      )
      .subscribe({
        next: (updated) => {
          this.updatingStaffId.set(null);
          this.bannerMsg.set(`Updated role for ${updated.full_name} to ${updated.role}.`);
          this.loadMemberships();
        },
        error: (err) => {
          this.updatingStaffId.set(null);
          if (err?.status === 401) {
            this.handleMutationError(err, 'Staff role update', 'Failed to update staff member role.');
          } else {
            this.staffActionError.set(
              formatApiErrorMessage(err, 'Failed to update staff member role.')
            );
          }
        },
      });
  }

  toggleStaffActive(membership: TenantMembershipItem): void {
    this.staffActionError.set('');
    if (this.updatingStaffId()) return;
    this.updatingStaffId.set(membership.id);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    const newActive = !membership.is_active;
    this.http
      .patch<TenantMembershipItem>(
        `${API_BASE_URL}/tenant/memberships/${membership.id}/`,
        { is_active: newActive },
        { headers }
      )
      .subscribe({
        next: (updated) => {
          this.updatingStaffId.set(null);
          const actionText = updated.is_active ? 'reactivated' : 'deactivated';
          this.bannerMsg.set(`Staff member ${updated.full_name} ${actionText}.`);
          this.loadMemberships();
        },
        error: (err) => {
          this.updatingStaffId.set(null);
          if (err?.status === 401) {
            this.handleMutationError(err, 'Staff status update', 'Failed to update staff status.');
          } else {
            this.staffActionError.set(
              formatApiErrorMessage(
                err,
                'Failed to update staff status. Cannot deactivate last active Tenant Owner.'
              )
            );
          }
        },
      });
  }

  createCustomer(): void {
    this.errorMsg.set('');
    if (this.submittingCustomer()) return;
    this.submittingCustomer.set(true);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http
      .post(
        `${API_BASE_URL}/tenant/customers/`,
        { name: this.custName, company_name: this.custCompany, phone: this.custPhone },
        { headers }
      )
      .subscribe({
        next: () => {
          this.submittingCustomer.set(false);
          this.custName = '';
          this.custCompany = '';
          this.custPhone = '';
          this.bannerMsg.set('Customer added successfully.');
          this.loadWorkspaceData();
        },
        error: (err) => {
          this.submittingCustomer.set(false);
          this.handleMutationError(
            err,
            'New customer creation',
            'Failed to add customer. Ensure name and phone are provided.'
          );
        },
      });
  }

  createQuotation(): void {
    this.errorMsg.set('');
    if (this.submittingQuote()) return;
    this.submittingQuote.set(true);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http
      .post(
        `${API_BASE_URL}/tenant/quotations/`,
        {
          customer_id: this.quoteCustomerId,
          title: this.quoteTitle,
          specification_summary: this.quoteSpec,
          quantity: this.quoteQty,
          setup_fee_usd: this.quoteSetup,
          unit_price_usd: this.quoteUnitPrice,
          finishing_fee_usd: this.quoteFinishing,
          discount_usd: this.quoteDiscount,
        },
        { headers }
      )
      .subscribe({
        next: () => {
          this.submittingQuote.set(false);
          this.bannerMsg.set('Quotation calculated and saved.');
          this.loadWorkspaceData();
        },
        error: (err) => {
          this.submittingQuote.set(false);
          this.handleMutationError(
            err,
            'Quotation calculation',
            'Failed to save quotation. Ensure valid customer and pricing inputs.'
          );
        },
      });
  }

  convertQuote(quotationId: string): void {
    this.errorMsg.set('');
    if (this.convertingQuoteId()) return;
    this.convertingQuoteId.set(quotationId);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http
      .post(
        `${API_BASE_URL}/tenant/quotations/${quotationId}/convert/`,
        { artwork_file_name: 'approved_artwork_cmyk.pdf' },
        { headers }
      )
      .subscribe({
        next: () => {
          this.convertingQuoteId.set(null);
          this.bannerMsg.set('Quotation converted into Sales Order, Production Job, and Invoice!');
          this.loadWorkspaceData();
          this.activeTab = 'PRODUCTION';
        },
        error: (err) => {
          this.convertingQuoteId.set(null);
          this.handleMutationError(
            err,
            'Quotation conversion',
            'Quotation conversion failed. Verify subscription entitlement and order limits.'
          );
        },
      });
  }

  updateJobStage(jobId: string, stage: string): void {
    this.errorMsg.set('');
    if (this.updatingJobId()) return;
    this.updatingJobId.set(jobId);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http
      .post(
        `${API_BASE_URL}/tenant/production-jobs/${jobId}/stage/`,
        { stage, operator_notes: `Transitioned to ${stage}` },
        { headers }
      )
      .subscribe({
        next: () => {
          this.updatingJobId.set(null);
          this.bannerMsg.set(`Production job stage updated to ${stage}.`);
          this.loadWorkspaceData();
        },
        error: (err) => {
          this.updatingJobId.set(null);
          this.handleMutationError(
            err,
            'Job stage transition',
            `Cannot transition stage to ${stage}. Check role permissions.`
          );
        },
      });
  }

  recordStockMovement(): void {
    this.errorMsg.set('');
    if (this.submittingMovement()) return;
    this.submittingMovement.set(true);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http
      .post(
        `${API_BASE_URL}/tenant/inventory-movements/`,
        {
          material_id: this.moveMaterialId,
          transaction_type: this.moveType,
          quantity_delta: this.moveQty,
          reference_note: this.moveNote,
        },
        { headers }
      )
      .subscribe({
        next: () => {
          this.submittingMovement.set(false);
          this.bannerMsg.set('Immutable inventory ledger transaction recorded.');
          this.loadWorkspaceData();
        },
        error: (err) => {
          this.submittingMovement.set(false);
          this.handleMutationError(
            err,
            'Stock movement',
            'Stock movement rejected. Check non-negative constraints and role permissions.'
          );
        },
      });
  }

  recordInvoicePayment(invoiceId: string): void {
    this.errorMsg.set('');
    if (this.payingInvoiceId()) return;
    this.payingInvoiceId.set(invoiceId);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    const amount = this.paymentAmounts[invoiceId] || '0.00';
    this.http
      .post(
        `${API_BASE_URL}/tenant/invoices/${invoiceId}/payments/`,
        {
          amount_usd: amount,
          payment_method: 'KHQR_ABA',
          reference_number: `KHQR-${Date.now()}`,
        },
        { headers }
      )
      .subscribe({
        next: () => {
          this.payingInvoiceId.set(null);
          this.bannerMsg.set(`Payment of USD ${amount} allocated to invoice.`);
          this.loadWorkspaceData();
        },
        error: (err) => {
          this.payingInvoiceId.set(null);
          this.handleMutationError(err, 'Invoice payment allocation', 'Payment allocation failed.');
        },
      });
  }
}
