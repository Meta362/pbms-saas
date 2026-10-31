from django.contrib.auth.hashers import make_password
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from apps.operations.models import (
    Customer,
    CustomerInvoice,
    ProductionJob,
    Quotation,
    QuotationStatus,
    SalesOrder,
)
from apps.subscriptions.models import (
    BillingCycle,
    Plan,
    SubscriptionStatus,
    TenantSubscription,
)
from apps.subscriptions.views import ensure_default_plans
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus

User = get_user_model()


class PrintingBusinessOperationsDomainTests(TestCase):
    """
    Tests REQ-PRINT-01..05, REQ-RBAC-01..03, REQ-SAAS-02, and cross-tenant isolation.
    """

    def setUp(self) -> None:
        self.client = APIClient()
        ensure_default_plans()
        self.starter_plan = Plan.objects.get(code="starter")
        self.password = "PrintShopPass#2026"
        self.owner_a = User.objects.create_user(
            email="owner@khmersunprint.com",
            password=self.password,
            full_name="Vanna Owner",
        )
        self.owner_b = User.objects.create_user(
            email="owner@rivalprint.com",
            password=self.password,
            full_name="Rival Owner",
        )

        self.tenant_a = Tenant.objects.create(
            name="Khmer Sun Printing",
            slug="khmer-sun",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4100.00"),
            tax_rate_percent=Decimal("10.00"),
        )
        self.tenant_b = Tenant.objects.create(
            name="Rival Printing",
            slug="rival-print",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4100.00"),
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

        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.owner_a,
            role=TenantRole.TENANT_OWNER,
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b,
            user=self.owner_b,
            role=TenantRole.TENANT_OWNER,
        )

        login_a = self.client.post(
            "/api/v1/auth/login/",
            {"email": "owner@khmersunprint.com", "password": self.password},
            format="json",
        ).json()
        self.token_a = login_a["access_token"]

        login_b = self.client.post(
            "/api/v1/auth/login/",
            {"email": "owner@rivalprint.com", "password": self.password},
            format="json",
        ).json()
        self.token_b = login_b["access_token"]

    def _auth_tenant_a(self) -> None:
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
            HTTP_X_TENANT_ID=str(self.tenant_a.id),
        )

    def _auth_tenant_b(self) -> None:
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {self.token_b}",
            HTTP_X_TENANT_ID=str(self.tenant_b.id),
        )

    def test_inventory_ledger_and_negative_stock_prevention(self) -> None:
        self._auth_tenant_a()
        mat_res = self.client.post(
            "/api/v1/tenant/materials/",
            {
                "sku": "ART-C2S-300",
                "name": "Art Card 300gsm A3+",
                "unit": "SHEET",
                "reorder_level": "100.000",
                "unit_cost_usd": "0.15",
            },
            format="json",
        )
        self.assertEqual(mat_res.status_code, 201)
        material_id = mat_res.json()["id"]
        self.assertEqual(mat_res.json()["current_stock"], "0.000")

        # 1. Stock In 500 sheets
        in_res = self.client.post(
            "/api/v1/tenant/inventory-movements/",
            {
                "material_id": material_id,
                "transaction_type": "STOCK_IN",
                "quantity_delta": "500.000",
                "reference_note": "PO-001 Initial Stock",
            },
            format="json",
        )
        self.assertEqual(in_res.status_code, 201)
        self.assertEqual(in_res.json()["balance_after"], "500.000")

        # 2. Consume 120 sheets in production
        use_res = self.client.post(
            "/api/v1/tenant/inventory-movements/",
            {
                "material_id": material_id,
                "transaction_type": "CONSUMPTION",
                "quantity_delta": "120.000",
                "reference_note": "Used for SO-0001",
            },
            format="json",
        )
        self.assertEqual(use_res.status_code, 201)
        self.assertEqual(use_res.json()["balance_after"], "380.000")

        # 3. Negative Stock Prevention: Attempt to consume 400 sheets when only 380 available -> 400 Bad Request
        over_res = self.client.post(
            "/api/v1/tenant/inventory-movements/",
            {
                "material_id": material_id,
                "transaction_type": "CONSUMPTION",
                "quantity_delta": "400.000",
                "reference_note": "Over consumption attempt",
            },
            format="json",
        )
        self.assertEqual(over_res.status_code, 400)

    def test_quotation_pricing_order_conversion_production_and_invoice_allocations(self) -> None:
        self._auth_tenant_a()
        cust_res = self.client.post(
            "/api/v1/tenant/customers/",
            {
                "name": "Sokchea Coffee",
                "company_name": "Sokchea Roasters Co., Ltd",
                "phone": "098765432",
                "email": "orders@sokcheacoffee.com",
            },
            format="json",
        )
        self.assertEqual(cust_res.status_code, 201)
        customer_id = cust_res.json()["id"]

        # Create quotation:
        # Setup=$10 + (1000 * $0.08 = $80) + Finishing=$15 = Subtotal $105.00
        # Discount = $5.00 -> Taxable = $100.00
        # Tax (10%) = $10.00 -> Total USD = $110.00
        # Total KHR (4100 rate) = 451,000 Riel
        quote_res = self.client.post(
            "/api/v1/tenant/quotations/",
            {
                "customer_id": customer_id,
                "title": "1,000 Tri-fold Menus (Art Paper + Matte Lamination)",
                "specification_summary": "A4 open, tri-fold, 250gsm, 2-side full color",
                "quantity": 1000,
                "setup_fee_usd": "10.00",
                "unit_price_usd": "0.0800",
                "finishing_fee_usd": "15.00",
                "discount_usd": "5.00",
            },
            format="json",
        )
        self.assertEqual(quote_res.status_code, 201)
        q_data = quote_res.json()
        self.assertEqual(q_data["subtotal_usd"], "105.00")
        self.assertEqual(q_data["tax_amount_usd"], "10.00")
        self.assertEqual(q_data["total_usd"], "110.00")
        self.assertEqual(q_data["total_khr"], "451000")
        quotation_id = q_data["id"]

        # Convert quotation -> SalesOrder + ProductionJob + CustomerInvoice
        conv_res = self.client.post(
            f"/api/v1/tenant/quotations/{quotation_id}/convert/",
            {"artwork_file_name": "sokchea_menu_final_cmyk.pdf"},
            format="json",
        )
        self.assertEqual(conv_res.status_code, 201)
        order_data = conv_res.json()
        self.assertEqual(order_data["order_number"], "SO-0001")
        self.assertEqual(order_data["production_stage"], "PENDING")
        self.assertEqual(order_data["invoice_status"], "ISSUED")
        self.assertEqual(order_data["balance_due_usd"], "110.00")

        job_id = order_data["production_job_id"]
        invoice_id = order_data["invoice_id"]

        # Advance production stage -> PRINTING -> COMPLETED
        stage_res = self.client.post(
            f"/api/v1/tenant/production-jobs/{job_id}/stage/",
            {"stage": "PRINTING", "operator_notes": "Running on Heidelberg offset press"},
            format="json",
        )
        self.assertEqual(stage_res.status_code, 200)
        self.assertEqual(stage_res.json()["order_status"], "IN_PRODUCTION")

        done_res = self.client.post(
            f"/api/v1/tenant/production-jobs/{job_id}/stage/",
            {"stage": "COMPLETED", "operator_notes": "QC passed and packed"},
            format="json",
        )
        self.assertEqual(done_res.status_code, 200)
        self.assertEqual(done_res.json()["order_status"], "READY_FOR_DELIVERY")

        # Partial deposit payment ($50.00) -> PARTIALLY_PAID, balance $60.00
        pay1_res = self.client.post(
            f"/api/v1/tenant/invoices/{invoice_id}/payments/",
            {"amount_usd": "50.00", "payment_method": "KHQR_ABA", "reference_number": "DEP-001"},
            format="json",
        )
        self.assertEqual(pay1_res.status_code, 200)
        self.assertEqual(pay1_res.json()["status"], "PARTIALLY_PAID")
        self.assertEqual(pay1_res.json()["balance_due_usd"], "60.00")

        # Final balance payment ($60.00) -> PAID, balance $0.00
        pay2_res = self.client.post(
            f"/api/v1/tenant/invoices/{invoice_id}/payments/",
            {"amount_usd": "60.00", "payment_method": "CASH_USD", "reference_number": "FIN-002"},
            format="json",
        )
        self.assertEqual(pay2_res.status_code, 200)
        self.assertEqual(pay2_res.json()["status"], "PAID")
        self.assertEqual(pay2_res.json()["balance_due_usd"], "0.00")

        # Cross-Tenant Isolation Check: Tenant B must see 0 orders and 0 customers from Tenant A
        self._auth_tenant_b()
        b_orders = self.client.get("/api/v1/tenant/orders/")
        self.assertEqual(b_orders.status_code, 200)
        self.assertEqual(len(b_orders.json()), 0)

    def _create_role_token(self, email: str, role: str) -> str:
        user = User.objects.create_user(
            email=email,
            password=self.password,
            full_name=f"Staff {role}",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=user,
            role=role,
            is_active=True,
        )
        res = self.client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": self.password},
            format="json",
        ).json()
        return res["access_token"]

    def _auth_token(self, token: str, tenant: Tenant | None = None) -> None:
        target = tenant or self.tenant_a
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_X_TENANT_ID=str(target.id),
        )

    def test_tenant_rbac_matrix_enforces_docs_rbac_permissions_per_role(self) -> None:
        sales_token = self._create_role_token("sales@khmersunprint.com", TenantRole.SALES_STAFF)
        designer_token = self._create_role_token("designer@khmersunprint.com", TenantRole.DESIGNER)
        prod_token = self._create_role_token("prod@khmersunprint.com", TenantRole.PRODUCTION_STAFF)
        inv_token = self._create_role_token("inv@khmersunprint.com", TenantRole.INVENTORY_STAFF)
        fin_token = self._create_role_token("fin@khmersunprint.com", TenantRole.FINANCE_STAFF)
        mgr_token = self._create_role_token("mgr@khmersunprint.com", TenantRole.TENANT_MANAGER)

        # 1. SALES_STAFF can create customers, create quotations, and convert quotes to orders
        self._auth_token(sales_token)
        cust_res = self.client.post(
            "/api/v1/tenant/customers/",
            {"name": "Sales Customer", "phone": "012000111"},
            format="json",
        )
        self.assertEqual(cust_res.status_code, 201)
        customer_id = cust_res.json()["id"]

        quote_res = self.client.post(
            "/api/v1/tenant/quotations/",
            {
                "customer_id": customer_id,
                "title": "500 Brochures",
                "quantity": 500,
                "setup_fee_usd": "5.00",
                "unit_price_usd": "0.1000",
                "finishing_fee_usd": "0.00",
                "discount_usd": "0.00",
            },
            format="json",
        )
        self.assertEqual(quote_res.status_code, 201)
        quotation_id = quote_res.json()["id"]

        conv_res = self.client.post(
            f"/api/v1/tenant/quotations/{quotation_id}/convert/",
            {"artwork_file_name": "brochure.pdf"},
            format="json",
        )
        self.assertEqual(conv_res.status_code, 201)
        order_data = conv_res.json()
        job_id = order_data["production_job_id"]
        invoice_id = order_data["invoice_id"]

        # SALES_STAFF cannot create materials, adjust inventory, or record invoice payments -> 403
        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/materials/",
                {"sku": "SKU-DENIED", "name": "Denied Paper", "unit": "SHEET"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/tenant/invoices/{invoice_id}/payments/",
                {"amount_usd": "10.00", "payment_method": "CASH"},
                format="json",
            ).status_code,
            403,
        )

        # 2. DESIGNER cannot view financial dashboard/invoices, cannot create quotes/payments,
        #    can view orders, and can ONLY transition job stage PENDING -> PRE_PRESS
        self._auth_token(designer_token)
        self.assertEqual(self.client.get("/api/v1/tenant/dashboard/").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/tenant/invoices/").status_code, 403)
        self.assertEqual(
            self.client.post(
                f"/api/v1/tenant/invoices/{invoice_id}/payments/",
                {"amount_usd": "10.00", "payment_method": "CASH"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/quotations/",
                {
                    "customer_id": customer_id,
                    "title": "Unauthorized Quote",
                    "quantity": 100,
                    "unit_price_usd": "0.1000",
                },
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/v1/tenant/orders/").status_code, 200)
        # Designer cannot jump directly to PRINTING -> 403
        self.assertEqual(
            self.client.post(
                f"/api/v1/tenant/production-jobs/{job_id}/stage/",
                {"stage": "PRINTING", "operator_notes": "Skip prepress"},
                format="json",
            ).status_code,
            403,
        )
        # Designer CAN transition PENDING -> PRE_PRESS -> 200
        self.assertEqual(
            self.client.post(
                f"/api/v1/tenant/production-jobs/{job_id}/stage/",
                {"stage": "PRE_PRESS", "operator_notes": "Plates ready"},
                format="json",
            ).status_code,
            200,
        )
        # Designer cannot transition PRE_PRESS -> PRINTING -> 403
        self.assertEqual(
            self.client.post(
                f"/api/v1/tenant/production-jobs/{job_id}/stage/",
                {"stage": "PRINTING", "operator_notes": "Unauthorized press run"},
                format="json",
            ).status_code,
            403,
        )

        # 3. INVENTORY_STAFF can create materials and record STOCK_IN, but cannot record negative ADJUSTMENT
        self._auth_token(inv_token)
        mat_res = self.client.post(
            "/api/v1/tenant/materials/",
            {"sku": "GLOSS-150", "name": "Gloss Paper 150gsm", "unit": "SHEET"},
            format="json",
        )
        self.assertEqual(mat_res.status_code, 201)
        material_id = mat_res.json()["id"]

        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/inventory-movements/",
                {
                    "material_id": material_id,
                    "transaction_type": "STOCK_IN",
                    "quantity_delta": "200.000",
                    "reference_note": "Supplier receipt",
                },
                format="json",
            ).status_code,
            201,
        )
        # Negative manual adjustment by INVENTORY_STAFF -> 403 Forbidden
        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/inventory-movements/",
                {
                    "material_id": material_id,
                    "transaction_type": "ADJUSTMENT",
                    "quantity_delta": "-10.000",
                    "reference_note": "Unauthorized write-off",
                },
                format="json",
            ).status_code,
            403,
        )
        # TENANT_MANAGER can perform manual negative adjustment -> 201 Created
        self._auth_token(mgr_token)
        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/inventory-movements/",
                {
                    "material_id": material_id,
                    "transaction_type": "ADJUSTMENT",
                    "quantity_delta": "-10.000",
                    "reference_note": "Audited manager stock count adjustment",
                },
                format="json",
            ).status_code,
            201,
        )

        # 4. PRODUCTION_STAFF can advance job stages (PRE_PRESS -> PRINTING) and log CONSUMPTION,
        #    but cannot record STOCK_IN or create invoice payments
        self._auth_token(prod_token)
        self.assertEqual(
            self.client.post(
                f"/api/v1/tenant/production-jobs/{job_id}/stage/",
                {"stage": "PRINTING", "operator_notes": "Press started"},
                format="json",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/inventory-movements/",
                {
                    "material_id": material_id,
                    "transaction_type": "CONSUMPTION",
                    "quantity_delta": "50.000",
                    "reference_note": "Job consumption",
                },
                format="json",
            ).status_code,
            201,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/inventory-movements/",
                {
                    "material_id": material_id,
                    "transaction_type": "STOCK_IN",
                    "quantity_delta": "50.000",
                    "reference_note": "Unauthorized stock in",
                },
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/tenant/invoices/{invoice_id}/payments/",
                {"amount_usd": "10.00", "payment_method": "CASH"},
                format="json",
            ).status_code,
            403,
        )

        # 5. FINANCE_STAFF can list invoices and record payments, but cannot create quotes or adjust stock
        self._auth_token(fin_token)
        self.assertEqual(self.client.get("/api/v1/tenant/invoices/").status_code, 200)
        pay_res = self.client.post(
            f"/api/v1/tenant/invoices/{invoice_id}/payments/",
            {"amount_usd": "25.00", "payment_method": "KHQR_ABA", "reference_number": "ABA-001"},
            format="json",
        )
        self.assertEqual(pay_res.status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/quotations/",
                {
                    "customer_id": customer_id,
                    "title": "Finance Unauthorized Quote",
                    "quantity": 100,
                    "unit_price_usd": "0.1000",
                },
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/tenant/inventory-movements/",
                {
                    "material_id": material_id,
                    "transaction_type": "STOCK_IN",
                    "quantity_delta": "10.000",
                },
                format="json",
            ).status_code,
            403,
        )

    def test_monthly_order_entitlement_enforced_atomically_and_isolated_per_tenant(self) -> None:
        self.starter_plan.max_orders_per_month = 2
        self.starter_plan.save(update_fields=["max_orders_per_month", "updated_at"])

        self._auth_tenant_a()
        cust_a = self.client.post(
            "/api/v1/tenant/customers/",
            {"name": "Cap Test Customer A", "phone": "012333444"},
            format="json",
        ).json()["id"]

        quote_ids = []
        for idx in range(3):
            q_res = self.client.post(
                "/api/v1/tenant/quotations/",
                {
                    "customer_id": cust_a,
                    "title": f"Order Cap Quote #{idx + 1}",
                    "quantity": 100,
                    "setup_fee_usd": "5.00",
                    "unit_price_usd": "0.1000",
                },
                format="json",
            )
            self.assertEqual(q_res.status_code, 201)
            quote_ids.append(q_res.json()["id"])

        # 1st and 2nd order conversions succeed (below/at limit of 2)
        self.assertEqual(
            self.client.post(
                f"/api/v1/tenant/quotations/{quote_ids[0]}/convert/",
                {},
                format="json",
            ).status_code,
            201,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/tenant/quotations/{quote_ids[1]}/convert/",
                {},
                format="json",
            ).status_code,
            201,
        )

        # 3rd order conversion exceeds max_orders_per_month=2 -> 400 Bad Request
        over_res = self.client.post(
            f"/api/v1/tenant/quotations/{quote_ids[2]}/convert/",
            {},
            format="json",
        )
        self.assertEqual(over_res.status_code, 400)

        # Verify atomicity: 3rd quotation remains DRAFT and no partial order/job/invoice was created
        third_quote = Quotation.objects.get(id=quote_ids[2])
        self.assertEqual(third_quote.status, QuotationStatus.DRAFT)
        self.assertEqual(SalesOrder.objects.filter(tenant=self.tenant_a).count(), 2)
        self.assertEqual(ProductionJob.objects.filter(tenant=self.tenant_a).count(), 2)
        self.assertEqual(CustomerInvoice.objects.filter(tenant=self.tenant_a).count(), 2)

        # Verify tenant isolation: Tenant B can still convert its own quotation into an order
        self._auth_tenant_b()
        cust_b = self.client.post(
            "/api/v1/tenant/customers/",
            {"name": "Tenant B Customer", "phone": "012555666"},
            format="json",
        ).json()["id"]
        q_b = self.client.post(
            "/api/v1/tenant/quotations/",
            {
                "customer_id": cust_b,
                "title": "Tenant B Quote",
                "quantity": 100,
                "setup_fee_usd": "5.00",
                "unit_price_usd": "0.1000",
            },
            format="json",
        ).json()["id"]
        conv_b = self.client.post(
            f"/api/v1/tenant/quotations/{q_b}/convert/",
            {},
            format="json",
        )
        self.assertEqual(conv_b.status_code, 201)
        self.assertEqual(SalesOrder.objects.filter(tenant=self.tenant_b).count(), 1)

    def test_order_conversion_fails_closed_when_subscription_period_end_is_missing_or_expired(self) -> None:
        self._auth_tenant_a()
        cust_res = self.client.post(
            "/api/v1/tenant/customers/",
            {"name": "Period Test Customer", "phone": "012888999"},
            format="json",
        )
        self.assertEqual(cust_res.status_code, 201)
        customer_id = cust_res.json()["id"]

        quote_res = self.client.post(
            "/api/v1/tenant/quotations/",
            {
                "customer_id": customer_id,
                "title": "Period Test Quotation",
                "quantity": 100,
                "setup_fee_usd": "5.00",
                "unit_price_usd": "0.1000",
            },
            format="json",
        )
        self.assertEqual(quote_res.status_code, 201)
        quote_id = quote_res.json()["id"]

        # 1. Missing current_period_end (current_period_end=None) -> conversion blocked
        self.sub_a.current_period_end = None
        self.sub_a.save(update_fields=["current_period_end", "updated_at"])

        # When calling the API endpoint, HasActiveTenantMembership blocks with 403 Forbidden
        api_conv_res = self.client.post(
            f"/api/v1/tenant/quotations/{quote_id}/convert/",
            {"artwork_file_name": "test.pdf"},
            format="json",
        )
        self.assertEqual(api_conv_res.status_code, 403)

        # Direct service call raises ValidationError
        from rest_framework.exceptions import ValidationError
        from apps.operations.services import convert_quotation_to_order_and_invoice
        with self.assertRaises(ValidationError) as ctx:
            convert_quotation_to_order_and_invoice(
                tenant=self.tenant_a,
                quotation_id=quote_id,
                artwork_file_name="test.pdf",
                actor_user=self.owner_a,
            )
        self.assertIn("Tenant subscription billing period has expired.", str(ctx.exception))

        # Assert quotation remains in DRAFT and zero partial records exist
        quote = Quotation.objects.get(id=quote_id)
        self.assertEqual(quote.status, QuotationStatus.DRAFT)
        self.assertEqual(SalesOrder.objects.filter(quotation=quote).count(), 0)
        self.assertEqual(ProductionJob.objects.filter(sales_order__quotation=quote).count(), 0)
        self.assertEqual(CustomerInvoice.objects.filter(sales_order__quotation=quote).count(), 0)

        # 2. Expired current_period_end -> conversion blocked
        now = timezone.now()
        self.sub_a.current_period_end = now - timedelta(minutes=10)
        self.sub_a.save(update_fields=["current_period_end", "updated_at"])

        with self.assertRaises(ValidationError):
            convert_quotation_to_order_and_invoice(
                tenant=self.tenant_a,
                quotation_id=quote_id,
                artwork_file_name="test.pdf",
                actor_user=self.owner_a,
            )

        quote.refresh_from_db()
        self.assertEqual(quote.status, QuotationStatus.DRAFT)
        self.assertEqual(SalesOrder.objects.filter(quotation=quote).count(), 0)

        # 3. Valid future period end -> conversion succeeds
        self.sub_a.current_period_end = now + timedelta(days=30)
        self.sub_a.save(update_fields=["current_period_end", "updated_at"])

        valid_conv_res = self.client.post(
            f"/api/v1/tenant/quotations/{quote_id}/convert/",
            {"artwork_file_name": "test.pdf"},
            format="json",
        )
        self.assertEqual(valid_conv_res.status_code, 201)
        quote.refresh_from_db()
        self.assertEqual(quote.status, QuotationStatus.CONVERTED)
        self.assertEqual(SalesOrder.objects.filter(quotation=quote).count(), 1)
        self.assertEqual(ProductionJob.objects.filter(sales_order__quotation=quote).count(), 1)
        self.assertEqual(CustomerInvoice.objects.filter(sales_order__quotation=quote).count(), 1)

    def test_quotation_create_rejects_negative_amounts(self) -> None:
        """
        TASK 03B (FIN-02): Verify QuotationCreateSerializer rejects negative
        monetary amounts for setup_fee_usd, unit_price_usd, finishing_fee_usd, and discount_usd.
        """
        self._auth_tenant_a()
        cust_res = self.client.post(
            "/api/v1/tenant/customers/",
            {"name": "Negative Test Customer", "phone": "012999001"},
            format="json",
        )
        self.assertEqual(cust_res.status_code, 201)
        customer_id = cust_res.json()["id"]

        base_payload = {
            "customer_id": customer_id,
            "title": "Validation Test Booklet",
            "quantity": 100,
            "setup_fee_usd": "5.00",
            "unit_price_usd": "0.5000",
            "finishing_fee_usd": "2.00",
            "discount_usd": "1.00",
        }

        # 1. Negative setup_fee_usd
        p1 = dict(base_payload, setup_fee_usd="-1.00")
        res1 = self.client.post("/api/v1/tenant/quotations/", p1, format="json")
        self.assertEqual(res1.status_code, 400)
        self.assertIn("setup_fee_usd", res1.json())

        # 2. Negative unit_price_usd
        p2 = dict(base_payload, unit_price_usd="-0.0100")
        res2 = self.client.post("/api/v1/tenant/quotations/", p2, format="json")
        self.assertEqual(res2.status_code, 400)
        self.assertIn("unit_price_usd", res2.json())

        # 3. Negative finishing_fee_usd
        p3 = dict(base_payload, finishing_fee_usd="-0.50")
        res3 = self.client.post("/api/v1/tenant/quotations/", p3, format="json")
        self.assertEqual(res3.status_code, 400)
        self.assertIn("finishing_fee_usd", res3.json())

        # 4. Negative discount_usd
        p4 = dict(base_payload, discount_usd="-2.00")
        res4 = self.client.post("/api/v1/tenant/quotations/", p4, format="json")
        self.assertEqual(res4.status_code, 400)
        self.assertIn("discount_usd", res4.json())

    def test_quotation_create_accepts_zero_and_positive_amounts(self) -> None:
        """
        TASK 03B (FIN-02): Verify zero is accepted where permitted and positive values calculate accurately.
        """
        self._auth_tenant_a()
        cust_res = self.client.post(
            "/api/v1/tenant/customers/",
            {"name": "Zero Amount Customer", "phone": "012999002"},
            format="json",
        )
        self.assertEqual(cust_res.status_code, 201)
        customer_id = cust_res.json()["id"]

        zero_payload = {
            "customer_id": customer_id,
            "title": "Zero Cost Promotional Flyers",
            "quantity": 50,
            "setup_fee_usd": "0.00",
            "unit_price_usd": "0.0000",
            "finishing_fee_usd": "0.00",
            "discount_usd": "0.00",
        }
        res = self.client.post("/api/v1/tenant/quotations/", zero_payload, format="json")
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["subtotal_usd"], "0.00")
        self.assertEqual(data["total_usd"], "0.00")
        self.assertEqual(data["total_khr"], "0")

    def test_quotation_number_sequential_allocation_under_tenant_lock(self) -> None:
        """
        TASK 03B (FIN-01): Verify sequential quotation numbers remain tenant-scoped
        and serialize under row-level tenant locking.
        """
        self._auth_tenant_a()
        cust_a = self.client.post(
            "/api/v1/tenant/customers/",
            {"name": "Seq Customer A", "phone": "012999003"},
            format="json",
        ).json()["id"]

        q1 = self.client.post(
            "/api/v1/tenant/quotations/",
            {
                "customer_id": cust_a,
                "title": "First Quote",
                "quantity": 100,
                "setup_fee_usd": "5.00",
                "unit_price_usd": "0.1000",
                "finishing_fee_usd": "0.00",
                "discount_usd": "0.00",
            },
            format="json",
        ).json()
        self.assertEqual(q1["quote_number"], "QT-0001")

        q2 = self.client.post(
            "/api/v1/tenant/quotations/",
            {
                "customer_id": cust_a,
                "title": "Second Quote",
                "quantity": 200,
                "setup_fee_usd": "5.00",
                "unit_price_usd": "0.1000",
                "finishing_fee_usd": "0.00",
                "discount_usd": "0.00",
            },
            format="json",
        ).json()
        self.assertEqual(q2["quote_number"], "QT-0002")

        # Now test Tenant B sequence isolation
        self._auth_tenant_b()
        cust_b = self.client.post(
            "/api/v1/tenant/customers/",
            {"name": "Seq Customer B", "phone": "012999004"},
            format="json",
        ).json()["id"]

        q_b1 = self.client.post(
            "/api/v1/tenant/quotations/",
            {
                "customer_id": cust_b,
                "title": "Tenant B First Quote",
                "quantity": 50,
                "setup_fee_usd": "2.00",
                "unit_price_usd": "0.2000",
                "finishing_fee_usd": "0.00",
                "discount_usd": "0.00",
            },
            format="json",
        ).json()
        self.assertEqual(q_b1["quote_number"], "QT-0001")

    def _create_order_and_invoice(self) -> str:
        self._auth_tenant_a()
        cust_id = self.client.post(
            "/api/v1/tenant/customers/",
            {"name": "Invoice Test Customer", "phone": "012888777"},
            format="json",
        ).json()["id"]
        quote_id = self.client.post(
            "/api/v1/tenant/quotations/",
            {
                "customer_id": cust_id,
                "title": "Invoice Validation Quote",
                "quantity": 100,
                "setup_fee_usd": "0.00",
                "unit_price_usd": "1.0000",
                "finishing_fee_usd": "0.00",
                "discount_usd": "0.00",
            },
            format="json",
        ).json()["id"]
        conv_res = self.client.post(
            f"/api/v1/tenant/quotations/{quote_id}/convert/",
            {"artwork_file_name": "test_artwork.pdf"},
            format="json",
        )
        return conv_res.json()["invoice_id"]

    def test_invoice_payment_create_serializer_validation(self) -> None:
        """P2 unit validation: verify InvoicePaymentCreateSerializer enforces min_value=0.01."""
        from apps.operations.serializers import InvoicePaymentCreateSerializer

        # Reject negative amounts
        s_neg = InvoicePaymentCreateSerializer(data={"amount_usd": "-5.00"})
        self.assertFalse(s_neg.is_valid())
        self.assertIn("amount_usd", s_neg.errors)

        # Reject zero amount
        s_zero = InvoicePaymentCreateSerializer(data={"amount_usd": "0.00"})
        self.assertFalse(s_zero.is_valid())
        self.assertIn("amount_usd", s_zero.errors)

        # Accept valid positive boundary amount
        s_min = InvoicePaymentCreateSerializer(data={"amount_usd": "0.01"})
        self.assertTrue(s_min.is_valid())
        self.assertEqual(s_min.validated_data["amount_usd"], Decimal("0.01"))

    def test_invoice_payment_rejects_negative_and_zero_amounts_via_api(self) -> None:
        """P2 API validation: verify /tenant/invoices/{id}/payments/ returns HTTP 400 for non-positive values."""
        invoice_id = self._create_order_and_invoice()

        # 1. Negative amount
        res_neg = self.client.post(
            f"/api/v1/tenant/invoices/{invoice_id}/payments/",
            {"amount_usd": "-15.00", "payment_method": "KHQR_ABA"},
            format="json",
        )
        self.assertEqual(res_neg.status_code, 400)
        self.assertIn("amount_usd", res_neg.json())

        # 2. Zero amount
        res_zero = self.client.post(
            f"/api/v1/tenant/invoices/{invoice_id}/payments/",
            {"amount_usd": "0.00", "payment_method": "KHQR_ABA"},
            format="json",
        )
        self.assertEqual(res_zero.status_code, 400)
        self.assertIn("amount_usd", res_zero.json())

    def test_invoice_payment_accepts_valid_boundary_amount_via_api(self) -> None:
        """P2 API validation: verify /tenant/invoices/{id}/payments/ accepts 0.01 boundary."""
        invoice_id = self._create_order_and_invoice()

        res = self.client.post(
            f"/api/v1/tenant/invoices/{invoice_id}/payments/",
            {"amount_usd": "0.01", "payment_method": "KHQR_ABA"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["paid_usd"], "0.01")
        self.assertEqual(data["balance_due_usd"], "109.99")
        self.assertEqual(data["status"], "PARTIALLY_PAID")


class MultiItemQuotationAndOrderLineItemTests(TestCase):
    """
    DOM-001 & docs/DATABASE.md Section 2.4:
    Verifies multi-item quotation creation, deterministic line-item rollup,
    QuotationItem persistence, and SalesOrderItem propagation on conversion.
    """

    def setUp(self):
        self.client = APIClient()
        self.password = "TenantPass#2026"
        self.tenant = Tenant.objects.create(
            name="Angkor Commercial Press",
            slug="angkor-press",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4100.00"),
            tax_rate_percent=Decimal("10.00"),
        )
        self.user = User.objects.create(
            email="owner@angkor-press.com",
            full_name="Angkor Owner",
            password=make_password(self.password),
            is_active=True,
        )
        self.membership = TenantMembership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=TenantRole.TENANT_OWNER,
        )
        plan = Plan.objects.create(
            code="enterprise-plan",
            name_en="Enterprise Plan",
            name_km="គម្រោងសហគ្រាស",
            monthly_price_usd=Decimal("99.00"),
            annual_price_usd=Decimal("990.00"),
            max_staff_users=20,
            max_orders_per_month=500,
        )
        TenantSubscription.objects.create(
            tenant=self.tenant,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            name="Chip Mong Innotech",
            company_name="Chip Mong Group",
            phone="012345678",
        )

        login_res = self.client.post(
            "/api/v1/auth/login/",
            {"email": "owner@angkor-press.com", "password": self.password},
            format="json",
        )
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json()["access_token"]
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_X_TENANT_ID=str(self.tenant.id),
        )

    def test_multi_item_quotation_creation_and_rollups(self):
        """
        Tests creating a quotation with 2 distinct line items:
        Item 1: 1,000 Business Cards @ $0.0350 + $5 Setup + $10 Finishing = $50.00
        Item 2: 500 Letterheads @ $0.0800 + $10 Setup + $0 Finishing = $50.00
        Total Subtotal: $100.00
        Discount: $10.00 -> Taxable: $90.00
        Tax (10%): $9.00 -> Total USD: $99.00
        Total KHR (4100): 405,900 Riel
        """
        payload = {
            "customer_id": str(self.customer.id),
            "title": "Corporate Identity Print Package",
            "discount_usd": "10.00",
            "items": [
                {
                    "item_title": "1,000 Business Cards",
                    "specification_summary": "300gsm Art Card, 2-side Matte",
                    "quantity": 1000,
                    "unit_price_usd": "0.0350",
                    "setup_fee_usd": "5.00",
                    "finishing_fee_usd": "10.00",
                },
                {
                    "item_title": "500 Letterheads A4",
                    "specification_summary": "100gsm Woodfree, 1-side CMYK",
                    "quantity": 500,
                    "unit_price_usd": "0.0800",
                    "setup_fee_usd": "10.00",
                    "finishing_fee_usd": "0.00",
                },
            ],
        }

        res = self.client.post("/api/v1/tenant/quotations/", payload, format="json")
        self.assertEqual(res.status_code, 201)
        data = res.json()

        # Check calculated rollups
        self.assertEqual(data["subtotal_usd"], "100.00")
        self.assertEqual(data["tax_amount_usd"], "9.00")
        self.assertEqual(data["total_usd"], "99.00")
        self.assertEqual(data["total_khr"], "405900")
        self.assertEqual(data["quantity"], 1500)  # Sum of item quantities

        # Check items in response
        self.assertIn("items", data)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["item_title"], "1,000 Business Cards")
        self.assertEqual(data["items"][0]["subtotal_usd"], "50.00")
        self.assertEqual(data["items"][1]["item_title"], "500 Letterheads A4")
        self.assertEqual(data["items"][1]["subtotal_usd"], "50.00")

        # Verify database models
        quote_id = data["id"]
        from apps.operations.models import QuotationItem
        db_items = QuotationItem.objects.filter(quotation_id=quote_id)
        self.assertEqual(db_items.count(), 2)

    def test_multi_item_quotation_conversion_populates_sales_order_items(self):
        """
        Tests converting a multi-item quotation into a SalesOrder spawns corresponding SalesOrderItems.
        """
        payload = {
            "customer_id": str(self.customer.id),
            "title": "Dual Item Package",
            "discount_usd": "0.00",
            "items": [
                {
                    "item_title": "Brochure A4",
                    "specification_summary": "150gsm Gloss",
                    "quantity": 200,
                    "unit_price_usd": "0.5000",
                    "setup_fee_usd": "10.00",
                    "finishing_fee_usd": "5.00",
                },
                {
                    "item_title": "Rollup Banner 80x200cm",
                    "specification_summary": "PP Synthetic + Stand",
                    "quantity": 2,
                    "unit_price_usd": "15.0000",
                    "setup_fee_usd": "5.00",
                    "finishing_fee_usd": "0.00",
                },
            ],
        }
        q_res = self.client.post("/api/v1/tenant/quotations/", payload, format="json")
        self.assertEqual(q_res.status_code, 201)
        quote_id = q_res.json()["id"]

        # Convert to Sales Order
        conv_res = self.client.post(
            f"/api/v1/tenant/quotations/{quote_id}/convert/",
            {"artwork_file_name": "package_artwork_final.pdf"},
            format="json",
        )
        self.assertEqual(conv_res.status_code, 201)
        order_data = conv_res.json()
        self.assertEqual(order_data["order_number"], "SO-0001")

        # Verify SalesOrderItem models created
        from apps.operations.models import SalesOrderItem
        order_items = SalesOrderItem.objects.filter(sales_order_id=order_data["id"])
        self.assertEqual(order_items.count(), 2)
        self.assertEqual(order_items.filter(item_title="Brochure A4").count(), 1)
        self.assertEqual(order_items.filter(item_title="Rollup Banner 80x200cm").count(), 1)


class CambodiaBakongKhqrTests(TestCase):
    """
    CAM-001: Verification of NBC Bakong KHQR dynamic EMVCo payloads,
    dual-currency breakdowns (USD & KHR), and strict tenant isolation.
    """

    def setUp(self) -> None:
        self.client = APIClient()
        ensure_default_plans()
        self.starter_plan = Plan.objects.get(code="starter")

        self.tenant_a = Tenant.objects.create(
            name="Angkor Printing House",
            slug="angkor-print",
            status=TenantStatus.ACTIVE,
            phone="+85512998877",
            khr_exchange_rate=Decimal("4120.00"),
        )
        self.tenant_b = Tenant.objects.create(
            name="Mekong Offset",
            slug="mekong-offset",
            status=TenantStatus.ACTIVE,
            phone="+85512112233",
            khr_exchange_rate=Decimal("4100.00"),
        )
        self.user_a = User.objects.create_user(
            email="owner.angkor@pbms.local",
            password="StrongPassword123!",
            full_name="Angkor Owner",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            role=TenantRole.TENANT_OWNER,
            is_active=True,
        )

        self.user_designer = User.objects.create_user(
            email="designer.angkor@pbms.local",
            password="StrongPassword123!",
            full_name="Angkor Designer",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_a,
            user=self.user_designer,
            role=TenantRole.DESIGNER,
            is_active=True,
        )

        self.user_b = User.objects.create_user(
            email="owner.mekong@pbms.local",
            password="StrongPassword123!",
            full_name="Mekong Owner",
        )
        TenantMembership.objects.create(
            tenant=self.tenant_b,
            user=self.user_b,
            role=TenantRole.TENANT_OWNER,
            is_active=True,
        )

        now = timezone.now()
        TenantSubscription.objects.create(
            tenant=self.tenant_a,
            plan=self.starter_plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=365),
        )
        TenantSubscription.objects.create(
            tenant=self.tenant_b,
            plan=self.starter_plan,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=365),
        )

        self.customer = Customer.objects.create(
            tenant=self.tenant_a,
            name="Sihanoukville Casino & Hotel",
            phone="034998877",
        )

    def _login_as(self, user: User, tenant: Tenant) -> None:
        login_res = self.client.post(
            "/api/v1/auth/login/",
            {"email": user.email, "password": "StrongPassword123!"},
            format="json",
        )
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json()["access_token"]
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_X_TENANT_ID=str(tenant.id),
        )

    def test_emvco_crc16_and_tlv_compliance(self) -> None:
        """
        Verify pure Python CRC-16 (CCITT-FALSE 0x1021) and TLV generation.
        """
        from apps.operations.khqr_service import compute_emv_crc16, generate_khqr_payload, generate_khqr_svg

        # Known standard test
        sample = "00020101021129370016A0000006770101110113006681234567853037645802TH6304"
        self.assertEqual(compute_emv_crc16(sample), "823E")

        # Generate USD dynamic payload
        usd_payload = generate_khqr_payload(
            bakong_account_id="angkor_print@aclb",
            merchant_name="Angkor Printing House",
            merchant_city="Phnom Penh",
            amount=Decimal("150.00"),
            currency="USD",
            bill_number="INV-0001",
        )
        qr_str = usd_payload["qr_payload"]
        self.assertTrue(qr_str.startswith("000201010212"))
        self.assertIn("5303840", qr_str)  # USD currency code
        self.assertIn("5406150.00", qr_str)  # Amount
        self.assertIn("5802KH", qr_str)  # Cambodia
        self.assertIn("6304", qr_str)  # CRC tag

        # Verify CRC integrity: recalculating over payload[:-4] matches payload[-4:]
        calculated_crc = compute_emv_crc16(qr_str[:-4])
        self.assertEqual(calculated_crc, qr_str[-4:])

        # Verify SVG generation
        svg = generate_khqr_svg(qr_str, size=300)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn('viewBox="0 0', svg)
        self.assertIn("<path d=", svg)

    def test_invoice_khqr_endpoint_and_strict_tenant_isolation(self) -> None:
        """
        Verify GET /api/v1/tenant/invoices/<id>/khqr/ returns valid bundle
        and blocks cross-tenant access.
        """
        self._login_as(self.user_a, self.tenant_a)

        # 1. Create quote and convert to generate invoice
        q_res = self.client.post(
            "/api/v1/tenant/quotations/",
            {
                "customer_id": str(self.customer.id),
                "title": "VIP Brochures",
                "quantity": 500,
                "setup_fee_usd": "20.00",
                "unit_price_usd": "0.4000",
                "finishing_fee_usd": "10.00",
                "discount_usd": "0.00",
            },
            format="json",
        )
        self.assertEqual(q_res.status_code, 201)
        quote_id = q_res.json()["id"]

        conv_res = self.client.post(
            f"/api/v1/tenant/quotations/{quote_id}/convert/",
            {"artwork_file_name": "vip_brochures.pdf"},
            format="json",
        )
        self.assertEqual(conv_res.status_code, 201)

        # Retrieve invoice list
        inv_res = self.client.get("/api/v1/tenant/invoices/")
        self.assertEqual(inv_res.status_code, 200)
        invoices = inv_res.json()
        self.assertGreater(len(invoices), 0)
        invoice_id = invoices[0]["id"]

        # 2. Fetch KHQR bundle
        khqr_res = self.client.get(f"/api/v1/tenant/invoices/{invoice_id}/khqr/")
        self.assertEqual(khqr_res.status_code, 200)
        data = khqr_res.json()

        self.assertEqual(data["invoice_id"], invoice_id)
        self.assertEqual(data["merchant_name"], "Angkor Printing House")
        self.assertEqual(data["khr_exchange_rate"], "4120.00")
        self.assertEqual(data["balance_due_usd"], "230.00")  # (500*0.4) + 20 + 10 = 230
        self.assertEqual(data["balance_due_khr"], "947600")  # 230 * 4120 = 947600

        # Validate USD sub-bundle
        self.assertEqual(data["usd"]["currency"], "USD")
        self.assertEqual(data["usd"]["amount"], "230.00")
        self.assertTrue(len(data["usd"]["qr_payload"]) > 50)
        self.assertTrue(len(data["usd"]["qr_svg"]) > 200)
        self.assertEqual(len(data["usd"]["md5_hash"]), 32)
        self.assertTrue(data["usd"]["deep_link"].startswith("https://bakong.nbc.org.kh/pay?qr="))

        # Validate KHR sub-bundle
        self.assertEqual(data["khr"]["currency"], "KHR")
        self.assertEqual(data["khr"]["amount"], "947600")
        self.assertTrue("5303116" in data["khr"]["qr_payload"])  # KHR code

        # 3. RBAC Check: DESIGNER role should be forbidden (403)
        self._login_as(self.user_designer, self.tenant_a)
        designer_res = self.client.get(f"/api/v1/tenant/invoices/{invoice_id}/khqr/")
        self.assertEqual(designer_res.status_code, 403)

        # 4. Strict Tenant Isolation: Tenant B user cannot access Tenant A invoice (404)
        self._login_as(self.user_b, self.tenant_b)
        cross_res = self.client.get(f"/api/v1/tenant/invoices/{invoice_id}/khqr/")
        self.assertEqual(cross_res.status_code, 404)
