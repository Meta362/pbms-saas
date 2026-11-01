from django.urls import path
from apps.accounts.views import (
    CurrentUserAPIView,
    LoginAPIView,
    LogoutAPIView,
    LogoutAllAPIView,
    PasswordResetConfirmAPIView,
    PasswordResetRequestAPIView,
    RefreshTokenAPIView,
    StaffInvitationAcceptAPIView,
    TenantAuditEventListAPIView,
    TenantMembershipDetailAPIView,
    TenantMembershipListCreateAPIView,
    TenantWorkspaceContextAPIView,
)

urlpatterns = [
    path("auth/login/", LoginAPIView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshTokenAPIView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutAPIView.as_view(), name="auth-logout"),
    path("auth/logout-all/", LogoutAllAPIView.as_view(), name="auth-logout-all"),
    path("auth/password-reset/", PasswordResetRequestAPIView.as_view(), name="auth-password-reset"),
    path("auth/password-reset-confirm/", PasswordResetConfirmAPIView.as_view(), name="auth-password-reset-confirm"),
    path("auth/accept-invitation/", StaffInvitationAcceptAPIView.as_view(), name="auth-accept-invitation"),
    path("auth/me/", CurrentUserAPIView.as_view(), name="auth-me"),
    path("tenant/context/", TenantWorkspaceContextAPIView.as_view(), name="tenant-context"),
    path("tenant/audit-events/", TenantAuditEventListAPIView.as_view(), name="tenant-audit-events"),
    path("tenant/audit-logs/", TenantAuditEventListAPIView.as_view(), name="tenant-audit-logs"),
    path(
        "tenant/memberships/",
        TenantMembershipListCreateAPIView.as_view(),
        name="tenant-memberships",
    ),
    path(
        "tenant/memberships/<uuid:membership_id>/",
        TenantMembershipDetailAPIView.as_view(),
        name="tenant-membership-detail",
    ),
]
