from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.models import AuditEvent
from apps.subscriptions.models import (
    BillingCycle,
    Plan,
    SubscriptionStatus,
    TenantSubscription,
)
from apps.subscriptions.views import ensure_default_plans
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus

User = get_user_model()


class TenantSettingsAPITests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        ensure_default_plans()
        plan = Plan.objects.get(code="starter")
        now = timezone.now()

        # Tenant A
        self.tenant_a = Tenant.objects.create(
            name="Angkor Print Studio",
            slug="angkor-print-settings",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4100.00"),
            tax_rate_percent=Decimal("10.00"),
        )
        TenantSubscription.objects.create(
            tenant=self.tenant_a,
            plan=plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
        )

        # Tenant A Staff
        self.owner_a = User.objects.create_user(
            email="owner_a@angkorprint.com",
            password="StrongPassword#2026",
            full_name="Owner A",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.owner_a,
            role=TenantRole.TENANT_OWNER,
        )

        self.manager_a = User.objects.create_user(
            email="manager_a@angkorprint.com",
            password="StrongPassword#2026",
            full_name="Manager A",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.manager_a,
            role=TenantRole.TENANT_MANAGER,
        )

        self.sales_a = User.objects.create_user(
            email="sales_a@angkorprint.com",
            password="StrongPassword#2026",
            full_name="Sales A",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.sales_a,
            role=TenantRole.SALES_STAFF,
        )

        # Tenant B
        self.tenant_b = Tenant.objects.create(
            name="Battambang Graphics",
            slug="battambang-settings",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4050.00"),
            tax_rate_percent=Decimal("5.00"),
        )
        TenantSubscription.objects.create(
            tenant=self.tenant_b,
            plan=plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
        )

        self.owner_b = User.objects.create_user(
            email="owner_b@battambang.com",
            password="StrongPassword#2026",
            full_name="Owner B",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b,
            user=self.owner_b,
            role=TenantRole.TENANT_OWNER,
        )

    def _auth(self, user: User, tenant: Tenant) -> None:
        self.client.force_authenticate(user=user)
        self.client.credentials(HTTP_X_TENANT_ID=str(tenant.id))

    def test_tenant_owner_can_read_settings(self) -> None:
        self._auth(self.owner_a, self.tenant_a)
        res = self.client.get("/api/v1/tenant/settings/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["name"], "Angkor Print Studio")
        self.assertEqual(data["slug"], "angkor-print-settings")
        self.assertEqual(data["base_currency"], "USD")
        self.assertEqual(data["khr_exchange_rate"], "4100.00")
        self.assertEqual(data["tax_rate_percent"], "10.00")

    def test_non_owner_staff_can_read_settings(self) -> None:
        # Tenant Manager can read
        self._auth(self.manager_a, self.tenant_a)
        res_mgr = self.client.get("/api/v1/tenant/settings/")
        self.assertEqual(res_mgr.status_code, status.HTTP_200_OK)
        self.assertEqual(res_mgr.json()["khr_exchange_rate"], "4100.00")

        # Sales Staff can read
        self._auth(self.sales_a, self.tenant_a)
        res_sales = self.client.get("/api/v1/tenant/settings/")
        self.assertEqual(res_sales.status_code, status.HTTP_200_OK)

    def test_tenant_owner_can_update_settings_and_generates_audit_event(self) -> None:
        self._auth(self.owner_a, self.tenant_a)
        initial_events_count = AuditEvent.objects.filter(
            tenant=self.tenant_a, event_type="TENANT_SETTINGS_UPDATED"
        ).count()

        payload = {
            "khr_exchange_rate": "4125.00",
            "tax_rate_percent": "7.50",
        }
        res = self.client.patch("/api/v1/tenant/settings/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["khr_exchange_rate"], "4125.00")
        self.assertEqual(data["tax_rate_percent"], "7.50")

        # Verify database mutation
        self.tenant_a.refresh_from_db()
        self.assertEqual(self.tenant_a.khr_exchange_rate, Decimal("4125.00"))
        self.assertEqual(self.tenant_a.tax_rate_percent, Decimal("7.50"))

        # Verify AuditEvent creation
        events = AuditEvent.objects.filter(
            tenant=self.tenant_a, event_type="TENANT_SETTINGS_UPDATED"
        )
        self.assertEqual(events.count(), initial_events_count + 1)
        latest_event = events.latest("created_at")
        self.assertEqual(latest_event.actor_user, self.owner_a)
        self.assertEqual(latest_event.target_model, "tenants.Tenant")
        self.assertEqual(latest_event.target_id, str(self.tenant_a.id))
        self.assertEqual(
            latest_event.metadata["before"],
            {"khr_exchange_rate": "4100.00", "tax_rate_percent": "10.00"},
        )
        self.assertEqual(
            latest_event.metadata["after"],
            {"khr_exchange_rate": "4125.00", "tax_rate_percent": "7.50"},
        )
        self.assertEqual(
            set(latest_event.metadata["updated_fields"]),
            {"khr_exchange_rate", "tax_rate_percent"},
        )

    def test_unauthenticated_request_is_rejected(self) -> None:
        self.client.force_authenticate(user=None)
        res = self.client.get("/api/v1/tenant/settings/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res_patch = self.client.patch(
            "/api/v1/tenant/settings/",
            {"khr_exchange_rate": "4150.00"},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_owner_cannot_update_settings(self) -> None:
        initial_events_count = AuditEvent.objects.filter(
            event_type="TENANT_SETTINGS_UPDATED"
        ).count()

        # Manager cannot patch settings
        self._auth(self.manager_a, self.tenant_a)
        res_mgr = self.client.patch(
            "/api/v1/tenant/settings/",
            {"khr_exchange_rate": "4150.00"},
            format="json",
        )
        self.assertEqual(res_mgr.status_code, status.HTTP_403_FORBIDDEN)

        # Sales staff cannot patch settings
        self._auth(self.sales_a, self.tenant_a)
        res_sales = self.client.patch(
            "/api/v1/tenant/settings/",
            {"tax_rate_percent": "5.00"},
            format="json",
        )
        self.assertEqual(res_sales.status_code, status.HTTP_403_FORBIDDEN)

        # Confirm no database changes and no AuditEvent
        self.tenant_a.refresh_from_db()
        self.assertEqual(self.tenant_a.khr_exchange_rate, Decimal("4100.00"))
        self.assertEqual(self.tenant_a.tax_rate_percent, Decimal("10.00"))
        self.assertEqual(
            AuditEvent.objects.filter(event_type="TENANT_SETTINGS_UPDATED").count(),
            initial_events_count,
        )

    def test_cross_tenant_access_denied(self) -> None:
        # Owner B tries to access Tenant A by supplying Tenant A header
        self.client.force_authenticate(user=self.owner_b)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant_a.id))

        res_get = self.client.get("/api/v1/tenant/settings/")
        self.assertEqual(res_get.status_code, status.HTTP_403_FORBIDDEN)

        res_patch = self.client.patch(
            "/api/v1/tenant/settings/",
            {"khr_exchange_rate": "5000.00"},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)

        # Confirm Tenant A untouched
        self.tenant_a.refresh_from_db()
        self.assertEqual(self.tenant_a.khr_exchange_rate, Decimal("4100.00"))

    def test_invalid_exchange_rate_rejected(self) -> None:
        self._auth(self.owner_a, self.tenant_a)

        for invalid_rate in ["0.00", "-4100.00", "not_a_number"]:
            res = self.client.patch(
                "/api/v1/tenant/settings/",
                {"khr_exchange_rate": invalid_rate},
                format="json",
            )
            self.assertEqual(
                res.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Expected 400 for rate {invalid_rate}",
            )
            self.assertIn("khr_exchange_rate", res.json())

        # Confirm no change in DB
        self.tenant_a.refresh_from_db()
        self.assertEqual(self.tenant_a.khr_exchange_rate, Decimal("4100.00"))

    def test_invalid_tax_rate_rejected(self) -> None:
        self._auth(self.owner_a, self.tenant_a)

        for invalid_tax in ["-0.01", "100.01", "150.00", "invalid"]:
            res = self.client.patch(
                "/api/v1/tenant/settings/",
                {"tax_rate_percent": invalid_tax},
                format="json",
            )
            self.assertEqual(
                res.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Expected 400 for tax {invalid_tax}",
            )
            self.assertIn("tax_rate_percent", res.json())

        # Confirm no change in DB
        self.tenant_a.refresh_from_db()
        self.assertEqual(self.tenant_a.tax_rate_percent, Decimal("10.00"))

    def test_partial_update_preserves_unspecified_setting(self) -> None:
        self._auth(self.owner_a, self.tenant_a)

        # 1. Update only tax_rate_percent
        res1 = self.client.patch(
            "/api/v1/tenant/settings/",
            {"tax_rate_percent": "8.00"},
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        data1 = res1.json()
        self.assertEqual(data1["tax_rate_percent"], "8.00")
        self.assertEqual(data1["khr_exchange_rate"], "4100.00")  # untouched

        # 2. Update only khr_exchange_rate
        res2 = self.client.patch(
            "/api/v1/tenant/settings/",
            {"khr_exchange_rate": "4150.00"},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        data2 = res2.json()
        self.assertEqual(data2["tax_rate_percent"], "8.00")  # untouched
        self.assertEqual(data2["khr_exchange_rate"], "4150.00")

    def test_empty_patch_rejected(self) -> None:
        self._auth(self.owner_a, self.tenant_a)
        res = self.client.patch("/api/v1/tenant/settings/", {}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_only_fields_cannot_be_mutated(self) -> None:
        self._auth(self.owner_a, self.tenant_a)
        res = self.client.patch(
            "/api/v1/tenant/settings/",
            {
                "id": "00000000-0000-0000-0000-000000000000",
                "name": "Hacked Tenant Name",
                "slug": "hacked-slug",
                "base_currency": "EUR",
                "khr_exchange_rate": "4200.00",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.tenant_a.refresh_from_db()
        self.assertEqual(self.tenant_a.name, "Angkor Print Studio")
        self.assertEqual(self.tenant_a.slug, "angkor-print-settings")
        self.assertEqual(self.tenant_a.base_currency, "USD")
        self.assertEqual(self.tenant_a.khr_exchange_rate, Decimal("4200.00"))

