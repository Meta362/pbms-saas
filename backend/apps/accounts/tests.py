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
from apps.accounts.models import AuthSession, PasswordResetToken
from apps.core.models import AuditEvent
from apps.subscriptions.models import (
    BillingCycle,
    Plan,
    SubscriptionStatus,
    TenantSubscription,
)
from apps.subscriptions.views import ensure_default_plans
from apps.tenants.models import StaffInvitation, Tenant, TenantMembership, TenantRole, TenantStatus
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

    def test_logout_all_revokes_all_active_sessions_and_blocks_tokens(self) -> None:
        # 1. User logs in on Client 1
        res1 = self.client.post(
            "/api/v1/auth/login/",
            {"email": "sokha@shop-a.com", "password": self.password},
            format="json",
        ).json()
        token1 = res1["access_token"]

        # 2. User logs in on Client 2
        res2 = self.client.post(
            "/api/v1/auth/login/",
            {"email": "sokha@shop-a.com", "password": self.password},
            format="json",
        ).json()
        token2 = res2["access_token"]

        # Assert two active sessions exist for User A
        self.assertEqual(AuthSession.objects.filter(user=self.user_a, is_revoked=False).count(), 2)

        # 3. Client 2 executes logout-all
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token2}")
        logout_all_res = self.client.post("/api/v1/auth/logout-all/")
        self.assertEqual(logout_all_res.status_code, 200)
        self.assertEqual(logout_all_res.json()["status"], "revoked_all")
        self.assertEqual(logout_all_res.json()["sessions_revoked"], 2)

        # 4. Assert all sessions in DB are revoked
        self.assertEqual(AuthSession.objects.filter(user=self.user_a, is_revoked=False).count(), 0)

        # 5. Neither token can authenticate anymore
        c1 = APIClient()
        c1.credentials(HTTP_AUTHORIZATION=f"Bearer {token1}")
        self.assertEqual(c1.get("/api/v1/auth/me/").status_code, 401)

        c2 = APIClient()
        c2.credentials(HTTP_AUTHORIZATION=f"Bearer {token2}")
        self.assertEqual(c2.get("/api/v1/auth/me/").status_code, 401)

        # 6. Audit event was generated
        self.assertTrue(
            AuditEvent.objects.filter(actor_user=self.user_a, event_type="AUTH_LOGOUT_ALL").exists()
        )

    def test_login_throttling_enforces_rate_limit(self) -> None:
        from unittest.mock import patch
        from django.core.cache import cache
        from rest_framework.throttling import ScopedRateThrottle
        cache.clear()

        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"auth_login": "5/minute"}):
            # Make requests up to rate limit (5)
            for _ in range(5):
                res = self.client.post(
                    "/api/v1/auth/login/",
                    {"email": "sokha@shop-a.com", "password": "wrong-password"},
                    format="json",
                )
                self.assertEqual(res.status_code, 401)

            # 6th attempt should be throttled
            throttled_res = self.client.post(
                "/api/v1/auth/login/",
                {"email": "sokha@shop-a.com", "password": "wrong-password"},
                format="json",
            )
            self.assertEqual(throttled_res.status_code, 429)
        cache.clear()

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

    def test_user_profile_me_get_and_patch(self) -> None:
        """AUTH-001: Verifies GET /auth/me/ includes phone and PATCH updates profile safely."""
        self.user_a.phone = "012345678"
        self.user_a.save(update_fields=["phone", "updated_at"])

        self.client.force_authenticate(user=self.user_a)

        # 1. GET /api/v1/auth/me/ returns phone
        get_res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["phone"], "012345678")
        self.assertEqual(get_res.json()["full_name"], "Sokha Shop A")

        # 2. PATCH /api/v1/auth/me/ updates full_name and phone
        patch_res = self.client.patch(
            "/api/v1/auth/me/",
            {
                "full_name": "Sokha Shop A (Updated)",
                "phone": "098765432",
                "preferred_language": "en",
            },
            format="json",
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()["full_name"], "Sokha Shop A (Updated)")
        self.assertEqual(patch_res.json()["phone"], "098765432")
        self.assertEqual(patch_res.json()["preferred_language"], "en")

        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.full_name, "Sokha Shop A (Updated)")
        self.assertEqual(self.user_a.phone, "098765432")
        self.assertEqual(self.user_a.preferred_language, "en")

        # 3. Privilege escalation injection rejected
        priv_res = self.client.patch(
            "/api/v1/auth/me/",
            {"platform_role": "SUPER_ADMIN", "is_staff": True},
            format="json",
        )
        self.assertEqual(priv_res.status_code, 400)

        # 4. Empty PATCH rejected
        empty_res = self.client.patch("/api/v1/auth/me/", {}, format="json")
        self.assertEqual(empty_res.status_code, 400)

    def test_password_reset_flow_and_session_revocation(self) -> None:
        """AUTH-002: Verifies password reset request, confirmation, and session mass-revocation."""
        # 1. User logs in and gets an active session
        login_res = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.user_a.email, "password": self.password},
            format="json",
        )
        self.assertEqual(login_res.status_code, 200)
        self.assertTrue(AuthSession.objects.filter(user=self.user_a, is_revoked=False).exists())

        # 2. Request password reset
        reset_req_res = self.client.post(
            "/api/v1/auth/password-reset/",
            {"email": self.user_a.email},
            format="json",
        )
        self.assertEqual(reset_req_res.status_code, 200)
        raw_token = reset_req_res.json().get("reset_token")
        self.assertTrue(raw_token)
        self.assertTrue(PasswordResetToken.objects.filter(user=self.user_a, is_used=False).exists())

        # 3. Requesting reset for non-existent user returns generic message
        non_user_res = self.client.post(
            "/api/v1/auth/password-reset/",
            {"email": "nobody@unknown.com"},
            format="json",
        )
        self.assertEqual(non_user_res.status_code, 200)
        self.assertNotIn("reset_token", non_user_res.json())

        # 4. Confirm password reset with new password
        new_password = "NewStrongPassword#2026"
        confirm_res = self.client.post(
            "/api/v1/auth/password-reset-confirm/",
            {"token": raw_token, "new_password": new_password},
            format="json",
        )
        self.assertEqual(confirm_res.status_code, 200)
        self.assertEqual(confirm_res.json()["sessions_revoked"], 1)

        # 5. Check sessions are revoked
        active_sessions = AuthSession.objects.filter(user=self.user_a, is_revoked=False)
        self.assertEqual(active_sessions.count(), 0)

        # 6. Check login with old password fails
        old_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.user_a.email, "password": self.password},
            format="json",
        )
        self.assertEqual(old_login.status_code, 401)

        # 7. Check login with new password succeeds
        new_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.user_a.email, "password": new_password},
            format="json",
        )
        self.assertEqual(new_login.status_code, 200)

        # 8. Re-using the same reset token fails
        reuse_res = self.client.post(
            "/api/v1/auth/password-reset-confirm/",
            {"token": raw_token, "new_password": "AnotherPassword#2026"},
            format="json",
        )
        self.assertEqual(reuse_res.status_code, 400)

    def test_staff_invitation_lifecycle(self) -> None:
        """AUTH-003: Verifies tenant staff invitation lifecycle (invite, list, revoke, accept)."""
        self.client.force_authenticate(user=self.user_a)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant_a.id))

        # 1. Tenant Owner invites a new staff member
        invite_res = self.client.post(
            "/api/v1/tenant/invitations/",
            {"email": "operator@printshop.local", "role": TenantRole.PRODUCTION_STAFF},
            format="json",
        )
        self.assertEqual(invite_res.status_code, 201)
        raw_token = invite_res.json()["invitation_token"]
        invite_id = invite_res.json()["id"]

        # 2. List invitations
        list_res = self.client.get("/api/v1/tenant/invitations/")
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(len(list_res.json()), 1)
        self.assertEqual(list_res.json()[0]["email"], "operator@printshop.local")

        # 3. Test revoking invitation
        revoke_res = self.client.post(f"/api/v1/tenant/invitations/{invite_id}/revoke/")
        self.assertEqual(revoke_res.status_code, 200)

        # 4. Attempting to accept a revoked invitation fails
        accept_revoked_res = self.client.post(
            "/api/v1/auth/accept-invitation/",
            {
                "token": raw_token,
                "password": "SecureStaffPass#2026",
                "full_name": "Print Operator",
            },
            format="json",
        )
        self.assertEqual(accept_revoked_res.status_code, 400)

        # 5. Issue fresh invitation and accept it
        fresh_invite = self.client.post(
            "/api/v1/tenant/invitations/",
            {"email": "operator2@printshop.local", "role": TenantRole.INVENTORY_STAFF},
            format="json",
        )
        self.assertEqual(fresh_invite.status_code, 201)
        fresh_token = fresh_invite.json()["invitation_token"]

        # Accept fresh invitation
        self.client.credentials()  # clear auth
        accept_res = self.client.post(
            "/api/v1/auth/accept-invitation/",
            {
                "token": fresh_token,
                "password": "SecureStaffPass#2026",
                "full_name": "Inventory Operator",
                "phone": "012888999",
            },
            format="json",
        )
        self.assertEqual(accept_res.status_code, 200)
        self.assertIn("tokens", accept_res.json())
        self.assertEqual(accept_res.json()["user"]["email"], "operator2@printshop.local")

        # Check membership created
        new_membership = TenantMembership.objects.filter(
            tenant=self.tenant_a,
            user__email="operator2@printshop.local",
        ).first()
        self.assertIsNotNone(new_membership)
        self.assertEqual(new_membership.role, TenantRole.INVENTORY_STAFF)
        self.assertTrue(new_membership.is_active)

    def test_inactive_user_login_rejected(self) -> None:
        """SEC-GAP-01: Verifies that deactivating a user prevents login."""
        self.user_b.is_active = False
        self.user_b.save(update_fields=["is_active", "updated_at"])

        res = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.user_b.email, "password": self.password},
            format="json",
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email or password.")
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="AUTH_LOGIN_FAILED",
                metadata__attempted_email=self.user_b.email,
            ).exists()
        )
