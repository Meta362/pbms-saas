from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.views import APIView
from apps.accounts.models import AuthSession
from apps.core.models import AuditEvent
from apps.subscriptions.models import (
    BillingCycle,
    Plan,
    SubscriptionStatus,
    TenantSubscription,
)
from apps.subscriptions.views import ensure_default_plans
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus
from apps.tenants.permissions import HasActiveTenantMembership

User = get_user_model()


class _UnconfiguredRoleTenantView(APIView):
    """Test view intentionally omitting allowed_tenant_roles to verify fail-closed behavior."""

    permission_classes = [IsAuthenticated, HasActiveTenantMembership]

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


class AuthenticationAndTenantIsolationSecurityTests(TestCase):
    """
    Tests REQ-AUTH-01..04, REQ-RBAC-01..03, and Staff Membership CRUD & Entitlements.
    """

    def setUp(self) -> None:
        self.client = APIClient()
        ensure_default_plans()
        self.starter_plan = Plan.objects.get(code="starter")
        self.password = "SecurePrintingPass#2026"
        self.user_a = User.objects.create_user(
            email="sokha@shop-a.com",
            password=self.password,
            full_name="Sokha Shop A",
        )
        self.user_b = User.objects.create_user(
            email="dara@shop-b.com",
            password=self.password,
            full_name="Dara Shop B",
        )

        self.tenant_a = Tenant.objects.create(
            name="Shop A Printing",
            slug="shop-a",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4100.00"),
        )
        self.tenant_b = Tenant.objects.create(
            name="Shop B Printing",
            slug="shop-b",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4050.00"),
        )

        now = timezone.now()
        self.sub_a = TenantSubscription.objects.create(
            tenant=self.tenant_a,
            plan=self.starter_plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        self.sub_b = TenantSubscription.objects.create(
            tenant=self.tenant_b,
            plan=self.starter_plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )

        self.membership_a = TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            role=TenantRole.TENANT_OWNER,
        )
        self.membership_b = TenantMembership.objects.create(
            tenant=self.tenant_b,
            user=self.user_b,
            role=TenantRole.TENANT_OWNER,
        )

    def test_login_issues_tokens_and_returns_tenant_memberships(self) -> None:
        res = self.client.post(
            "/api/v1/auth/login/",
            {"email": "sokha@shop-a.com", "password": self.password},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertEqual(len(data["user"]["memberships"]), 1)
        self.assertEqual(data["user"]["memberships"][0]["tenant_slug"], "shop-a")

    def test_refresh_token_rotation_and_reuse_detection_revokes_session(self) -> None:
        login_res = self.client.post(
            "/api/v1/auth/login/",
            {"email": "sokha@shop-a.com", "password": self.password},
            format="json",
        ).json()
        refresh_1 = login_res["refresh_token"]
        session_id = login_res["session_id"]

        # 1. Valid rotation with refresh_1 -> issues refresh_2 and access_2
        rot_res = self.client.post(
            "/api/v1/auth/refresh/",
            {"refresh_token": refresh_1},
            format="json",
        )
        self.assertEqual(rot_res.status_code, 200)
        access_2 = rot_res.json()["access_token"]

        # 2. Attacker or client replays already-rotated refresh_1 -> MUST detect reuse and revoke session!
        reuse_res = self.client.post(
            "/api/v1/auth/refresh/",
            {"refresh_token": refresh_1},
            format="json",
        )
        self.assertEqual(reuse_res.status_code, 401)

        # Verify session is marked revoked in PostgreSQL and audit event recorded
        session = AuthSession.objects.get(id=session_id)
        self.assertTrue(session.is_revoked)
        self.assertEqual(session.revoked_reason, "REFRESH_TOKEN_REUSE_DETECTED")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="AUTH_REFRESH_REUSE_DETECTED",
                target_id=session_id,
            ).exists()
        )

        # 3. Even access_2 from that compromised session family must now be rejected immediately
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_2}")
        me_res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_res.status_code, 401)

    def test_logout_immediately_revokes_session_in_postgres(self) -> None:
        login_res = self.client.post(
            "/api/v1/auth/login/",
            {"email": "sokha@shop-a.com", "password": self.password},
            format="json",
        ).json()
        access = login_res["access_token"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout_res = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(logout_res.status_code, 200)

        # Subsequent API call with the same unexpired access JWT must fail with 401
        me_res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_res.status_code, 401)

    def test_cross_tenant_idor_access_is_strictly_blocked(self) -> None:
        login_res = self.client.post(
            "/api/v1/auth/login/",
            {"email": "sokha@shop-a.com", "password": self.password},
            format="json",
        ).json()
        access_a = login_res["access_token"]

        # User A accesses their own Tenant A -> 200 OK
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {access_a}",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )
        own_res = self.client.get("/api/v1/tenant/context/")
        self.assertEqual(own_res.status_code, 200)
        self.assertEqual(own_res.json()["tenant_slug"], "shop-a")

        # User A attempts to access Tenant B by spoofing X-Tenant-ID -> 403 Forbidden
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {access_a}",
            HTTP_X_TENANT_ID=str(self.tenant_b.id),
        )
        cross_res = self.client.get("/api/v1/tenant/context/")
        self.assertEqual(cross_res.status_code, 403)

    def test_missing_role_configuration_fails_closed(self) -> None:
        factory = APIRequestFactory()
        request = factory.get(
            "/api/v1/tenant/unconfigured/",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )
        force_authenticate(request, user=self.user_a)
        view = _UnconfiguredRoleTenantView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_staff_membership_crud_role_enforcement_audit_and_entitlements(self) -> None:
        login_a = self.client.post(
            "/api/v1/auth/login/",
            {"email": "sokha@shop-a.com", "password": self.password},
            format="json",
        ).json()
        owner_token = login_a["access_token"]
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )

        # 1. Owner lists memberships -> sees only Tenant A's membership, without sensitive fields
        list_res = self.client.get("/api/v1/tenant/memberships/")
        self.assertEqual(list_res.status_code, 200)
        items = list_res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["email"], "sokha@shop-a.com")
        self.assertNotIn("password", items[0])
        self.assertNotIn("current_refresh_jti_hash", items[0])

        # 2. Attempt to inject platform_role via membership creation -> 400 Bad Request
        priv_res = self.client.post(
            "/api/v1/tenant/memberships/",
            {
                "email": "attacker@shop-a.com",
                "full_name": "Attacker",
                "password": "StrongStaffPass#2026",
                "role": TenantRole.SALES_STAFF,
                "platform_role": "SUPER_ADMIN",
            },
            format="json",
        )
        self.assertEqual(priv_res.status_code, 400)

        # 3. Owner creates a SALES_STAFF member -> 201 Created + AuditEvent
        create_res = self.client.post(
            "/api/v1/tenant/memberships/",
            {
                "email": "sales1@shop-a.com",
                "full_name": "Bopha Sales",
                "phone": "012111222",
                "password": "StrongStaffPass#2026",
                "role": TenantRole.SALES_STAFF,
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, 201)
        staff_data = create_res.json()
        staff_membership_id = staff_data["id"]
        self.assertEqual(staff_data["role"], TenantRole.SALES_STAFF)
        self.assertTrue(staff_data["is_active"])
        self.assertNotIn("password", staff_data)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant_a,
                event_type="TENANT_MEMBERSHIP_CREATED",
                target_id=staff_membership_id,
            ).exists()
        )

        # 4. Duplicate membership creation in the same tenant -> 400 Bad Request
        dup_res = self.client.post(
            "/api/v1/tenant/memberships/",
            {
                "email": "sales1@shop-a.com",
                "role": TenantRole.FINANCE_STAFF,
            },
            format="json",
        )
        self.assertEqual(dup_res.status_code, 400)

        # 5. Non-admin role (SALES_STAFF) cannot list, create, or update memberships -> 403 Forbidden
        staff_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": "sales1@shop-a.com", "password": "StrongStaffPass#2026"},
            format="json",
        ).json()
        staff_token = staff_login["access_token"]
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {staff_token}",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )
        self.assertEqual(self.client.get("/api/v1/tenant/memberships/").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/memberships/",
                {
                    "email": "unauthorized@shop-a.com",
                    "full_name": "Unauthorized",
                    "password": "StrongStaffPass#2026",
                    "role": TenantRole.DESIGNER,
                },
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/v1/tenant/memberships/{staff_membership_id}/",
                {"role": TenantRole.TENANT_OWNER},
                format="json",
            ).status_code,
            403,
        )
        # Non-admin also cannot read tenant audit logs -> 403 Forbidden
        self.assertEqual(self.client.get("/api/v1/tenant/audit-events/").status_code, 403)

        # 6. Switch back to Owner: update staff role to FINANCE_STAFF -> 200 OK + AuditEvent
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )
        patch_role_res = self.client.patch(
            f"/api/v1/tenant/memberships/{staff_membership_id}/",
            {"role": TenantRole.FINANCE_STAFF},
            format="json",
        )
        self.assertEqual(patch_role_res.status_code, 200)
        self.assertEqual(patch_role_res.json()["role"], TenantRole.FINANCE_STAFF)
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant_a,
                event_type="TENANT_MEMBERSHIP_ROLE_CHANGED",
                target_id=staff_membership_id,
            ).exists()
        )

        # Verify updated role is immediately effective on subsequent requests
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {staff_token}",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )
        ctx_res = self.client.get("/api/v1/tenant/context/")
        self.assertEqual(ctx_res.status_code, 200)
        self.assertEqual(ctx_res.json()["role"], TenantRole.FINANCE_STAFF)

        # 7. Owner deactivates staff membership -> 200 OK + AuditEvent, and staff is immediately denied access
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )
        deact_res = self.client.patch(
            f"/api/v1/tenant/memberships/{staff_membership_id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(deact_res.status_code, 200)
        self.assertFalse(deact_res.json()["is_active"])
        self.assertTrue(
            AuditEvent.objects.filter(
                tenant=self.tenant_a,
                event_type="TENANT_MEMBERSHIP_DEACTIVATED",
                target_id=staff_membership_id,
            ).exists()
        )

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {staff_token}",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 403)

        # 8. Last active TENANT_OWNER cannot be deactivated or demoted -> 400 Bad Request
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )
        self.assertEqual(
            self.client.patch(
                f"/api/v1/tenant/memberships/{self.membership_a.id}/",
                {"is_active": False},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/v1/tenant/memberships/{self.membership_a.id}/",
                {"role": TenantRole.TENANT_MANAGER},
                format="json",
            ).status_code,
            400,
        )

        # 9. Cross-tenant membership modification is blocked -> 404 Not Found
        self.assertEqual(
            self.client.patch(
                f"/api/v1/tenant/memberships/{self.membership_b.id}/",
                {"is_active": False},
                format="json",
            ).status_code,
            404,
        )

        # 10. Plan max_staff_users limit enforcement (set max_staff_users=2 on starter plan)
        self.starter_plan.max_staff_users = 2
        self.starter_plan.save(update_fields=["max_staff_users", "updated_at"])

        # Currently 1 active member (owner). Reactivating sales1 brings active count to 2 -> 200 OK
        react_res = self.client.patch(
            f"/api/v1/tenant/memberships/{staff_membership_id}/",
            {"is_active": True},
            format="json",
        )
        self.assertEqual(react_res.status_code, 200)

        # Creating a 3rd active member exceeds max_staff_users=2 -> 400 Bad Request
        over_limit_res = self.client.post(
            "/api/v1/tenant/memberships/",
            {
                "email": "staff3@shop-a.com",
                "full_name": "Third Staff",
                "password": "StrongStaffPass#2026",
                "role": TenantRole.DESIGNER,
            },
            format="json",
        )
        self.assertEqual(over_limit_res.status_code, 400)

        # 11. Owner can read tenant-scoped audit events
        audit_res = self.client.get("/api/v1/tenant/audit-events/")
        self.assertEqual(audit_res.status_code, 200)
        self.assertGreaterEqual(len(audit_res.json()), 3)
