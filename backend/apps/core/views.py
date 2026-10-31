from django.conf import settings
from django.db import connection
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AuditEvent, PlatformAnnouncement
from apps.core.serializers import PlatformAnnouncementSerializer
from apps.tenants.permissions import HasVerifiedUsbLicense, IsPlatformSuperAdmin


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


class ActiveAnnouncementAPIView(APIView):
    """
    Public/Tenant endpoint to fetch current active system broadcast announcement.
    """
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        announcement = PlatformAnnouncement.objects.filter(is_active=True).first()
        if not announcement:
            return Response({"announcement": None}, status=status.HTTP_200_OK)
        return Response(
            {"announcement": PlatformAnnouncementSerializer(announcement).data},
            status=status.HTTP_200_OK,
        )


class SuperAdminAnnouncementListCreateAPIView(APIView):
    """
    SuperAdmin endpoint to list and broadcast new system announcements.
    """
    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin, HasVerifiedUsbLicense]

    def get(self, request: Request) -> Response:
        announcements = PlatformAnnouncement.objects.all().order_by("-created_at")
        serializer = PlatformAnnouncementSerializer(announcements, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        serializer = PlatformAnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(created_by=request.user)

        AuditEvent.objects.create(
            actor_user=request.user,
            event_type="PLATFORM_ANNOUNCEMENT_CREATED",
            target_model="core.PlatformAnnouncement",
            target_id=str(announcement.id),
            metadata={
                "title": announcement.title,
                "level": announcement.level,
                "is_active": announcement.is_active,
            },
        )
        return Response(
            PlatformAnnouncementSerializer(announcement).data,
            status=status.HTTP_201_CREATED,
        )


class SuperAdminAnnouncementDetailAPIView(APIView):
    """
    SuperAdmin endpoint to update or toggle active status of platform announcements.
    """
    permission_classes = [IsAuthenticated, IsPlatformSuperAdmin, HasVerifiedUsbLicense]

    def patch(self, request: Request, announcement_id: str) -> Response:
        announcement = get_object_or_404(PlatformAnnouncement, id=announcement_id)
        serializer = PlatformAnnouncementSerializer(announcement, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()

        AuditEvent.objects.create(
            actor_user=request.user,
            event_type="PLATFORM_ANNOUNCEMENT_UPDATED",
            target_model="core.PlatformAnnouncement",
            target_id=str(updated.id),
            metadata={
                "title": updated.title,
                "level": updated.level,
                "is_active": updated.is_active,
            },
        )
        return Response(PlatformAnnouncementSerializer(updated).data, status=status.HTTP_200_OK)

    def delete(self, request: Request, announcement_id: str) -> Response:
        announcement = get_object_or_404(PlatformAnnouncement, id=announcement_id)
        announcement_id_str = str(announcement.id)
        announcement.delete()

        AuditEvent.objects.create(
            actor_user=request.user,
            event_type="PLATFORM_ANNOUNCEMENT_DELETED",
            target_model="core.PlatformAnnouncement",
            target_id=announcement_id_str,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

