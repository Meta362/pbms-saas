from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from apps.accounts.models import PlatformRole
from apps.subscriptions.models import (
    BillingCycle,
    PaymentProvider,
    Plan,
    SubscriptionStatus,
    TenantSubscription,
)
from apps.subscriptions.views import ensure_default_plans
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus

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
        self.assertEqual(len(plans_res.json()), 4)

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

    def test_subscription_access_gate_and_super_admin_suspend_reactivate_sync(self) -> None:
        ensure_default_plans()
        starter = Plan.objects.get(code="starter")
        owner = User.objects.create_user(
            email="owner@gate-test.com",
            password="OwnerPass#2026",
            full_name="Gate Owner",
        )
        tenant = Tenant.objects.create(
            name="Gate Test Press",
            slug="gate-test-press",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4100.00"),
        )
        TenantMembership.objects.create(
            tenant=tenant,
            user=owner,
            role=TenantRole.TENANT_OWNER,
            is_active=True,
        )

        owner_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": "owner@gate-test.com", "password": "OwnerPass#2026"},
            format="json",
        ).json()
        owner_token = owner_login["access_token"]
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
            HTTP_X_TENANT_ID=str(tenant.id),
        )

        # 1. Missing TenantSubscription record -> 403 Forbidden (fail-closed)
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 403)

        # 2. Ineligible subscription statuses -> 403 Forbidden
        now = timezone.now()
        sub = TenantSubscription.objects.create(
            tenant=tenant,
            plan=starter,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.PENDING_PAYMENT,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        for bad_status in (
            SubscriptionStatus.PENDING_PAYMENT,
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.CANCELED,
        ):
            sub.status = bad_status
            sub.save(update_fields=["status", "updated_at"])
            self.assertEqual(
                self.client.get("/api/v1/tenant/context/").status_code,
                403,
            )

        # 3. Missing current_period_end (current_period_end=None) -> 403 Forbidden for ACTIVE & TRIALING
        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_end = None
        sub.save(update_fields=["status", "current_period_end", "updated_at"])
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 403)

        sub.status = SubscriptionStatus.TRIALING
        sub.current_period_end = None
        sub.save(update_fields=["status", "current_period_end", "updated_at"])
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 403)

        # 4. Expired current_period_end -> 403 Forbidden for ACTIVE & TRIALING
        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_end = now - timedelta(minutes=5)
        sub.save(update_fields=["status", "current_period_end", "updated_at"])
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 403)

        sub.status = SubscriptionStatus.TRIALING
        sub.current_period_end = now - timedelta(minutes=5)
        sub.save(update_fields=["status", "current_period_end", "updated_at"])
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 403)

        # 5. Future period end -> 200 OK for TRIALING & ACTIVE
        sub.status = SubscriptionStatus.TRIALING
        sub.current_period_end = now + timedelta(days=14)
        sub.save(update_fields=["status", "current_period_end", "updated_at"])
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 200)

        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_end = now + timedelta(days=30)
        sub.save(update_fields=["status", "current_period_end", "updated_at"])
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 200)

        # 5. Super Admin suspends tenant -> both Tenant.status and TenantSubscription.status become SUSPENDED
        sa_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": "admin@pbms-platform.com", "password": self.super_admin_pass},
            format="json",
        ).json()
        sa_token = sa_login["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {sa_token}")

        suspend_res = self.client.post(
            f"/api/v1/super-admin/tenants/{tenant.id}/status/",
            {"action": "SUSPEND", "reason": "Overdue invoice verification"},
            format="json",
        )
        self.assertEqual(suspend_res.status_code, 200)
        tenant.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(tenant.status, TenantStatus.SUSPENDED)
        self.assertEqual(sub.status, SubscriptionStatus.SUSPENDED)

        # Suspended tenant cannot access workspace -> 403 Forbidden
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
            HTTP_X_TENANT_ID=str(tenant.id),
        )
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 403)

        # 6. Super Admin reactivates tenant -> both Tenant.status and TenantSubscription.status become ACTIVE
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {sa_token}")
        activate_res = self.client.post(
            f"/api/v1/super-admin/tenants/{tenant.id}/status/",
            {"action": "ACTIVATE", "reason": "Payment settled"},
            format="json",
        )
        self.assertEqual(activate_res.status_code, 200)
        tenant.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(tenant.status, TenantStatus.ACTIVE)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {owner_token}",
            HTTP_X_TENANT_ID=str(tenant.id),
        )
        self.assertEqual(self.client.get("/api/v1/tenant/context/").status_code, 200)

    def test_super_admin_cannot_reactivate_expired_subscription_without_payment(self) -> None:
        ensure_default_plans()
        starter = Plan.objects.get(code="starter")
        now = timezone.now()
        expired_end = now - timedelta(days=5)

        tenant = Tenant.objects.create(
            name="Expired Subscription Press",
            slug="expired-subscription-press",
            status=TenantStatus.SUSPENDED,
            khr_exchange_rate=Decimal("4100.00"),
        )
        sub = TenantSubscription.objects.create(
            tenant=tenant,
            plan=starter,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.SUSPENDED,
            current_period_start=now - timedelta(days=35),
            current_period_end=expired_end,
        )

        login = self.client.post(
            "/api/v1/auth/login/",
            {
                "email": "admin@pbms-platform.com",
                "password": self.super_admin_pass,
            },
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login.json()['access_token']}"
        )

        response = self.client.post(
            f"/api/v1/super-admin/tenants/{tenant.id}/status/",
            {"action": "ACTIVATE", "reason": "Attempted activation without renewal"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        tenant.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(tenant.status, TenantStatus.SUSPENDED)
        self.assertEqual(sub.status, SubscriptionStatus.SUSPENDED)
        self.assertEqual(sub.current_period_end, expired_end)

    def test_super_admin_cannot_reactivate_canceled_subscription_directly(self) -> None:
        ensure_default_plans()
        starter = Plan.objects.get(code="starter")
        now = timezone.now()

        tenant = Tenant.objects.create(
            name="Canceled Subscription Press",
            slug="canceled-subscription-press",
            status=TenantStatus.SUSPENDED,
            khr_exchange_rate=Decimal("4100.00"),
        )
        sub = TenantSubscription.objects.create(
            tenant=tenant,
            plan=starter,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.CANCELED,
            current_period_start=now,
            current_period_end=now + timedelta(days=20),
        )

        login = self.client.post(
            "/api/v1/auth/login/",
            {
                "email": "admin@pbms-platform.com",
                "password": self.super_admin_pass,
            },
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login.json()['access_token']}"
        )

        response = self.client.post(
            f"/api/v1/super-admin/tenants/{tenant.id}/status/",
            {"action": "ACTIVATE", "reason": "Attempted direct canceled-plan activation"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        tenant.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(tenant.status, TenantStatus.SUSPENDED)
        self.assertEqual(sub.status, SubscriptionStatus.CANCELED)

    def test_platform_support_has_read_only_access_and_cannot_mutate(self) -> None:
        ensure_default_plans()
        support_user = User.objects.create_user(
            email="support@pbms-platform.com",
            password="SupportPass#2026",
            full_name="Platform Support Specialist",
            is_platform_staff=True,
            platform_role=PlatformRole.PLATFORM_SUPPORT,
        )
        tenant = Tenant.objects.create(
            name="Support View Press",
            slug="support-view-press",
            status=TenantStatus.ACTIVE,
        )

        support_login = self.client.post(
            "/api/v1/auth/login/",
            {"email": "support@pbms-platform.com", "password": "SupportPass#2026"},
            format="json",
        ).json()
        support_token = support_login["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {support_token}")

        # Allowed read-only endpoints -> 200 OK
        self.assertEqual(self.client.get("/api/v1/super-admin/overview/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/super-admin/tenants/").status_code, 200)

        # Denied mutation endpoints -> 403 Forbidden
        self.assertEqual(
            self.client.post(
                f"/api/v1/super-admin/tenants/{tenant.id}/status/",
                {"action": "SUSPEND", "reason": "Unauthorized support suspend"},
                format="json",
            ).status_code,
            403,
        )

    def test_super_admin_tenant_impersonation_support_mode(self) -> None:
        from apps.core.models import AuditEvent
        from apps.tenants.models import TenantMembership, TenantRole

        ensure_default_plans()
        plan = Plan.objects.get(code="starter")
        tenant = Tenant.objects.create(
            name="Angkor Support Client",
            slug="angkor-support-client",
            status=TenantStatus.ACTIVE,
        )
        TenantSubscription.objects.create(
            tenant=tenant,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            billing_cycle=BillingCycle.MONTHLY,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        shop_owner = User.objects.create_user(
            email="owner@angkorsupport.local",
            password="OwnerPassword123!",
            is_platform_staff=False,
        )
        TenantMembership.objects.create(
            tenant=tenant,
            user=shop_owner,
            role=TenantRole.TENANT_OWNER,
            is_active=True,
        )

        super_admin = User.objects.create_user(
            email="admin_impersonate@pbms.local",
            password="AdminPassword123!",
            is_platform_staff=True,
            platform_role=PlatformRole.SUPER_ADMIN,
        )
        sa_token = self.client.post(
            "/api/v1/auth/login/",
            {"email": "admin_impersonate@pbms.local", "password": "AdminPassword123!"},
            format="json",
        ).json()["access_token"]

        # 1. Deny non-superadmin
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {sa_token}")
        self.client.force_authenticate(user=shop_owner)
        denied_res = self.client.post(f"/api/v1/super-admin/tenants/{tenant.id}/impersonate/")
        self.assertEqual(denied_res.status_code, 403)

        # 2. SuperAdmin issues impersonation token
        self.client.force_authenticate(user=super_admin)
        imp_res = self.client.post(f"/api/v1/super-admin/tenants/{tenant.id}/impersonate/")
        self.assertEqual(imp_res.status_code, 200)
        imp_data = imp_res.json()
        self.assertTrue(imp_data["is_impersonation"])
        self.assertEqual(imp_data["tenant_id"], str(tenant.id))
        self.assertEqual(imp_data["target_user_email"], "owner@angkorsupport.local")
        self.assertEqual(imp_data["impersonator_email"], "admin_impersonate@pbms.local")
        self.assertIn("access_token", imp_data)

        # 3. Verify Audit Event logged
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="SUPERADMIN_TENANT_IMPERSONATED",
                tenant=tenant,
                actor_user=super_admin,
            ).exists()
        )

        # 4. Use impersonation token with X-Tenant-ID header to access workspace settings
        self.client.force_authenticate(user=None)
        imp_token = imp_data["access_token"]
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {imp_token}",
            HTTP_X_TENANT_ID=str(tenant.id),
        )
        settings_res = self.client.get("/api/v1/tenant/settings/")
        self.assertEqual(settings_res.status_code, 200)

    def test_super_admin_seed_tenant_master_presets(self) -> None:
        from apps.core.models import AuditEvent
        from apps.operations.models import Customer, Material

        tenant = Tenant.objects.create(
            name="New Print Hub",
            slug="new-print-hub",
            status=TenantStatus.ACTIVE,
        )
        super_admin = User.objects.create_user(
            email="admin_seeder@pbms.local",
            password="AdminPassword123!",
            is_platform_staff=True,
            platform_role=PlatformRole.SUPER_ADMIN,
        )
        self.client.force_authenticate(user=super_admin)

        seed_res = self.client.post(f"/api/v1/super-admin/tenants/{tenant.id}/seed-presets/")
        self.assertEqual(seed_res.status_code, 200)
        data = seed_res.json()
        self.assertEqual(data["tenant_id"], str(tenant.id))
        self.assertGreater(data["materials_seeded"], 0)
        self.assertEqual(data["customers_seeded"], 1)

        # Verify materials exist in database for this tenant
        self.assertTrue(Material.objects.filter(tenant=tenant, sku="MAT-AC-300").exists())
        self.assertTrue(Material.objects.filter(tenant=tenant, sku="MAT-PP-STICKER").exists())
        self.assertTrue(Customer.objects.filter(tenant=tenant, phone="012000000").exists())

        # Verify Audit Event logged
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="TENANT_MASTER_PRESETS_SEEDED",
                tenant=tenant,
                actor_user=super_admin,
            ).exists()
        )

    def test_super_admin_overview_business_analytics_metrics(self) -> None:
        super_admin = User.objects.create_user(
            email="admin_analytics@pbms.local",
            password="AdminPassword123!",
            is_platform_staff=True,
            platform_role=PlatformRole.SUPER_ADMIN,
        )
        self.client.force_authenticate(user=super_admin)
        res = self.client.get("/api/v1/super-admin/overview/")
        self.assertEqual(res.status_code, 200)
        metrics = res.json()["metrics"]
        self.assertIn("mrr_usd", metrics)
        self.assertIn("total_orders", metrics)
        self.assertIn("churn_risk_count", metrics)
        self.assertIn("active_announcements_count", metrics)

    def test_process_subscription_lifecycle_command_past_due_and_suspension(self) -> None:
        """SUB-001: Verifies management command transitions ACTIVE -> PAST_DUE and PAST_DUE -> SUSPENDED."""
        from django.core.management import call_command
        from io import StringIO
        from apps.core.models import AuditEvent

        ensure_default_plans()
        starter_plan = Plan.objects.get(code="starter")
        now = timezone.now()

        # Tenant 1: Active but expired 1 day ago
        tenant_1 = Tenant.objects.create(name="Expiring Shop", slug="expiring-shop", status=TenantStatus.ACTIVE)
        sub_1 = TenantSubscription.objects.create(
            tenant=tenant_1,
            plan=starter_plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now - timedelta(days=31),
            current_period_end=now - timedelta(days=1),
        )

        # Tenant 2: Already PAST_DUE and period ended 10 days ago (past 7-day grace)
        tenant_2 = Tenant.objects.create(name="Grace Expired Shop", slug="grace-expired-shop", status=TenantStatus.ACTIVE)
        sub_2 = TenantSubscription.objects.create(
            tenant=tenant_2,
            plan=starter_plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.PAST_DUE,
            current_period_start=now - timedelta(days=40),
            current_period_end=now - timedelta(days=10),
        )

        # 1. Test Dry Run: Database should not be modified
        out = StringIO()
        call_command("process_subscription_lifecycle", dry_run=True, stdout=out)
        self.assertIn("SIMULATION - DRY RUN", out.getvalue())

        sub_1.refresh_from_db()
        self.assertEqual(sub_1.status, SubscriptionStatus.ACTIVE)
        tenant_2.refresh_from_db()
        self.assertEqual(tenant_2.status, TenantStatus.ACTIVE)

        # 2. Test Live Run: Transitions should commit
        out = StringIO()
        call_command("process_subscription_lifecycle", grace_days=7, stdout=out)
        self.assertIn("COMMITTED", out.getvalue())

        sub_1.refresh_from_db()
        self.assertEqual(sub_1.status, SubscriptionStatus.PAST_DUE)

        sub_2.refresh_from_db()
        self.assertEqual(sub_2.status, SubscriptionStatus.SUSPENDED)
        tenant_2.refresh_from_db()
        self.assertEqual(tenant_2.status, TenantStatus.SUSPENDED)

        # Verify audit logs
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="SAAS_SUBSCRIPTION_PAST_DUE",
                tenant=tenant_1,
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="SAAS_TENANT_AUTO_SUSPENDED_GRACE_EXPIRED",
                tenant=tenant_2,
            ).exists()
        )

        # 3. Test Time-travel with --as-of
        tenant_3 = Tenant.objects.create(name="Future Shop", slug="future-shop", status=TenantStatus.ACTIVE)
        sub_3 = TenantSubscription.objects.create(
            tenant=tenant_3,
            plan=starter_plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=15),
        )

        # Evaluate as of 20 days into future
        future_date = (now + timedelta(days=20)).isoformat()
        call_command("process_subscription_lifecycle", as_of=future_date, stdout=StringIO())

        sub_3.refresh_from_db()
        self.assertEqual(sub_3.status, SubscriptionStatus.PAST_DUE)

        # 4. Subsequent run produces 0 transitions (idempotent, no repeated churn)
        subsequent_out = StringIO()
        call_command("process_subscription_lifecycle", grace_days=7, stdout=subsequent_out)
        self.assertIn("0 transitioned to PAST_DUE, 0 transitioned to SUSPENDED", subsequent_out.getvalue())

        # 5. Offboarded tenant protection: an OFFBOARDED tenant status is never rewritten to SUSPENDED
        tenant_offboarded = Tenant.objects.create(
            name="Offboarded Shop",
            slug="offboarded-shop",
            status=TenantStatus.OFFBOARDED,
        )
        TenantSubscription.objects.create(
            tenant=tenant_offboarded,
            plan=starter_plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.PAST_DUE,
            current_period_start=now - timedelta(days=60),
            current_period_end=now - timedelta(days=30),
        )
        call_command("process_subscription_lifecycle", grace_days=7, stdout=StringIO())
        tenant_offboarded.refresh_from_db()
        self.assertEqual(tenant_offboarded.status, TenantStatus.OFFBOARDED)


    def test_super_admin_reconcile_payment_reject_action(self) -> None:
        """SUB-002: Verifies SuperAdmin can reject manual bank transfer payments with audit logging."""
        from apps.subscriptions.models import PaymentStatus, SubscriptionPayment

        ensure_default_plans()
        starter_plan = Plan.objects.get(code="starter")
        tenant = Tenant.objects.create(name="Reject Test Shop", slug="reject-test-shop", status=TenantStatus.PENDING_REVIEW)
        sub = TenantSubscription.objects.create(
            tenant=tenant,
            plan=starter_plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.PENDING_PAYMENT,
        )
        payment = SubscriptionPayment.objects.create(
            tenant=tenant,
            subscription=sub,
            amount_usd=Decimal("29.00"),
            provider=PaymentProvider.MANUAL_TRANSFER,
            provider_reference="ABA-REJECT-001",
            idempotency_key="reject-test-key-001",
            status=PaymentStatus.PENDING,
        )

        self.client.force_authenticate(user=self.super_admin)

        res = self.client.post(
            f"/api/v1/super-admin/payments/{payment.id}/reconcile/",
            {"action": "REJECT", "notes": "Bank transfer reference not found in bank ledger."},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["payment_status"], PaymentStatus.REJECTED)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REJECTED)
        self.assertEqual(payment.notes, "Bank transfer reference not found in bank ledger.")

        # Tenant stays PENDING_REVIEW and subscription stays INCOMPLETE
        tenant.refresh_from_db()
        self.assertEqual(tenant.status, TenantStatus.PENDING_REVIEW)
