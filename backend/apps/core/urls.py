from django.urls import path
from apps.core.views import (
    ActiveAnnouncementAPIView,
    SuperAdminAnnouncementDetailAPIView,
    SuperAdminAnnouncementListCreateAPIView,
    health_check_view,
)

urlpatterns = [
    path("health/", health_check_view, name="api-health-check"),
    path("announcements/active/", ActiveAnnouncementAPIView.as_view(), name="active-announcement"),
    path(
        "super-admin/announcements/",
        SuperAdminAnnouncementListCreateAPIView.as_view(),
        name="super-admin-announcements",
    ),
    path(
        "super-admin/announcements/<uuid:announcement_id>/",
        SuperAdminAnnouncementDetailAPIView.as_view(),
        name="super-admin-announcement-detail",
    ),
]
