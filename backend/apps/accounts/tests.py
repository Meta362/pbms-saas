from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import AuthSession
from apps.core.models import AuditEvent
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus

User = get_user_model()


class AuthenticationAndTenantIsolationSecurityTests(TestCase):
    """
    Tests REQ-AUTH-01, REQ-AUTH-02, REQ-AUTH-03, REQ-AUTH-04, REQ-RBAC-02, REQ-RBAC-03.
    """

    def setUp(self) -> None:
        self.client = APIClient()
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

        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            role=TenantRole.TENANT_OWNER,
        )
        TenantMembership.objects.create(
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
