from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus

User = get_user_model()


class PrintingBusinessOperationsDomainTests(TestCase):
    """
    Tests REQ-PRINT-01 through REQ-PRINT-05 and cross-tenant isolation on business records.
    """

    def setUp(self) -> None:
        self.client = APIClient()
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
