from django.urls import path
from apps.operations.views import (
    CustomerInvoiceListAPIView,
    CustomerInvoicePaymentAPIView,
    CustomerListCreateAPIView,
    InventoryMovementListCreateAPIView,
    MaterialListCreateAPIView,
    ProductionJobStageUpdateAPIView,
    QuotationConvertAPIView,
    QuotationListCreateAPIView,
    SalesOrderListAPIView,
    TenantDashboardSummaryAPIView,
)

urlpatterns = [
    path("tenant/dashboard/", TenantDashboardSummaryAPIView.as_view(), name="tenant-dashboard"),
    path("tenant/customers/", CustomerListCreateAPIView.as_view(), name="tenant-customers"),
    path("tenant/materials/", MaterialListCreateAPIView.as_view(), name="tenant-materials"),
    path(
        "tenant/inventory-movements/",
        InventoryMovementListCreateAPIView.as_view(),
        name="tenant-inventory-movements",
    ),
    path("tenant/quotations/", QuotationListCreateAPIView.as_view(), name="tenant-quotations"),
    path(
        "tenant/quotations/<uuid:quotation_id>/convert/",
        QuotationConvertAPIView.as_view(),
        name="tenant-quotation-convert",
    ),
    path("tenant/orders/", SalesOrderListAPIView.as_view(), name="tenant-orders"),
    path(
        "tenant/production-jobs/<uuid:job_id>/stage/",
        ProductionJobStageUpdateAPIView.as_view(),
        name="tenant-job-stage",
    ),
    path("tenant/invoices/", CustomerInvoiceListAPIView.as_view(), name="tenant-invoices"),
    path(
        "tenant/invoices/<uuid:invoice_id>/payments/",
        CustomerInvoicePaymentAPIView.as_view(),
        name="tenant-invoice-payment",
    ),
]
