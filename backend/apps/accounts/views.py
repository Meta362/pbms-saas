from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.accounts.jwt_service import create_session_and_issue_tokens, rotate_refresh_token
from apps.accounts.models import AuthSession
from apps.accounts.serializers import LoginRequestSerializer, RefreshTokenRequestSerializer
from apps.core.models import AuditEvent
from apps.tenants.models import TenantMembership, TenantStatus
from apps.tenants.permissions import HasActiveTenantMembership


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _serialize_user_memberships(user) -> list[dict]:
    memberships = TenantMembership.objects.select_related("tenant").filter(
        user=user,
        is_active=True,
        tenant__status=TenantStatus.ACTIVE,
    )
    return [
        {
            "tenant_id": str(m.tenant.id),
            "tenant_name": m.tenant.name,
            "tenant_slug": m.tenant.slug,
            "role": m.role,
            "base_currency": m.tenant.base_currency,
            "khr_exchange_rate": str(m.tenant.khr_exchange_rate),
        }
        for m in memberships
    ]


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].lower().strip()
        password = serializer.validated_data["password"]
        ip_addr = _get_client_ip(request)

        user = authenticate(request=request, username=email, password=password)
        if user is None or not user.is_active:
            AuditEvent.objects.create(
                event_type="AUTH_LOGIN_FAILED",
                target_model="accounts.User",
                ip_address=ip_addr,
                metadata={"attempted_email": email},
            )
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        tokens = create_session_and_issue_tokens(
            user=user,
            ip_address=ip_addr,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        return Response(
            {
                **tokens,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "platform_role": user.platform_role,
                    "preferred_language": user.preferred_language,
                    "memberships": _serialize_user_memberships(user),
                },
            },
            status=status.HTTP_200_OK,
        )


class RefreshTokenAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = RefreshTokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            tokens = rotate_refresh_token(
                raw_refresh_token=serializer.validated_data["refresh_token"],
                ip_address=_get_client_ip(request),
            )
        except AuthenticationFailed as exc:
            return Response(
                {"detail": str(exc.detail)},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(tokens, status=status.HTTP_200_OK)


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        session: AuthSession = request.auth
        now = timezone.now()
        session.is_revoked = True
        session.revoked_at = now
        session.revoked_reason = "USER_LOGOUT"
        session.save(update_fields=["is_revoked", "revoked_at", "revoked_reason", "updated_at"])

        AuditEvent.objects.create(
            actor_user=request.user,
            event_type="AUTH_LOGOUT",
            target_model="accounts.AuthSession",
            target_id=str(session.id),
            ip_address=_get_client_ip(request),
        )
        return Response({"status": "revoked"}, status=status.HTTP_200_OK)


class CurrentUserAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        return Response(
            {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "platform_role": user.platform_role,
                "preferred_language": user.preferred_language,
                "memberships": _serialize_user_memberships(user),
            }
        )


class TenantWorkspaceContextAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]

    def get(self, request: Request) -> Response:
        tenant = request.tenant
        membership = request.tenant_membership
        return Response(
            {
                "tenant_id": str(tenant.id),
                "tenant_name": tenant.name,
                "tenant_slug": tenant.slug,
                "role": membership.role,
                "base_currency": tenant.base_currency,
                "khr_exchange_rate": str(tenant.khr_exchange_rate),
                "tax_rate_percent": str(tenant.tax_rate_percent),
            }
        )
