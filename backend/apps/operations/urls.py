from django.urls import path
from apps.operations.views import (
    CustomerDetailAPIView,
    CustomerInvoiceDetailAPIView,
    CustomerInvoiceKhqrAPIView,
    CustomerInvoiceKhqrVerifyAPIView,
    CustomerInvoiceListAPIView,
    CustomerInvoicePaymentAPIView,
    CustomerInvoiceVoidAPIView,
    CustomerListCreateAPIView,
    CustomerReceivablesReportAPIView,
    DailySalesReportAPIView,
    ImpositionCalculatorAPIView,
    InventoryAlertsReportAPIView,
    InventoryMovementListCreateAPIView,
    MaterialDetailAPIView,
    MaterialListCreateAPIView,
    MaterialSeedPresetsAPIView,
    ProductionJobDetailAPIView,
    ProductionJobListAPIView,
    ProductionJobStageUpdateAPIView,
    ProductionQueueReportAPIView,
    QuotationApproveAPIView,
    QuotationConvertAPIView,
    QuotationDetailAPIView,
    QuotationListCreateAPIView,
    QuotationRejectAPIView,
    SalesOrderCancelAPIView,
    SalesOrderCompleteAPIView,
    SalesOrderDetailAPIView,
    SalesOrderListAPIView,
    TenantDashboardSummaryAPIView,
    TenantPaymentListAPIView,
    VatSalesJournalReportAPIView,
)

urlpatterns = [
    # Dashboard & Operational Summary
    path("tenant/dashboard/", TenantDashboardSummaryAPIView.as_view(), name="tenant-dashboard"),

    # Customers & Master Materials
    path("tenant/customers/", CustomerListCreateAPIView.as_view(), name="tenant-customers"),
    path("tenant/customers/<uuid:customer_id>/", CustomerDetailAPIView.as_view(), name="tenant-customer-detail"),
    path("tenant/materials/", MaterialListCreateAPIView.as_view(), name="tenant-materials"),
    path("tenant/materials/<uuid:material_id>/", MaterialDetailAPIView.as_view(), name="tenant-material-detail"),
    path("tenant/materials/seed-presets/", MaterialSeedPresetsAPIView.as_view(), name="tenant-material-seed-presets"),
    path(
        "tenant/inventory-movements/",
        InventoryMovementListCreateAPIView.as_view(),
        name="tenant-inventory-movements",
    ),

    # Quotations Lifecycle
    path("tenant/quotations/", QuotationListCreateAPIView.as_view(), name="tenant-quotations"),
    path(
        "tenant/quotations/<uuid:quotation_id>/",
        QuotationDetailAPIView.as_view(),
        name="tenant-quotation-detail",
    ),
    path(
        "tenant/quotations/<uuid:quotation_id>/approve/",
        QuotationApproveAPIView.as_view(),
        name="tenant-quotation-approve",
    ),
    path(
        "tenant/quotations/<uuid:quotation_id>/reject/",
        QuotationRejectAPIView.as_view(),
        name="tenant-quotation-reject",
    ),
    path(
        "tenant/quotations/<uuid:quotation_id>/convert/",
        QuotationConvertAPIView.as_view(),
        name="tenant-quotation-convert",
    ),

    # Sales Orders & Production Jobs
    path("tenant/orders/", SalesOrderListAPIView.as_view(), name="tenant-orders"),
    path("tenant/orders/<uuid:order_id>/", SalesOrderDetailAPIView.as_view(), name="tenant-order-detail"),
    path("tenant/orders/<uuid:order_id>/complete/", SalesOrderCompleteAPIView.as_view(), name="tenant-order-complete"),
    path("tenant/orders/<uuid:order_id>/cancel/", SalesOrderCancelAPIView.as_view(), name="tenant-order-cancel"),
    path("tenant/production-jobs/", ProductionJobListAPIView.as_view(), name="tenant-production-jobs"),
    path("tenant/production-jobs/<uuid:job_id>/", ProductionJobDetailAPIView.as_view(), name="tenant-production-job-detail"),
    path(
        "tenant/production-jobs/<uuid:job_id>/stage/",
        ProductionJobStageUpdateAPIView.as_view(),
        name="tenant-job-stage",
    ),

    # Invoices & Payments
    path("tenant/invoices/", CustomerInvoiceListAPIView.as_view(), name="tenant-invoices"),
    path("tenant/invoices/<uuid:invoice_id>/", CustomerInvoiceDetailAPIView.as_view(), name="tenant-invoice-detail"),
    path("tenant/invoices/<uuid:invoice_id>/void/", CustomerInvoiceVoidAPIView.as_view(), name="tenant-invoice-void"),
    path(
        "tenant/invoices/<uuid:invoice_id>/payments/",
        CustomerInvoicePaymentAPIView.as_view(),
        name="tenant-invoice-payment",
    ),
    path(
        "tenant/invoices/<uuid:invoice_id>/khqr/",
        CustomerInvoiceKhqrAPIView.as_view(),
        name="tenant-invoice-khqr",
    ),
    path(
        "tenant/invoices/<uuid:invoice_id>/khqr/verify/",
        CustomerInvoiceKhqrVerifyAPIView.as_view(),
        name="tenant-invoice-khqr-verify",
    ),
    path("tenant/payments/", TenantPaymentListAPIView.as_view(), name="tenant-payments"),

    # Tools & Calculations
    path(
        "tenant/tools/imposition/",
        ImpositionCalculatorAPIView.as_view(),
        name="tenant-tool-imposition",
    ),

    # Reports
    path(
        "tenant/reports/vat-sales-journal/",
        VatSalesJournalReportAPIView.as_view(),
        name="tenant-report-vat-sales",
    ),
    path(
        "tenant/reports/daily-sales/",
        DailySalesReportAPIView.as_view(),
        name="tenant-report-daily-sales",
    ),
    path(
        "tenant/reports/inventory-alerts/",
        InventoryAlertsReportAPIView.as_view(),
        name="tenant-report-inventory-alerts",
    ),
    path(
        "tenant/reports/receivables/",
        CustomerReceivablesReportAPIView.as_view(),
        name="tenant-report-receivables",
    ),
    path(
        "tenant/reports/production-queue/",
        ProductionQueueReportAPIView.as_view(),
        name="tenant-report-production-queue",
    ),
]
