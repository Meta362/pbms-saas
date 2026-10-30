from django.urls import path
from apps.tenants.views import TenantSettingsAPIView

urlpatterns = [
    path("tenant/settings/", TenantSettingsAPIView.as_view(), name="tenant-settings"),
]
