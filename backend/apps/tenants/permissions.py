from uuid import UUID
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView
from apps.accounts.models import PlatformRole
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
            TenantMembership.objects.select_related("tenant")
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

        allowed_roles = getattr(view, "allowed_tenant_roles", None)
        if allowed_roles is not None and membership.role not in allowed_roles:
            raise PermissionDenied("Access denied: Insufficient role permissions within this tenant.")

        request.tenant = membership.tenant
        request.tenant_membership = membership
        return True
