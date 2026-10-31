import test from 'node:test';
import assert from 'node:assert';
import '@angular/compiler';
import { Injector, runInInjectionContext } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { of } from 'rxjs';
import {
  PbmsI18nService,
  PbmsSessionClient,
} from '../projects/pbms-shared/src/public-api';
import { AppComponent as TenantAppComponent } from '../projects/tenant-workspace/src/app/app.component';

function setupMockSessionStorage(): void {
  const store = new Map<string, string>();
  globalThis.sessionStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => store.set(k, String(v)),
    removeItem: (k: string) => store.delete(k),
    clear: () => store.clear(),
    get length() {
      return store.size;
    },
    key: (i: number) => Array.from(store.keys())[i] ?? null,
  };
}

setupMockSessionStorage();

test('Smart UI: getJobsForStage filters orders by production stage', () => {
  const mockHttp = {
    get: () => of({}),
    post: () => of({}),
    patch: () => of({}),
  } as unknown as HttpClient;

  const injector = Injector.create({
    providers: [
      { provide: PbmsI18nService, useClass: PbmsI18nService },
      { provide: PbmsSessionClient, useValue: new PbmsSessionClient(mockHttp) },
      { provide: HttpClient, useValue: mockHttp },
    ],
  });

  const comp = runInInjectionContext(injector, () => new TenantAppComponent());

  comp.orders.set([
    { production_job_id: 'job-1', order_number: 'SO-0001', production_stage: 'PENDING' },
    { production_job_id: 'job-2', order_number: 'SO-0002', production_stage: 'PRINTING' },
    { production_job_id: 'job-3', order_number: 'SO-0003', production_stage: 'PRINTING' },
    { production_job_id: 'job-4', order_number: 'SO-0004', production_stage: 'COMPLETED' },
  ]);

  const pending = comp.getJobsForStage('PENDING');
  assert.strictEqual(pending.length, 1);
  assert.strictEqual(pending[0].order_number, 'SO-0001');

  const printing = comp.getJobsForStage('PRINTING');
  assert.strictEqual(printing.length, 2);

  const qc = comp.getJobsForStage('QC');
  assert.strictEqual(qc.length, 0);

  const completed = comp.getJobsForStage('COMPLETED');
  assert.strictEqual(completed.length, 1);
});

test('Smart UI: getStageConfig returns correct bilingual metadata and icons', () => {
  const mockHttp = { get: () => of({}), post: () => of({}) } as unknown as HttpClient;
  const injector = Injector.create({
    providers: [
      { provide: PbmsI18nService, useClass: PbmsI18nService },
      { provide: PbmsSessionClient, useValue: new PbmsSessionClient(mockHttp) },
      { provide: HttpClient, useValue: mockHttp },
    ],
  });

  const comp = runInInjectionContext(injector, () => new TenantAppComponent());

  const prepress = comp.getStageConfig('PRE_PRESS');
  assert.strictEqual(prepress.labelEn, 'Pre-Press Check');
  assert.strictEqual(prepress.icon, '🎨');

  const printing = comp.getStageConfig('PRINTING');
  assert.strictEqual(printing.labelEn, 'Printing on Press');
  assert.strictEqual(printing.icon, '🖨️');

  const qc = comp.getStageConfig('QC');
  assert.strictEqual(qc.labelEn, 'Quality Control');
  assert.strictEqual(qc.icon, '🔍');
});

test('Smart UI: onStageDrop validates role permissions before transitioning', () => {
  let calledUrl = '';
  let calledPayload: any = null;

  const mockHttp = {
    get: () => of({}),
    post: (url: string, payload: any) => {
      calledUrl = url;
      calledPayload = payload;
      return of({ status: 'ok' });
    },
  } as unknown as HttpClient;

  const injector = Injector.create({
    providers: [
      { provide: PbmsI18nService, useClass: PbmsI18nService },
      { provide: PbmsSessionClient, useValue: new PbmsSessionClient(mockHttp) },
      { provide: HttpClient, useValue: mockHttp },
    ],
  });

  const comp = runInInjectionContext(injector, () => new TenantAppComponent());

  // 1. Designer role: cannot move directly from PENDING to FINISHING
  comp.tenantContext.set({
    tenant_id: 't-1',
    tenant_name: 'Test Printing',
    tenant_slug: 'test-print',
    role: 'DESIGNER',
    base_currency: 'USD',
    khr_exchange_rate: '4100.00',
    tax_rate_percent: '10.00',
  });

  const order = { production_job_id: 'job-99', production_stage: 'PENDING' };
  comp.draggedOrder.set(order);

  const fakeEvent = { preventDefault: () => {} } as DragEvent;
  comp.onStageDrop(fakeEvent, 'FINISHING');

  assert.ok(comp.errorMsg().includes('Permission Denied'));
  assert.strictEqual(calledUrl, '');

  // 2. Designer role: CAN move from PENDING to PRE_PRESS
  comp.errorMsg.set('');
  comp.draggedOrder.set(order);
  comp.onStageDrop(fakeEvent, 'PRE_PRESS');

  assert.strictEqual(comp.errorMsg(), '');
  assert.ok(calledUrl.includes('/tenant/production-jobs/job-99/stage/'));
  assert.strictEqual(calledPayload.stage, 'PRE_PRESS');
});

test('Smart UI: onWidgetDrop reorders modular dashboard widgets', () => {
  const mockHttp = { get: () => of({}), post: () => of({}) } as unknown as HttpClient;
  const injector = Injector.create({
    providers: [
      { provide: PbmsI18nService, useClass: PbmsI18nService },
      { provide: PbmsSessionClient, useValue: new PbmsSessionClient(mockHttp) },
      { provide: HttpClient, useValue: mockHttp },
    ],
  });

  const comp = runInInjectionContext(injector, () => new TenantAppComponent());

  const initialWidgets = comp.dashboardWidgets();
  assert.strictEqual(initialWidgets[0].id, 'orders_count');
  assert.strictEqual(initialWidgets[1].id, 'active_jobs');

  // Drag first widget (index 0) and drop onto position 2
  comp.onWidgetDragStart(0);
  comp.onWidgetDrop(2);

  const reordered = comp.dashboardWidgets();
  assert.strictEqual(reordered[0].id, 'active_jobs');
  assert.strictEqual(reordered[2].id, 'orders_count');
});

test('Smart UI: Multi-Item Quotation Line Builder and Deterministic Calculations', () => {
  const mockHttp = { get: () => of({}), post: () => of({}) } as unknown as HttpClient;
  const injector = Injector.create({
    providers: [
      { provide: PbmsI18nService, useClass: PbmsI18nService },
      { provide: PbmsSessionClient, useValue: new PbmsSessionClient(mockHttp) },
      { provide: HttpClient, useValue: mockHttp },
    ],
  });

  const comp = runInInjectionContext(injector, () => new TenantAppComponent());

  // Initial state should have 2 default items
  assert.strictEqual(comp.quoteItems.length, 2);

  // Add line item
  comp.addQuoteLineItem();
  assert.strictEqual(comp.quoteItems.length, 3);

  // Set line item values
  // Item 0: qty 500, unit 0.15, setup 10, finish 5 => subtotal = (500 * 0.15) + 10 + 5 = 75 + 15 = 90
  comp.quoteItems[0] = {
    item_title: 'Custom Item 1',
    specification_summary: 'Test Spec 1',
    quantity: 500,
    unit_price_usd: '0.15',
    setup_fee_usd: '10.00',
    finishing_fee_usd: '5.00',
  };

  const item0Subtotal = comp.computeItemSubtotal(comp.quoteItems[0]);
  assert.strictEqual(item0Subtotal, 90);

  // Item 1: qty 1000, unit 0.10, setup 0, finish 0 => subtotal = 100
  comp.quoteItems[1] = {
    item_title: 'Custom Item 2',
    specification_summary: 'Test Spec 2',
    quantity: 1000,
    unit_price_usd: '0.10',
    setup_fee_usd: '0',
    finishing_fee_usd: '0',
  };

  const item1Subtotal = comp.computeItemSubtotal(comp.quoteItems[1]);
  assert.strictEqual(item1Subtotal, 100);

  // Remove 3rd item
  comp.removeQuoteLineItem(2);
  assert.strictEqual(comp.quoteItems.length, 2);

  // Total quote subtotal should be 190
  assert.strictEqual(comp.computeQuoteSubtotal(), 190);

  // Remove second item
  comp.removeQuoteLineItem(1);
  assert.strictEqual(comp.quoteItems.length, 1);
  assert.strictEqual(comp.computeQuoteSubtotal(), 90);

  // Attempting to remove the last item should keep at least 1 item
  comp.removeQuoteLineItem(0);
  assert.strictEqual(comp.quoteItems.length, 1);
});



test('Smart UI: Cambodia Bakong KHQR Modal and GDT Tax Invoice UI State', () => {
  let requestedUrl = '';
  const mockHttp = {
    get: (url: string) => {
      requestedUrl = url;
      return of({
        invoice_id: 'inv-123',
        invoice_number: 'INV-0001',
        khr_exchange_rate: '4100.00',
        balance_due_usd: '100.00',
        balance_due_khr: '410000',
        usd: { qr_payload: '000201010212...', qr_svg: '<svg>USD</svg>' },
        khr: { qr_payload: '000201010212...', qr_svg: '<svg>KHR</svg>' },
      });
    },
    post: () => of({}),
  } as unknown as HttpClient;

  const injector = Injector.create({
    providers: [
      { provide: PbmsI18nService, useClass: PbmsI18nService },
      { provide: PbmsSessionClient, useValue: new PbmsSessionClient(mockHttp) },
      { provide: HttpClient, useValue: mockHttp },
    ],
  });

  const comp = runInInjectionContext(injector, () => new TenantAppComponent());

  // Initial modal state
  assert.strictEqual(comp.activeKhqrModal(), false);
  assert.strictEqual(comp.activeTaxInvoiceModal(), false);
  assert.strictEqual(comp.khqrCurrency(), 'USD');

  // Open KHQR Modal
  const fakeInvoice = { id: 'inv-123', invoice_number: 'INV-0001', customer_name: 'Khmer Hotel' };
  comp.openKhqrModal(fakeInvoice);

  assert.strictEqual(comp.activeKhqrModal(), true);
  assert.ok(requestedUrl.includes('/tenant/invoices/inv-123/khqr/'));
  assert.strictEqual(comp.khqrBundle()?.invoice_number, 'INV-0001');

  // Toggle currency
  comp.toggleKhqrCurrency('KHR');
  assert.strictEqual(comp.khqrCurrency(), 'KHR');
  comp.toggleKhqrCurrency('USD');
  assert.strictEqual(comp.khqrCurrency(), 'USD');

  // Close KHQR Modal
  comp.closeKhqrModal();
  assert.strictEqual(comp.activeKhqrModal(), false);
  assert.strictEqual(comp.khqrBundle(), null);

  // Open GDT Tax Invoice Modal
  comp.openTaxInvoiceModal(fakeInvoice);
  assert.strictEqual(comp.activeTaxInvoiceModal(), true);
  assert.strictEqual(comp.selectedTaxInvoice()?.customer_name, 'Khmer Hotel');

  // Close GDT Tax Invoice Modal
  comp.closeTaxInvoiceModal();
  assert.strictEqual(comp.activeTaxInvoiceModal(), false);
  assert.strictEqual(comp.selectedTaxInvoice(), null);
});
