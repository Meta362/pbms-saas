import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { API_BASE_URL, PbmsI18nService, PbmsSessionClient, UserProfile } from '@pbms/shared';

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
  readonly activeTenantName = signal<string>('');
  email = 'owner@angkorprint.com';
  password = 'Owner@PBMS2026';

  activeTab: 'DASHBOARD' | 'QUOTATIONS' | 'PRODUCTION' | 'INVENTORY' | 'INVOICES' = 'DASHBOARD';
  readonly stages = ['PENDING', 'PRE_PRESS', 'PRINTING', 'FINISHING', 'QC', 'COMPLETED'];

  readonly errorMsg = signal<string>('');
  readonly bannerMsg = signal<string>('');

  readonly dashboard = signal<any | null>(null);
  readonly customers = signal<any[]>([]);
  readonly quotations = signal<any[]>([]);
  readonly orders = signal<any[]>([]);
  readonly materials = signal<any[]>([]);
  readonly invoices = signal<any[]>([]);

  // Form bindings
  custName = '';
  custCompany = '';
  custPhone = '';

  quoteCustomerId = '';
  quoteTitle = '1,000 Business Cards (2-Side Matte)';
  quoteSpec = '300gsm Art Card, 90x54mm';
  quoteQty = 1000;
  quoteUnitPrice = '0.0350';
  quoteSetup = '5.00';
  quoteFinishing = '10.00';
  quoteDiscount = '0.00';

  moveMaterialId = '';
  moveType = 'CONSUMPTION';
  moveQty = '50.000';
  moveNote = 'Press run consumption';

  paymentAmounts: Record<string, string> = {};

  ngOnInit(): void {
    const existing = this.session.getStoredUser(this.STORAGE_KEY);
    if (existing && existing.memberships.length > 0) {
      this.user.set(existing);
      this.activeTenantName.set(existing.memberships[0].tenant_name);
      this.loadWorkspaceData();
    }
  }

  login(): void {
    this.errorMsg.set('');
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
        this.loadWorkspaceData();
      },
      error: (err) => {
        this.errorMsg.set(err?.error?.detail || 'Login failed.');
      },
    });
  }

  logout(): void {
    this.session.logout(this.STORAGE_KEY).subscribe(() => {
      this.user.set(null);
    });
  }

  loadWorkspaceData(): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http.get(`${API_BASE_URL}/tenant/dashboard/`, { headers }).subscribe({
      next: (d) => this.dashboard.set(d),
    });
    this.http.get<any[]>(`${API_BASE_URL}/tenant/customers/`, { headers }).subscribe({
      next: (list) => {
        this.customers.set(list);
        if (list.length > 0 && !this.quoteCustomerId) {
          this.quoteCustomerId = list[0].id;
        }
      },
    });
    this.http.get<any[]>(`${API_BASE_URL}/tenant/quotations/`, { headers }).subscribe({
      next: (list) => this.quotations.set(list),
    });
    this.http.get<any[]>(`${API_BASE_URL}/tenant/orders/`, { headers }).subscribe({
      next: (list) => this.orders.set(list),
    });
    this.http.get<any[]>(`${API_BASE_URL}/tenant/materials/`, { headers }).subscribe({
      next: (list) => {
        this.materials.set(list);
        if (list.length > 0 && !this.moveMaterialId) {
          this.moveMaterialId = list[0].id;
        }
      },
    });
    this.http.get<any[]>(`${API_BASE_URL}/tenant/invoices/`, { headers }).subscribe({
      next: (list) => {
        this.invoices.set(list);
        list.forEach((inv) => {
          if (!this.paymentAmounts[inv.id]) {
            this.paymentAmounts[inv.id] = inv.balance_due_usd;
          }
        });
      },
    });
  }

  createCustomer(): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http
      .post(
        `${API_BASE_URL}/tenant/customers/`,
        { name: this.custName, company_name: this.custCompany, phone: this.custPhone },
        { headers }
      )
      .subscribe({
        next: () => {
          this.custName = '';
          this.custCompany = '';
          this.custPhone = '';
          this.bannerMsg.set('Customer added successfully.');
          this.loadWorkspaceData();
        },
      });
  }

  createQuotation(): void {
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
          this.bannerMsg.set('Quotation calculated and saved.');
          this.loadWorkspaceData();
        },
      });
  }

  convertQuote(quotationId: string): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http
      .post(
        `${API_BASE_URL}/tenant/quotations/${quotationId}/convert/`,
        { artwork_file_name: 'approved_artwork_cmyk.pdf' },
        { headers }
      )
      .subscribe({
        next: () => {
          this.bannerMsg.set('Quotation converted into Sales Order, Production Job, and Invoice!');
          this.loadWorkspaceData();
          this.activeTab = 'PRODUCTION';
        },
      });
  }

  updateJobStage(jobId: string, stage: string): void {
    const headers = this.session.getHeaders(this.STORAGE_KEY, true);
    this.http
      .post(
        `${API_BASE_URL}/tenant/production-jobs/${jobId}/stage/`,
        { stage, operator_notes: `Transitioned to ${stage}` },
        { headers }
      )
      .subscribe({
        next: () => {
          this.bannerMsg.set(`Production job stage updated to ${stage}.`);
          this.loadWorkspaceData();
        },
      });
  }

  recordStockMovement(): void {
    this.errorMsg.set('');
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
          this.bannerMsg.set('Immutable inventory ledger transaction recorded.');
          this.loadWorkspaceData();
        },
        error: (err) => {
          this.errorMsg.set(JSON.stringify(err?.error || 'Stock movement rejected.'));
        },
      });
  }

  recordInvoicePayment(invoiceId: string): void {
    this.errorMsg.set('');
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
          this.bannerMsg.set(`Payment of USD ${amount} allocated to invoice.`);
          this.loadWorkspaceData();
        },
        error: (err) => {
          this.errorMsg.set(JSON.stringify(err?.error || 'Payment failed.'));
        },
      });
  }
}