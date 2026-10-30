from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.accounts.jwt_service import create_session_and_issue_tokens, rotate_refresh_token
from apps.accounts.models import AuthSession
from apps.accounts.serializers import (
    LoginRequestSerializer,
    RefreshTokenRequestSerializer,
    TenantMembershipCreateSerializer,
    TenantMembershipSerializer,
    TenantMembershipUpdateSerializer,
)
from apps.core.models import AuditEvent
from apps.subscriptions.models import TenantSubscription
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus
from apps.tenants.permissions import HasActiveTenantMembership

User = get_user_model()


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
    allowed_tenant_roles_by_method = {
        "GET": set(TenantRole.values),
    }

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


class TenantAuditEventListAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {TenantRole.TENANT_OWNER, TenantRole.TENANT_MANAGER},
    }

    def get(self, request: Request) -> Response:
        events = AuditEvent.objects.filter(tenant=request.tenant)[:50]
        return Response(
            [
                {
                    "id": str(ev.id),
                    "created_at": ev.created_at.isoformat(),
                    "actor_user_id": str(ev.actor_user_id) if ev.actor_user_id else None,
                    "event_type": ev.event_type,
                    "target_model": ev.target_model,
                    "target_id": ev.target_id,
                    "metadata": ev.metadata,
                }
                for ev in events
            ]
        )


class TenantMembershipListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {TenantRole.TENANT_OWNER},
        "POST": {TenantRole.TENANT_OWNER},
    }

    def get(self, request: Request) -> Response:
        memberships = (
            TenantMembership.objects.select_related("user")
            .filter(tenant=request.tenant)
            .order_by("created_at")
        )
        return Response(TenantMembershipSerializer(memberships, many=True).data)

    @transaction.atomic
    def post(self, request: Request) -> Response:
        serializer = TenantMembershipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        locked_tenant = Tenant.objects.select_for_update().get(id=request.tenant.id)
        subscription = (
            TenantSubscription.objects.select_for_update()
            .select_related("plan")
            .filter(tenant=locked_tenant)
            .first()
        )
        if subscription is None:
            raise ValidationError(
                {"detail": "Tenant does not have an active subscription."}
            )

        active_staff_count = TenantMembership.objects.filter(
            tenant=locked_tenant,
            is_active=True,
        ).count()
        max_staff = subscription.plan.max_staff_users
        if active_staff_count >= max_staff:
            raise ValidationError(
                {
                    "detail": (
                        f"Plan staff limit reached ({max_staff} active staff users "
                        f"maximum for plan '{subscription.plan.code}')."
                    )
                }
            )

        staff_user = data.get("existing_user")
        if staff_user is not None:
            if TenantMembership.objects.filter(
                tenant=locked_tenant,
                user=staff_user,
            ).exists():
                raise ValidationError(
                    {"email": "This user already has a membership in this tenant."}
                )
        else:
            try:
                staff_user = User.objects.create_user(
                    email=data["email"],
                    password=data["password"],
                    full_name=data["full_name"],
                    phone=data.get("phone", ""),
                    preferred_language=data["preferred_language"],
                )
            except IntegrityError as exc:
                raise ValidationError(
                    {"email": "An account with this email already exists."}
                ) from exc

        try:
            membership = TenantMembership.objects.create(
                tenant=locked_tenant,
                user=staff_user,
                role=data["role"],
                is_active=True,
            )
        except IntegrityError as exc:
            raise ValidationError(
                {"email": "This user already has a membership in this tenant."}
            ) from exc

        AuditEvent.objects.create(
            actor_user=request.user,
            tenant=locked_tenant,
            event_type="TENANT_MEMBERSHIP_CREATED",
            target_model="tenants.TenantMembership",
            target_id=str(membership.id),
            ip_address=_get_client_ip(request),
            metadata={
                "user_id": str(staff_user.id),
                "email": staff_user.email,
                "role": membership.role,
                "is_active": membership.is_active,
            },
        )
        return Response(
            TenantMembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )


class TenantMembershipDetailAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "PATCH": {TenantRole.TENANT_OWNER},
    }

    @transaction.atomic
    def patch(self, request: Request, membership_id: str) -> Response:
        serializer = TenantMembershipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        locked_tenant = Tenant.objects.select_for_update().get(id=request.tenant.id)
        subscription = (
            TenantSubscription.objects.select_for_update()
            .select_related("plan")
            .filter(tenant=locked_tenant)
            .first()
        )
        if subscription is None:
            raise ValidationError(
                {"detail": "Tenant does not have an active subscription."}
            )

        membership = get_object_or_404(
            TenantMembership.objects.select_for_update().select_related("user"),
            id=membership_id,
            tenant=locked_tenant,
        )

        previous_role = membership.role
        previous_is_active = membership.is_active
        new_role = data.get("role", previous_role)
        new_is_active = data.get("is_active", previous_is_active)

        if (
            previous_role == TenantRole.TENANT_OWNER
            and previous_is_active
            and (new_role != TenantRole.TENANT_OWNER or not new_is_active)
        ):
            other_active_owners = (
                TenantMembership.objects.filter(
                    tenant=locked_tenant,
                    role=TenantRole.TENANT_OWNER,
                    is_active=True,
                )
                .exclude(id=membership.id)
                .count()
            )
            if other_active_owners == 0:
                raise ValidationError(
                    {
                        "detail": (
                            "Cannot deactivate or demote the last active "
                            "TENANT_OWNER of this tenant."
                        )
                    }
                )

        if not previous_is_active and new_is_active:
            active_staff_count = TenantMembership.objects.filter(
                tenant=locked_tenant,
                is_active=True,
            ).count()
            max_staff = subscription.plan.max_staff_users
            if active_staff_count >= max_staff:
                raise ValidationError(
                    {
                        "detail": (
                            f"Plan staff limit reached ({max_staff} active staff users "
                            f"maximum for plan '{subscription.plan.code}')."
                        )
                    }
                )

        membership.role = new_role
        membership.is_active = new_is_active
        membership.save(update_fields=["role", "is_active", "updated_at"])

        ip_addr = _get_client_ip(request)
        if previous_role != new_role:
            AuditEvent.objects.create(
                actor_user=request.user,
                tenant=locked_tenant,
                event_type="TENANT_MEMBERSHIP_ROLE_CHANGED",
                target_model="tenants.TenantMembership",
                target_id=str(membership.id),
                ip_address=ip_addr,
                metadata={
                    "user_id": str(membership.user_id),
                    "email": membership.user.email,
                    "previous_role": previous_role,
                    "new_role": new_role,
                },
            )
        if previous_is_active != new_is_active:
            event_type = (
                "TENANT_MEMBERSHIP_DEACTIVATED"
                if not new_is_active
                else "TENANT_MEMBERSHIP_REACTIVATED"
            )
            AuditEvent.objects.create(
                actor_user=request.user,
                tenant=locked_tenant,
                event_type=event_type,
                target_model="tenants.TenantMembership",
                target_id=str(membership.id),
                ip_address=ip_addr,
                metadata={
                    "user_id": str(membership.user_id),
                    "email": membership.user.email,
                    "role": new_role,
                    "previous_is_active": previous_is_active,
                    "new_is_active": new_is_active,
                },
            )
        if previous_role == new_role and previous_is_active == new_is_active:
            AuditEvent.objects.create(
                actor_user=request.user,
                tenant=locked_tenant,
                event_type="TENANT_MEMBERSHIP_UPDATED",
                target_model="tenants.TenantMembership",
                target_id=str(membership.id),
                ip_address=ip_addr,
                metadata={
                    "user_id": str(membership.user_id),
                    "email": membership.user.email,
                    "role": new_role,
                    "is_active": new_is_active,
                },
            )

        return Response(
            TenantMembershipSerializer(membership).data,
            status=status.HTTP_200_OK,
        )
