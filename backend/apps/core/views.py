from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check_view(request: Request) -> Response:
    primary_hasher = settings.PASSWORD_HASHERS[0] if settings.PASSWORD_HASHERS else ""
    return Response(
        {
            "status": "ok",
            "service": "pbms-backend-api",
            "version": "1.0.0",
            "argon2id_enabled": "Argon2PasswordHasher" in primary_hasher,
            "supported_frontends": [
                "super-admin",
                "tenant-workspace",
                "public-site",
            ],
        }
    )
