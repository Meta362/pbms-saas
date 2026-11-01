import hashlib
import secrets
from decimal import Decimal
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AuditEvent
from apps.subscriptions.models import TenantSubscription
from apps.tenants.models import StaffInvitation, Tenant, TenantMembership, TenantRole
from apps.tenants.permissions import HasActiveTenantMembership
from apps.tenants.serializers import (
    StaffInvitationCreateSerializer,
    StaffInvitationSerializer,
    TenantSettingsSerializer,
    TenantSettingsUpdateSerializer,
)


def _get_client_ip(request: Request) -> str | None:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class TenantSettingsAPIView(APIView):
    """
    Tenant business settings endpoint:
    - GET: All active tenant staff may view settings.
    - PATCH: Only TENANT_OWNER may update exchange rate or tax rate (per docs/RBAC.md).
    """

    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.FINANCE_STAFF,
            TenantRole.SALES_STAFF,
            TenantRole.DESIGNER,
            TenantRole.PRODUCTION_STAFF,
            TenantRole.INVENTORY_STAFF,
        },
        "PATCH": {
            TenantRole.TENANT_OWNER,
        },
    }

    def get(self, request: Request) -> Response:
        serializer = TenantSettingsSerializer(request.tenant)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def patch(self, request: Request) -> Response:
        serializer = TenantSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        locked_tenant = Tenant.objects.select_for_update().get(id=request.tenant.id)

        before_state = {
            "khr_exchange_rate": str(locked_tenant.khr_exchange_rate),
            "tax_rate_percent": str(locked_tenant.tax_rate_percent),
        }
        if "is_tax_registered" in validated:
            before_state["is_tax_registered"] = locked_tenant.is_tax_registered
        if "tax_id_number" in validated:
            before_state["tax_id_number"] = locked_tenant.tax_id_number

        update_fields = ["updated_at"]
        if "khr_exchange_rate" in validated:
            locked_tenant.khr_exchange_rate = validated["khr_exchange_rate"]
            update_fields.append("khr_exchange_rate")
        if "tax_rate_percent" in validated:
            locked_tenant.tax_rate_percent = validated["tax_rate_percent"]
            update_fields.append("tax_rate_percent")
        if "is_tax_registered" in validated:
            locked_tenant.is_tax_registered = validated["is_tax_registered"]
            update_fields.append("is_tax_registered")
            if not locked_tenant.is_tax_registered:
                locked_tenant.tax_rate_percent = Decimal("0.00")
                if "tax_rate_percent" not in update_fields:
                    update_fields.append("tax_rate_percent")
        if "tax_id_number" in validated:
            locked_tenant.tax_id_number = validated["tax_id_number"]
            update_fields.append("tax_id_number")

        locked_tenant.save(update_fields=update_fields)

        after_state = {
            "khr_exchange_rate": str(locked_tenant.khr_exchange_rate),
            "tax_rate_percent": str(locked_tenant.tax_rate_percent),
        }
        if "is_tax_registered" in validated:
            after_state["is_tax_registered"] = locked_tenant.is_tax_registered
        if "tax_id_number" in validated:
            after_state["tax_id_number"] = locked_tenant.tax_id_number

        AuditEvent.objects.create(
            actor_user=request.user,
            tenant=locked_tenant,
            event_type="TENANT_SETTINGS_UPDATED",
            target_model="tenants.Tenant",
            target_id=str(locked_tenant.id),
            ip_address=_get_client_ip(request),
            metadata={
                "before": before_state,
                "after": after_state,
                "updated_fields": [f for f in update_fields if f != "updated_at"],
            },
        )

        return Response(
            TenantSettingsSerializer(locked_tenant).data,
            status=status.HTTP_200_OK,
        )


class StaffInvitationListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {TenantRole.TENANT_OWNER, TenantRole.TENANT_MANAGER},
        "POST": {TenantRole.TENANT_OWNER, TenantRole.TENANT_MANAGER},
    }

    def get(self, request: Request) -> Response:
        invitations = StaffInvitation.objects.select_related("invited_by").filter(
            tenant=request.tenant,
        ).order_by("-created_at")
        serializer = StaffInvitationSerializer(invitations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def post(self, request: Request) -> Response:
        serializer = StaffInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        role = serializer.validated_data["role"]

        locked_tenant = Tenant.objects.select_for_update().get(id=request.tenant.id)

        # Check tenant staff limit under lock
        subscription = (
            TenantSubscription.objects.select_for_update()
            .select_related("plan")
            .filter(tenant=locked_tenant)
            .first()
        )
        if subscription:
            active_staff_count = TenantMembership.objects.filter(
                tenant=locked_tenant,
                is_active=True,
            ).count()
            pending_invites_count = StaffInvitation.objects.filter(
                tenant=locked_tenant,
                is_revoked=False,
                accepted_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).count()
            if (active_staff_count + pending_invites_count) >= subscription.plan.max_staff_users:
                raise ValidationError(
                    f"Maximum staff limit reached for plan '{subscription.plan.code}' ({subscription.plan.max_staff_users} staff)."
                )

        if TenantMembership.objects.filter(
            tenant=locked_tenant,
            user__email=email,
            is_active=True,
        ).exists():
            raise ValidationError("User is already an active member of this print shop.")

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = timezone.now() + timezone.timedelta(days=7)

        invitation = StaffInvitation.objects.create(
            tenant=locked_tenant,
            email=email,
            role=role,
            invited_by=request.user,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        AuditEvent.objects.create(
            actor_user=request.user,
            tenant=locked_tenant,
            event_type="TENANT_STAFF_INVITED",
            target_model="tenants.StaffInvitation",
            target_id=str(invitation.id),
            ip_address=_get_client_ip(request),
            metadata={"email": email, "role": role},
        )

        data = StaffInvitationSerializer(invitation).data
        data["invitation_token"] = raw_token  # returned for portfolio demo & testing delivery
        return Response(data, status=status.HTTP_201_CREATED)


class StaffInvitationRevokeAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "POST": {TenantRole.TENANT_OWNER, TenantRole.TENANT_MANAGER},
    }

    @transaction.atomic
    def post(self, request: Request, invitation_id: str) -> Response:
        invitation = get_object_or_404(
            StaffInvitation.objects.select_for_update(),
            id=invitation_id,
            tenant=request.tenant,
        )
        if invitation.accepted_at:
            raise ValidationError("Cannot revoke an invitation that has already been accepted.")

        invitation.is_revoked = True
        invitation.save(update_fields=["is_revoked", "updated_at"])

        AuditEvent.objects.create(
            actor_user=request.user,
            tenant=request.tenant,
            event_type="TENANT_STAFF_INVITATION_REVOKED",
            target_model="tenants.StaffInvitation",
            target_id=str(invitation.id),
            ip_address=_get_client_ip(request),
            metadata={"email": invitation.email},
        )

        return Response(
            {"status": "revoked", "invitation_id": str(invitation.id)},
            status=status.HTTP_200_OK,
        )
