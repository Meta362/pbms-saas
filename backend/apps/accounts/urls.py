from django.urls import path
from apps.accounts.views import (
    CurrentUserAPIView,
    LoginAPIView,
    LogoutAPIView,
    RefreshTokenAPIView,
    TenantWorkspaceContextAPIView,
)

urlpatterns = [
    path("auth/login/", LoginAPIView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshTokenAPIView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutAPIView.as_view(), name="auth-logout"),
    path("auth/me/", CurrentUserAPIView.as_view(), name="auth-me"),
    path("tenant/context/", TenantWorkspaceContextAPIView.as_view(), name="tenant-context"),
]
