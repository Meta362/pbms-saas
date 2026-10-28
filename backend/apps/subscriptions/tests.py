from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.tenants.models import TenantStatus

User = get_user_model()


class SaaSSubscriptionAndSuperAdminGovernanceTests(TestCase):
    """
    Tests REQ-SAAS-01, REQ-SAAS-02, REQ-SAAS-03, and REQ-RBAC-01.
    """

    def setUp(self) -> None:
        self.client = APIClient()
        self.super_admin_pass = "SuperAdminPass#2026"
        self.super_admin = User.objects.create_superuser(
            email="admin@pbms-platform.com",
            password=self.super_admin_pass,
            full_name="Platform Operator",
        )

    def test_public_registration_idempotency_and_super_admin_reconciliation_flow(self) -> None:
        # 1. Frontend C: Fetch public plans
        plans_res = self.client.get("/api/v1/public/plans/")
        self.assertEqual(plans_res.status_code, 200)
        self.assertEqual(len(plans_res.json()), 3)

        # 2. Frontend C: Register new printing business tenant with idempotency key
        payload = {
            "full_name": "Chanthy Printing Owner",
            "email": "chanthy@phnompenhprint.com",
            "password": "ChanthyStrongPass#2026",
            "phone": "012345678",
            "business_name": "Phnom Penh Master Print",
            "business_slug": "pp-master-print",
            "plan_code": "growth",
            "billing_cycle": "MONTHLY",
            "payment_provider": "MANUAL_TRANSFER",
            "provider_reference": "ABA-TXN-998877",
            "idempotency_key": "idem-reg-pp-master-001",
        }
        reg_res = self.client.post("/api/v1/public/register-tenant/", payload, format="json")
        self.assertEqual(reg_res.status_code, 201)
        reg_data = reg_res.json()
        self.assertEqual(reg_data["tenant_status"], TenantStatus.PENDING_REVIEW)
        self.assertEqual(reg_data["amount_usd"], "59.00")
        payment_id = reg_data["payment_id"]
        tenant_id = reg_data["tenant_id"]

        # 3. Replay same registration request with same idempotency_key -> 200 OK without duplicate error
        replay_res = self.client.post("/api/v1/public/register-tenant/", payload, format="json")
        self.assertEqual(replay_res.status_code, 200)
        self.assertTrue(replay_res.json()["idempotent_replay"])
        self.assertEqual(replay_res.json()["payment_id"], payment_id)

        # 4. Tenant Owner logs in BEFORE Super Admin approval -> cannot access active tenant workspace yet
        owner_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": "chanthy@phnompenhprint.com", "password": "ChanthyStrongPass#2026"},
            format="json",
        ).json()
        owner_token = owner_login["access_token"]
        self.assertEqual(len(owner_login["user"]["memberships"]), 0)

        # 5. Negative RBAC Test: Tenant Owner tries to approve their own payment via Super Admin API -> 403 Forbidden
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {owner_token}")
        illegal_reconcile = self.client.post(
            f"/api/v1/super-admin/payments/{payment_id}/reconcile/",
            {"action": "APPROVE", "notes": "Self approval attempt"},
            format="json",
        )
        self.assertEqual(illegal_reconcile.status_code, 403)

        # 6. Super Admin logs in and reconciles payment -> activates Tenant & Subscription
        sa_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": "admin@pbms-platform.com", "password": self.super_admin_pass},
            format="json",
        ).json()
        sa_token = sa_login["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {sa_token}")

        reconcile_res = self.client.post(
            f"/api/v1/super-admin/payments/{payment_id}/reconcile/",
            {"action": "APPROVE", "notes": "Verified ABA KHQR receipt #ABA-TXN-998877"},
            format="json",
        )
        self.assertEqual(reconcile_res.status_code, 200)
        self.assertEqual(reconcile_res.json()["tenant_status"], TenantStatus.ACTIVE)
        self.assertEqual(reconcile_res.json()["subscription_status"], "ACTIVE")

        # 7. Super Admin overview reflects $59.00 revenue and 1 active tenant
        overview_res = self.client.get("/api/v1/super-admin/overview/")
        self.assertEqual(overview_res.status_code, 200)
        self.assertEqual(overview_res.json()["metrics"]["total_revenue_usd"], "59.00")
        self.assertEqual(overview_res.json()["metrics"]["active_tenants"], 1)

        # 8. Now Tenant Owner can access Frontend B Tenant Workspace context!
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
            HTTP_X_TENANT_ID=tenant_id,
        )
        ctx_res = self.client.get("/api/v1/tenant/context/")
        self.assertEqual(ctx_res.status_code, 200)
        self.assertEqual(ctx_res.json()["tenant_slug"], "pp-master-print")
