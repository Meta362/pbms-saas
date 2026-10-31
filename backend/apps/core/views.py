from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check_view(request: Request) -> Response:
    primary_hasher = settings.PASSWORD_HASHERS[0] if settings.PASSWORD_HASHERS else ""
    db_healthy = True
    db_error = None

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
    except Exception as exc:
        db_healthy = False
        db_error = str(exc)

    http_status = status.HTTP_200_OK if db_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    response_data = {
        "status": "ok" if db_healthy else "degraded",
        "service": "pbms-backend-api",
        "version": "1.0.0",
        "argon2id_enabled": "Argon2PasswordHasher" in primary_hasher,
        "database": {
            "healthy": db_healthy,
            "engine": connection.settings_dict.get("ENGINE", "").rsplit(".", 1)[-1],
        },
        "supported_frontends": [
            "super-admin",
            "tenant-workspace",
            "public-site",
        ],
    }
    if not db_healthy:
        response_data["database"]["error"] = db_error

    return Response(response_data, status=http_status)
