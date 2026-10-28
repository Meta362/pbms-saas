from django.urls import path
from apps.core.views import health_check_view

urlpatterns = [
    path("health/", health_check_view, name="api-health-check"),
]
