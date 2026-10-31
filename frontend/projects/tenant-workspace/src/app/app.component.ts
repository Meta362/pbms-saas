import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import {
  API_BASE_URL,
  PbmsI18nService,
  PbmsSessionClient,
  TenantContext,
  TenantMembershipItem,
  TenantSettings,
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
  | 'MEMBERSHIPS'
  | 'SETTINGS'
  | 'TOOLS';

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
  email = '';
  password = '';

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
  readonly settings = signal<TenantSettings | null>(null);

  private sanitizer = inject(DomSanitizer, { optional: true });

  // KHQR Modal State (CAM-001)
  readonly activeKhqrModal = signal<boolean>(false);
  readonly khqrBundle = signal<any | null>(null);
  readonly khqrCurrency = signal<'USD' | 'KHR'>('USD');
  readonly loadingKhqr = signal<boolean>(false);
  readonly khqrCopied = signal<boolean>(false);

  // GDT Tax Invoice Modal State (CAM-001)
  readonly Math = Math;
  readonly activeTaxInvoiceModal = signal<boolean>(false);
  readonly selectedTaxInvoice = signal<any | null>(null);

  // Smart UI: Drag-and-Drop Production Kanban Board
  readonly draggedOrder = signal<any | null>(null);
  readonly dragOverStage = signal<string | null>(null);

  // Smart UI: Customizable Modular Dashboard Widgets
  readonly dashboardWidgets = signal<Array<{ id: string; titleKm: string; titleEn: string; icon: string; valueKey: string; color: string }>>([
    { id: 'orders_count', titleKm: 'ការបញ្ជាទិញសរុប (Sales Orders)', titleEn: 'Sales Orders', icon: '📦', valueKey: 'orders_count', color: 'text-slate-900 bg-white border-slate-200' },
    { id: 'active_jobs', titleKm: 'ការងារផលិតកម្មកំពុងរត់', titleEn: 'Active Production Jobs', icon: '🖨️', valueKey: 'active_jobs_count', color: 'text-indigo-600 bg-white border-slate-200' },
    { id: 'collected', titleKm: 'ប្រាក់ប្រមូលបានសរុប (USD)', titleEn: 'Collected Payments', icon: '💰', valueKey: 'total_collected_usd', color: 'text-emerald-600 bg-white border-slate-200' },
    { id: 'outstanding', titleKm: 'បំណុលអតិថិជននៅជំពាក់ (USD)', titleEn: 'Outstanding Balance', icon: '⏳', valueKey: 'outstanding_balance_usd', color: 'text-amber-600 bg-white border-slate-200' },
  ]);
  readonly draggedWidgetIndex = signal<number | null>(null);

  // Imposition Calculator State (PROD-001)
  impositionParentW = 790;
  impositionParentH = 1090;
  impositionCutW = 210;
  impositionCutH = 297;
  impositionMargin = 5;
  impositionGripper = 10;
  impositionBleed = 2;
  impositionQty = 5000;
  impositionSpoilage = 3;
  readonly impositionResult = signal<any | null>(null);
  readonly calculatingImposition = signal<boolean>(false);

  // GDT VAT Sales Journal State (REP-001)
  vatReportYear = new Date().getFullYear();
  vatReportMonth = new Date().getMonth() + 1;
  readonly vatJournalData = signal<any | null>(null);
  readonly loadingVatJournal = signal<boolean>(false);


  // Form bindings - Settings
  settingsKhrRate = '';
  settingsTaxRate = '';
  readonly loadingSettings = signal<boolean>(false);
  readonly submittingSettings = signal<boolean>(false);
  readonly settingsError = signal<string>('');

  // Form bindings - Customer
  custName = '';
  custCompany = '';
  custPhone = '';

  // Form bindings - Multi-Item Quotation (DOM-001)
  quoteCustomerId = '';
  quoteTitle = 'Corporate Identity Printing Package';
  quoteSpec = 'Comprehensive branding set (Cards, Letterheads, Envelopes)';
  quoteQty = 1000;
  quoteUnitPrice = '0.0350';
  quoteSetup = '5.00';
  quoteFinishing = '10.00';
  quoteDiscount = '0.00';

  quoteItems: Array<{
    item_title: string;
    specification_summary: string;
    quantity: number;
    unit_price_usd: string;
    setup_fee_usd: string;
    finishing_fee_usd: string;
  }> = [
    {
      item_title: '1,000 Business Cards (2-Side Matte)',
      specification_summary: '300gsm Art Card, 90x54mm, 2-side CMYK',
      quantity: 1000,
      unit_price_usd: '0.0350',
      setup_fee_usd: '5.00',
      finishing_fee_usd: '10.00',
    },
    {
      item_title: '500 Letterheads A4',
      specification_summary: '100gsm Woodfree, 1-side CMYK',
      quantity: 500,
      unit_price_usd: '0.0800',
      setup_fee_usd: '10.00',
      finishing_fee_usd: '0.00',
    },
  ];

  addQuoteLineItem(): void {
    this.quoteItems.push({
      item_title: '2 Rollup Banners (80x200cm)',
      specification_summary: 'PP Synthetic + Aluminum Stand',
      quantity: 2,
      unit_price_usd: '15.0000',
      setup_fee_usd: '5.00',
      finishing_fee_usd: '0.00',
    });
  }

  removeQuoteLineItem(index: number): void {
    if (this.quoteItems.length > 1) {
      this.quoteItems.splice(index, 1);
    }
  }

  computeItemSubtotal(item: any): number {
    const qty = Number(item.quantity) || 0;
    const unitPrice = parseFloat(item.unit_price_usd) || 0;
    const setup = parseFloat(item.setup_fee_usd) || 0;
    const finishing = parseFloat(item.finishing_fee_usd) || 0;
    return setup + (qty * unitPrice) + finishing;
  }

  computeQuoteSubtotal(): number {
    return this.quoteItems.reduce((acc, it) => acc + this.computeItemSubtotal(it), 0);
  }

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
      case 'SETTINGS':
        return true;
      case 'TOOLS':
        return true;
      default:
        return false;
    }
  }

  canMutateSettings(): boolean {
    return this.currentRole() === 'TENANT_OWNER';
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
    this.settings.set(null);
    this.settingsKhrRate = '';
    this.settingsTaxRate = '';
    this.loadingSettings.set(false);
    this.submittingSettings.set(false);
    this.settingsError.set('');
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

    if (this.canAccessTab('SETTINGS')) {
      this.loadSettings();
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
    const payload: any = {
      customer_id: this.quoteCustomerId,
      title: this.quoteTitle,
      specification_summary: this.quoteSpec,
      discount_usd: this.quoteDiscount || '0.00',
    };

    if (this.quoteItems && this.quoteItems.length > 0) {
      payload.items = this.quoteItems;
      payload.quantity = this.quoteItems.reduce((acc, it) => acc + (Number(it.quantity) || 0), 0);
    } else {
      payload.quantity = this.quoteQty;
      payload.setup_fee_usd = this.quoteSetup;
      payload.unit_price_usd = this.quoteUnitPrice;
      payload.finishing_fee_usd = this.quoteFinishing;
    }

    this.http
      .post(
        `${API_BASE_URL}/tenant/quotations/`,
        payload,
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

  getJobsForStage(stage: string): any[] {
    return this.orders().filter((o) => o.production_stage === stage);
  }

  getStageConfig(stage: string): { labelKm: string; labelEn: string; icon: string; headerBg: string; badgeBg: string } {
    switch (stage) {
      case 'PENDING':
        return { labelKm: 'រង់ចាំចាប់ផ្តើម', labelEn: 'Pending Queue', icon: '🕒', headerBg: 'bg-slate-100 border-slate-300 text-slate-800', badgeBg: 'bg-slate-200 text-slate-800' };
      case 'PRE_PRESS':
        return { labelKm: 'Artwork & Pre-Press', labelEn: 'Pre-Press Check', icon: '🎨', headerBg: 'bg-indigo-50 border-indigo-300 text-indigo-900', badgeBg: 'bg-indigo-100 text-indigo-800' };
      case 'PRINTING':
        return { labelKm: 'កំពុងបោះពុម្ព (Press)', labelEn: 'Printing on Press', icon: '🖨️', headerBg: 'bg-amber-50 border-amber-300 text-amber-900', badgeBg: 'bg-amber-100 text-amber-800' };
      case 'FINISHING':
        return { labelKm: 'កាត់ ស្រោប បត់ (Finish)', labelEn: 'Finishing & Binding', icon: '✂️', headerBg: 'bg-purple-50 border-purple-300 text-purple-900', badgeBg: 'bg-purple-100 text-purple-800' };
      case 'QC':
        return { labelKm: 'ត្រួតពិនិត្យគុណភាព (QC)', labelEn: 'Quality Control', icon: '🔍', headerBg: 'bg-teal-50 border-teal-300 text-teal-900', badgeBg: 'bg-teal-100 text-teal-800' };
      case 'COMPLETED':
        return { labelKm: 'រួចរាល់ ត្រៀមដឹកជញ្ជូន', labelEn: 'Ready for Delivery', icon: '✅', headerBg: 'bg-emerald-50 border-emerald-300 text-emerald-900', badgeBg: 'bg-emerald-100 text-emerald-800' };
      default:
        return { labelKm: stage, labelEn: stage, icon: '📋', headerBg: 'bg-slate-100 border-slate-300 text-slate-800', badgeBg: 'bg-slate-200 text-slate-800' };
    }
  }

  onJobDragStart(event: DragEvent, order: any): void {
    this.draggedOrder.set(order);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', order.production_job_id);
    }
  }

  onJobDragEnd(): void {
    this.draggedOrder.set(null);
    this.dragOverStage.set(null);
  }

  onStageDragOver(event: DragEvent, stage: string): void {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move';
    }
    this.dragOverStage.set(stage);
  }

  onStageDragLeave(stage: string): void {
    if (this.dragOverStage() === stage) {
      this.dragOverStage.set(null);
    }
  }

  onStageDrop(event: DragEvent, targetStage: string): void {
    event.preventDefault();
    this.dragOverStage.set(null);
    const order = this.draggedOrder();
    if (!order) return;
    this.draggedOrder.set(null);

    if (order.production_stage === targetStage) return;

    if (!this.canTransitionStage(order.production_stage, targetStage)) {
      this.errorMsg.set(
        `Permission Denied: Your role (${this.currentRole()}) cannot transition jobs from ${order.production_stage} to ${targetStage}.`
      );
      return;
    }

    this.updateJobStage(order.production_job_id, targetStage);
  }

  // Dashboard Widget Drag-and-Drop
  onWidgetDragStart(index: number): void {
    this.draggedWidgetIndex.set(index);
  }

  onWidgetDrop(targetIndex: number): void {
    const srcIndex = this.draggedWidgetIndex();
    if (srcIndex === null || srcIndex === targetIndex) {
      this.draggedWidgetIndex.set(null);
      return;
    }
    const list = [...this.dashboardWidgets()];
    const [moved] = list.splice(srcIndex, 1);
    list.splice(targetIndex, 0, moved);
    this.dashboardWidgets.set(list);
    this.draggedWidgetIndex.set(null);
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

  loadSettings(): void {
    if (!this.canAccessTab('SETTINGS')) return;
    this.loadingSettings.set(true);
    this.settingsError.set('');
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http.get<TenantSettings>(`${API_BASE_URL}/tenant/settings/`, { headers }).subscribe({
      next: (s) => {
        this.loadingSettings.set(false);
        this.settings.set(s);
        this.settingsKhrRate = s.khr_exchange_rate;
        this.settingsTaxRate = s.tax_rate_percent;
      },
      error: (err) => {
        this.loadingSettings.set(false);
        this.handleReadError(err, 'Failed to load tenant settings.');
      },
    });
  }

  updateSettings(): void {
    this.settingsError.set('');
    this.errorMsg.set('');
    if (this.submittingSettings()) return;

    if (!this.canMutateSettings()) {
      this.settingsError.set(
        this.i18n.t(
          'គណនីរបស់អ្នកមិនមានសិទ្ធិកែប្រែការកំណត់រោងពុម្ពឡើយ។',
          'Only Tenant Owner is authorized to modify tenant settings.'
        )
      );
      return;
    }

    this.submittingSettings.set(true);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    const payload = {
      khr_exchange_rate: this.settingsKhrRate,
      tax_rate_percent: this.settingsTaxRate,
    };

    this.http.patch<TenantSettings>(`${API_BASE_URL}/tenant/settings/`, payload, { headers }).subscribe({
      next: (updated) => {
        this.submittingSettings.set(false);
        this.settings.set(updated);
        this.settingsKhrRate = updated.khr_exchange_rate;
        this.settingsTaxRate = updated.tax_rate_percent;

        const ctx = this.tenantContext();
        if (ctx) {
          this.tenantContext.set({
            ...ctx,
            khr_exchange_rate: updated.khr_exchange_rate,
            tax_rate_percent: updated.tax_rate_percent,
          });
        }

        this.bannerMsg.set(
          this.i18n.t(
            'ការកំណត់រោងពុម្ពត្រូវបានរក្សាទុកដោយជោគជ័យ។',
            'Tenant settings saved successfully.'
          )
        );
      },
      error: (err) => {
        this.submittingSettings.set(false);
        const formatted = formatApiErrorMessage(err, 'Failed to save tenant settings.');
        this.settingsError.set(formatted);
        this.handleMutationError(
          err,
          'Tenant settings',
          'Failed to save tenant settings.',
          () => {}
        );
      },
    });
  }

  // KHQR & GDT Invoicing Methods (CAM-001)
  getSanitizedSvg(svg: string | null | undefined): SafeHtml {
    if (!svg) return '';
    if (this.sanitizer) {
      return this.sanitizer.bypassSecurityTrustHtml(svg);
    }
    return svg;
  }

  openKhqrModal(invoice: any): void {
    this.khqrBundle.set(null);
    this.activeKhqrModal.set(true);
    this.loadingKhqr.set(true);
    this.khqrCopied.set(false);
    this.khqrCurrency.set('USD');

    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http.get<any>(`${API_BASE_URL}/tenant/invoices/${invoice.id}/khqr/`, { headers }).subscribe({
      next: (bundle) => {
        this.loadingKhqr.set(false);
        this.khqrBundle.set(bundle);
      },
      error: (err) => {
        this.loadingKhqr.set(false);
        this.handleReadError(err, 'Failed to generate NBC Bakong KHQR bundle.');
      },
    });
  }

  closeKhqrModal(): void {
    this.activeKhqrModal.set(false);
    this.khqrBundle.set(null);
  }

  toggleKhqrCurrency(curr: 'USD' | 'KHR'): void {
    this.khqrCurrency.set(curr);
  }

  copyKhqrPayload(): void {
    const bundle = this.khqrBundle();
    if (!bundle) return;
    const pkg = this.khqrCurrency() === 'USD' ? bundle.usd : bundle.khr;
    if (pkg?.qr_payload && typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(pkg.qr_payload);
      this.khqrCopied.set(true);
      setTimeout(() => this.khqrCopied.set(false), 2500);
    }
  }

  openTaxInvoiceModal(invoice: any): void {
    this.selectedTaxInvoice.set(invoice);
    this.activeTaxInvoiceModal.set(true);
  }

  closeTaxInvoiceModal(): void {
    this.activeTaxInvoiceModal.set(false);
    this.selectedTaxInvoice.set(null);
  }

  printTaxInvoice(): void {
    if (typeof window !== 'undefined') {
      window.print();
    }
  }


  // Imposition & Reporting Methods (PROD-001 & REP-001)
  setImpositionPreset(preset: string): void {
    if (preset === '790x1090') { this.impositionParentW = 790; this.impositionParentH = 1090; }
    else if (preset === '650x900') { this.impositionParentW = 650; this.impositionParentH = 900; }
    else if (preset === '700x1000') { this.impositionParentW = 700; this.impositionParentH = 1000; }
    else if (preset === '330x483') { this.impositionParentW = 330; this.impositionParentH = 483; }
    this.calculateImposition();
  }

  setCutPreset(preset: string): void {
    if (preset === 'A4') { this.impositionCutW = 210; this.impositionCutH = 297; }
    else if (preset === 'A5') { this.impositionCutW = 148; this.impositionCutH = 210; }
    else if (preset === 'A6') { this.impositionCutW = 105; this.impositionCutH = 148; }
    else if (preset === 'CARD') { this.impositionCutW = 90; this.impositionCutH = 54; }
    else if (preset === 'A3') { this.impositionCutW = 297; this.impositionCutH = 420; }
    this.calculateImposition();
  }

  calculateImposition(): void {
    if (this.calculatingImposition()) return;
    this.calculatingImposition.set(true);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http.post<any>(`${API_BASE_URL}/tenant/tools/imposition/`, {
      parent_sheet_width_mm: Number(this.impositionParentW),
      parent_sheet_height_mm: Number(this.impositionParentH),
      cut_width_mm: Number(this.impositionCutW),
      cut_height_mm: Number(this.impositionCutH),
      margin_mm: Number(this.impositionMargin),
      gripper_mm: Number(this.impositionGripper),
      bleed_mm: Number(this.impositionBleed),
      target_quantity: Number(this.impositionQty),
      spoilage_percent: Number(this.impositionSpoilage),
    }, { headers }).subscribe({
      next: (res) => {
        this.calculatingImposition.set(false);
        this.impositionResult.set(res);
      },
      error: (err) => {
        this.calculatingImposition.set(false);
        this.handleReadError(err, 'Failed to calculate sheet imposition.');
      },
    });
  }

  loadVatJournal(): void {
    this.loadingVatJournal.set(true);
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http.get<any>(`${API_BASE_URL}/tenant/reports/vat-sales-journal/?year=${this.vatReportYear}&month=${this.vatReportMonth}`, { headers }).subscribe({
      next: (res) => {
        this.loadingVatJournal.set(false);
        this.vatJournalData.set(res);
      },
      error: (err) => {
        this.loadingVatJournal.set(false);
        this.handleReadError(err, 'Failed to load GDT VAT sales journal.');
      },
    });
  }

  downloadVatJournalCsv(): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http.get(`${API_BASE_URL}/tenant/reports/vat-sales-journal/?year=${this.vatReportYear}&month=${this.vatReportMonth}&export=csv`, {
      headers,
      responseType: 'text',
    }).subscribe({
      next: (csvText) => {
        if (typeof window !== 'undefined') {
          const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `gdt_vat_sales_journal_${this.vatReportYear}_${String(this.vatReportMonth).padStart(2, '0')}.csv`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }
      },
      error: (err) => {
        this.handleReadError(err, 'Failed to download GDT VAT CSV journal.');
      },
    });
  }

}
