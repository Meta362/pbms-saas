from django.urls import path
from apps.tenants.views import (
    StaffInvitationListCreateAPIView,
    StaffInvitationRevokeAPIView,
    TenantSettingsAPIView,
)

urlpatterns = [
    path("tenant/settings/", TenantSettingsAPIView.as_view(), name="tenant-settings"),
    path("tenant/invitations/", StaffInvitationListCreateAPIView.as_view(), name="tenant-invitations"),
    path(
        "tenant/invitations/<uuid:invitation_id>/revoke/",
        StaffInvitationRevokeAPIView.as_view(),
        name="tenant-invitation-revoke",
    ),
]
