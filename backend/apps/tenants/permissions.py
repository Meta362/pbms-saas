from uuid import UUID
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView
from apps.accounts.models import PlatformRole
from apps.subscriptions.models import SubscriptionStatus
from apps.tenants.models import TenantMembership, TenantStatus


class IsPlatformSuperAdmin(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_platform_staff
            and user.platform_role == PlatformRole.SUPER_ADMIN
        )


class IsPlatformSuperAdminOrSupportReadOnly(BasePermission):
    """
    REQ-RBAC-01 & docs/RBAC.md Section 2:
    - SUPER_ADMIN has full read/write platform access.
    - PLATFORM_SUPPORT has read-only (SAFE_METHODS) access to overview/tenant status/audit views.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_active and user.is_platform_staff):
            return False
        if user.platform_role == PlatformRole.SUPER_ADMIN:
            return True
        if (
            user.platform_role == PlatformRole.PLATFORM_SUPPORT
            and request.method in SAFE_METHODS
        ):
            return True
        return False


class HasActiveTenantMembership(BasePermission):
    header_name = "HTTP_X_TENANT_ID"

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False

        raw_tenant_id = request.META.get(self.header_name, "").strip()
        if not raw_tenant_id:
            raise PermissionDenied("X-Tenant-ID header is required for tenant workspace operations.")

        try:
            tenant_uuid = UUID(raw_tenant_id)
        except ValueError as exc:
            raise PermissionDenied("Invalid X-Tenant-ID format.") from exc

        membership = (
            TenantMembership.objects.select_related(
                "tenant",
                "tenant__subscription",
                "tenant__subscription__plan",
            )
            .filter(
                user=user,
                tenant_id=tenant_uuid,
                is_active=True,
                tenant__status=TenantStatus.ACTIVE,
            )
            .first()
        )

        if not membership:
            raise PermissionDenied("Access denied: You do not have active membership in this tenant.")

        subscription = getattr(membership.tenant, "subscription", None)
        if subscription is None:
            raise PermissionDenied(
                "Access denied: Tenant does not have an active subscription."
            )
        if subscription.status not in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
        ):
            raise PermissionDenied(
                f"Access denied: Tenant subscription is not active (status: {subscription.status})."
            )
        now = timezone.now()
        if (
            subscription.current_period_end is None
            or subscription.current_period_end <= now
        ):
            raise PermissionDenied(
                "Access denied: Tenant subscription billing period has expired."
            )

        roles_by_method = getattr(view, "allowed_tenant_roles_by_method", None)
        if isinstance(roles_by_method, dict):
            allowed_roles = roles_by_method.get(request.method.upper())
        else:
            allowed_roles = getattr(view, "allowed_tenant_roles", None)

        if not allowed_roles:
            raise PermissionDenied(
                "Access denied: Role permissions are not configured for this endpoint."
            )

        if membership.role not in allowed_roles:
            raise PermissionDenied("Access denied: Insufficient role permissions within this tenant.")

        request.tenant = membership.tenant
        request.tenant_membership = membership
        request.tenant_subscription = subscription
        return True
