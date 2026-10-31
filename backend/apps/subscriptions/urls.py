from django.urls import path
from apps.subscriptions.views import (
    PublicPlanListAPIView,
    PublicTenantRegistrationAPIView,
    SuperAdminOverviewAPIView,
    SuperAdminPaymentReconcileAPIView,
    SuperAdminTenantListAPIView,
    SuperAdminTenantStatusAPIView,
    SuperAdminUsbLicenseVerifyAPIView,
    SuperAdminUsbLicenseRevokeAPIView,
)

urlpatterns = [
    # Frontend C: Public SaaS Website endpoints
    path("public/plans/", PublicPlanListAPIView.as_view(), name="public-plans"),
    path(
        "public/register-tenant/",
        PublicTenantRegistrationAPIView.as_view(),
        name="public-register-tenant",
    ),
    # Frontend A: Super Admin Portal endpoints
    path(
        "super-admin/overview/",
        SuperAdminOverviewAPIView.as_view(),
        name="super-admin-overview",
    ),
    path(
        "super-admin/tenants/",
        SuperAdminTenantListAPIView.as_view(),
        name="super-admin-tenants",
    ),
    path(
        "super-admin/payments/<uuid:payment_id>/reconcile/",
        SuperAdminPaymentReconcileAPIView.as_view(),
        name="super-admin-payment-reconcile",
    ),
    path(
        "super-admin/tenants/<uuid:tenant_id>/status/",
        SuperAdminTenantStatusAPIView.as_view(),
        name="super-admin-tenant-status",
    ),
    path(
        "super-admin/license/verify/",
        SuperAdminUsbLicenseVerifyAPIView.as_view(),
        name="super-admin-usb-license-verify",
    ),
    path(
        "super-admin/license/revoke/",
        SuperAdminUsbLicenseRevokeAPIView.as_view(),
        name="super-admin-usb-license-revoke",
    ),
]
