import threading
import unittest
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITransactionTestCase

from apps.operations.models import Customer, Quotation
from apps.subscriptions.models import (
    BillingCycle,
    Plan,
    SubscriptionStatus,
    TenantSubscription,
)
from apps.subscriptions.views import ensure_default_plans
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus

User = get_user_model()


@unittest.skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL required for row-level locking concurrency verification",
)
class PostgresQuotationConcurrencyTestCase(APITransactionTestCase):
    """
    Verification suite for FIN-01: Row-level tenant locking under genuine concurrent requests
    using PostgreSQL transactions and connections.
    """

    def setUp(self) -> None:
        ensure_default_plans()
        plan = Plan.objects.get(code="starter")
        now = timezone.now()

        # Setup Tenant A
        self.tenant_a = Tenant.objects.create(
            name="Angkor Print Studio",
            slug="angkor-print-concurrency",
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
        self.user_a = User.objects.create_user(
            email="owner_a_concurrency@angkorprint.com",
            password="StrongPassword#2026",
            full_name="Owner A Concurrency",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            role=TenantRole.TENANT_OWNER,
        )
        self.customer_a = Customer.objects.create(
            tenant=self.tenant_a,
            name="Angkor Retail Client",
            email="retail_a@angkorclient.com",
            phone="012999888",
        )

        login_client_a = APIClient()
        res_a = login_client_a.post(
            "/api/v1/auth/login/",
            {"email": "owner_a_concurrency@angkorprint.com", "password": "StrongPassword#2026"},
            format="json",
        )
        self.assertEqual(res_a.status_code, status.HTTP_200_OK)
        self.token_a = res_a.json()["access_token"]

        # Setup Tenant B
        self.tenant_b = Tenant.objects.create(
            name="Battambang Signs & Graphics",
            slug="battambang-concurrency",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4100.00"),
            tax_rate_percent=Decimal("10.00"),
        )
        TenantSubscription.objects.create(
            tenant=self.tenant_b,
            plan=plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
        )
        self.user_b = User.objects.create_user(
            email="owner_b_concurrency@battambangsigns.com",
            password="StrongPassword#2026",
            full_name="Owner B Concurrency",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b,
            user=self.user_b,
            role=TenantRole.TENANT_OWNER,
        )
        self.customer_b = Customer.objects.create(
            tenant=self.tenant_b,
            name="Battambang Cafe Client",
            email="cafe_b@battambangclient.com",
            phone="012777666",
        )

        login_client_b = APIClient()
        res_b = login_client_b.post(
            "/api/v1/auth/login/",
            {"email": "owner_b_concurrency@battambangsigns.com", "password": "StrongPassword#2026"},
            format="json",
        )
        self.assertEqual(res_b.status_code, status.HTTP_200_OK)
        self.token_b = res_b.json()["access_token"]

    def test_concurrent_quotation_creation_produces_gapless_unique_sequences(self) -> None:
        """
        Verify that 6 simultaneous quotation-creation requests for the same tenant
        acquire the tenant row-level lock, serialize sequence calculation under PostgreSQL,
        and generate distinct, gapless quotation numbers without race conditions.
        """
        concurrency_count = 6
        barrier = threading.Barrier(concurrency_count)
        results = []
        errors = []
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            client = APIClient()
            client.credentials(
                HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
                HTTP_X_TENANT_ID=str(self.tenant_a.id),
            )
            payload = {
                "customer_id": str(self.customer_a.id),
                "title": f"Concurrent Quote Worker {worker_id}",
                "specification_summary": "Flyer 150gsm CMYK",
                "quantity": 500 + worker_id * 10,
                "setup_fee_usd": "5.00",
                "unit_price_usd": "0.10",
                "finishing_fee_usd": "2.00",
                "discount_usd": "0.00",
            }
            try:
                # Synchronize all threads so they fire at the exact same moment
                barrier.wait(timeout=10.0)
                res = client.post("/api/v1/tenant/quotations/", payload, format="json")
                with lock:
                    results.append((worker_id, res.status_code, res.json()))
            except Exception as exc:
                with lock:
                    errors.append((worker_id, exc))
            finally:
                # Ensure independent database connection is cleanly closed
                connections.close_all()

        threads = [
            threading.Thread(target=worker, args=(i,), name=f"Worker-{i}")
            for i in range(concurrency_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        self.assertEqual(len(errors), 0, f"Worker thread encountered exceptions: {errors}")
        self.assertEqual(
            len(results),
            concurrency_count,
            f"Expected {concurrency_count} results, got {len(results)}",
        )

        # 1. Assert all requests succeeded with HTTP 201 Created
        status_codes = [r[1] for r in results]
        self.assertEqual(
            status_codes,
            [status.HTTP_201_CREATED] * concurrency_count,
            f"Non-201 response received: {results}",
        )

        # 2. Assert all 6 returned quote_number values are distinct and match QT-0001 to QT-0006
        returned_quote_numbers = {r[2]["quote_number"] for r in results}
        expected_numbers = {f"QT-{i:04d}" for i in range(1, concurrency_count + 1)}
        self.assertEqual(
            len(returned_quote_numbers),
            concurrency_count,
            f"Duplicate quotation numbers detected: {returned_quote_numbers}",
        )
        self.assertEqual(returned_quote_numbers, expected_numbers)

        # 3. Assert database records persisted correctly with unique numbers
        persisted_quotes = Quotation.objects.filter(tenant=self.tenant_a)
        self.assertEqual(persisted_quotes.count(), concurrency_count)
        persisted_quote_numbers = set(
            persisted_quotes.values_list("quote_number", flat=True)
        )
        self.assertEqual(persisted_quote_numbers, expected_numbers)

    def test_concurrent_quotation_creation_across_different_tenants(self) -> None:
        """
        Verify tenant-scoped isolation: Locking Tenant A does not block or conflict with Tenant B.
        Simultaneous requests to Tenant A and Tenant B both allocate independent sequences (QT-0001, QT-0002).
        """
        concurrency_count = 4  # 2 for Tenant A, 2 for Tenant B
        barrier = threading.Barrier(concurrency_count)
        results = []
        errors = []
        lock = threading.Lock()

        def worker(worker_id: int, tenant, customer, token: str) -> None:
            client = APIClient()
            client.credentials(
                HTTP_AUTHORIZATION=f"Bearer {token}",
                HTTP_X_TENANT_ID=str(tenant.id),
            )
            payload = {
                "customer_id": str(customer.id),
                "title": f"Multi-tenant Quote Worker {worker_id}",
                "specification_summary": "Brochure 200gsm",
                "quantity": 1000,
                "setup_fee_usd": "10.00",
                "unit_price_usd": "0.20",
                "finishing_fee_usd": "5.00",
                "discount_usd": "0.00",
            }
            try:
                barrier.wait(timeout=10.0)
                res = client.post("/api/v1/tenant/quotations/", payload, format="json")
                with lock:
                    results.append((worker_id, str(tenant.id), res.status_code, res.json()))
            except Exception as exc:
                with lock:
                    errors.append((worker_id, exc))
            finally:
                connections.close_all()

        threads = [
            # 2 workers for Tenant A
            threading.Thread(
                target=worker,
                args=(0, self.tenant_a, self.customer_a, self.token_a),
                name="Worker-TenantA-0",
            ),
            threading.Thread(
                target=worker,
                args=(1, self.tenant_a, self.customer_a, self.token_a),
                name="Worker-TenantA-1",
            ),
            # 2 workers for Tenant B
            threading.Thread(
                target=worker,
                args=(2, self.tenant_b, self.customer_b, self.token_b),
                name="Worker-TenantB-0",
            ),
            threading.Thread(
                target=worker,
                args=(3, self.tenant_b, self.customer_b, self.token_b),
                name="Worker-TenantB-1",
            ),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        self.assertEqual(len(errors), 0, f"Worker thread encountered exceptions: {errors}")
        self.assertEqual(len(results), concurrency_count)

        # Assert all 4 succeeded
        status_codes = [r[2] for r in results]
        self.assertEqual(status_codes, [status.HTTP_201_CREATED] * concurrency_count)

        # Check Tenant A quotes
        quotes_a = {r[3]["quote_number"] for r in results if r[1] == str(self.tenant_a.id)}
        self.assertEqual(quotes_a, {"QT-0001", "QT-0002"})

        # Check Tenant B quotes
        quotes_b = {r[3]["quote_number"] for r in results if r[1] == str(self.tenant_b.id)}
        self.assertEqual(quotes_b, {"QT-0001", "QT-0002"})

        # Confirm persisted isolation in DB
        db_a = set(
            Quotation.objects.filter(tenant=self.tenant_a).values_list("quote_number", flat=True)
        )
        db_b = set(
            Quotation.objects.filter(tenant=self.tenant_b).values_list("quote_number", flat=True)
        )
        self.assertEqual(db_a, {"QT-0001", "QT-0002"})
        self.assertEqual(db_b, {"QT-0001", "QT-0002"})

