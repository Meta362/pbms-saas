from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.operations.models import Customer, InventoryTransactionType, Material, MaterialUnit, Quotation
from apps.operations.services import (
    calculate_quotation_totals,
    convert_quotation_to_order_and_invoice,
    record_customer_invoice_payment,
    record_inventory_movement,
)
from apps.subscriptions.models import (
    BillingCycle,
    PaymentProvider,
    PaymentStatus,
    Plan,
    SubscriptionPayment,
    SubscriptionStatus,
    TenantSubscription,
)
from apps.subscriptions.views import ensure_default_plans
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds idempotent demo data for Super Admin (Frontend A), Tenant Workspace (Frontend B), and Public Site (Frontend C)."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError("This command can only be run in local development mode (DEBUG=True).")

        ensure_default_plans()
        growth_plan = Plan.objects.get(code="growth")
        starter_plan = Plan.objects.get(code="starter")

        # 1. Super Admin Account (Frontend A)
        super_admin, created = User.objects.get_or_create(
            email="admin@pbms.local",
            defaults={"full_name": "PBMS Platform Operator"},
        )
        if created:
            super_admin.set_password("Admin@PBMS2026")
            super_admin.is_staff = True
            super_admin.is_superuser = True
            super_admin.is_platform_staff = True
            super_admin.platform_role = "SUPER_ADMIN"
            super_admin.save()

        # 2. Active Tenant: Angkor Printing House (Frontend B)
        owner, created = User.objects.get_or_create(
            email="owner@angkorprint.com",
            defaults={"full_name": "Sokha Angkor (Tenant Owner)", "phone": "012888999"},
        )
        if created:
            owner.set_password("Owner@PBMS2026")
            owner.save()

        angkor_tenant, t_created = Tenant.objects.get_or_create(
            slug="angkor-printing",
            defaults={
                "name": "Angkor Printing House (រោងពុម្ពអង្គរ)",
                "status": TenantStatus.ACTIVE,
                "phone": "012888999",
                "email": "owner@angkorprint.com",
                "address": "St. 271, Sangkat Tuol Tompoung, Phnom Penh",
                "khr_exchange_rate": Decimal("4100.00"),
                "tax_rate_percent": Decimal("10.00"),
            },
        )
        TenantMembership.objects.get_or_create(
            tenant=angkor_tenant,
            user=owner,
            defaults={"role": TenantRole.TENANT_OWNER, "is_active": True},
        )

        now = timezone.now()
        sub_a, _ = TenantSubscription.objects.get_or_create(
            tenant=angkor_tenant,
            defaults={
                "plan": growth_plan,
                "billing_cycle": BillingCycle.MONTHLY,
                "status": SubscriptionStatus.ACTIVE,
                "current_period_start": now,
                "current_period_end": now + timedelta(days=30),
            },
        )
        SubscriptionPayment.objects.get_or_create(
            idempotency_key="seed-angkor-initial-payment",
            defaults={
                "tenant": angkor_tenant,
                "subscription": sub_a,
                "amount_usd": growth_plan.monthly_price_usd,
                "provider": PaymentProvider.MANUAL_TRANSFER,
                "provider_reference": "ABA-KHQR-100200",
                "status": PaymentStatus.SUCCEEDED,
                "verified_by": super_admin,
                "verified_at": now,
                "notes": "Initial verified seed subscription payment",
            },
        )

        # Seed Operational Data for Angkor Printing House if not already present
        if not Customer.objects.filter(tenant=angkor_tenant).exists():
            customer = Customer.objects.create(
                tenant=angkor_tenant,
                name="Brown Aroma Cafe",
                company_name="Brown Aroma F&B Co., Ltd",
                phone="023999888",
                email="procurement@brownaroma.com",
                address="BKK1, Phnom Penh",
            )
            material = Material.objects.create(
                tenant=angkor_tenant,
                sku="PAPER-ART-300",
                name="Art Card 300gsm (79x109cm)",
                unit=MaterialUnit.SHEET,
                reorder_level=Decimal("200.000"),
                unit_cost_usd=Decimal("0.18"),
            )
            record_inventory_movement(
                tenant=angkor_tenant,
                material_id=str(material.id),
                transaction_type=InventoryTransactionType.STOCK_IN,
                quantity_delta=Decimal("1500.000"),
                reference_note="Initial Warehouse Stock In",
                actor_user=owner,
            )

            totals = calculate_quotation_totals(
                tenant=angkor_tenant,
                quantity=2000,
                setup_fee_usd=Decimal("15.00"),
                unit_price_usd=Decimal("0.0750"),
                finishing_fee_usd=Decimal("25.00"),
                discount_usd=Decimal("10.00"),
            )
            quote = Quotation.objects.create(
                tenant=angkor_tenant,
                customer=customer,
                quote_number="QT-0001",
                title="2,000 Luxury Takeaway Cup Sleeves & Menus",
                specification_summary="300gsm Art Card, Matte Lamination + Gold Foil Stamping",
                quantity=2000,
                setup_fee_usd=Decimal("15.00"),
                unit_price_usd=Decimal("0.0750"),
                finishing_fee_usd=Decimal("25.00"),
                discount_usd=Decimal("10.00"),
                subtotal_usd=totals["subtotal_usd"],
                tax_amount_usd=totals["tax_amount_usd"],
                total_usd=totals["total_usd"],
                total_khr=totals["total_khr"],
                created_by=owner,
            )
            order = convert_quotation_to_order_and_invoice(
                tenant=angkor_tenant,
                quotation_id=str(quote.id),
                artwork_file_name="brown_aroma_menu_v3_cmyk.pdf",
                actor_user=owner,
            )
            record_customer_invoice_payment(
                tenant=angkor_tenant,
                invoice_id=str(order.invoice.id),
                amount_usd=Decimal("80.00"),
                payment_method="KHQR_ABA",
                reference_number="ABA-DEP-556677",
                actor_user=owner,
            )

        # 3. Pending Review Tenant: Mekong Offset Press (For Super Admin Approval Demo)
        mekong_owner, m_created = User.objects.get_or_create(
            email="dara@mekongoffset.com",
            defaults={"full_name": "Dara Mekong", "phone": "077555444"},
        )
        if m_created:
            mekong_owner.set_password("Owner@PBMS2026")
            mekong_owner.save()

        mekong_tenant, _ = Tenant.objects.get_or_create(
            slug="mekong-offset",
            defaults={
                "name": "Mekong Offset Press (រោងពុម្ពមេគង្គ)",
                "status": TenantStatus.PENDING_REVIEW,
                "phone": "077555444",
                "email": "dara@mekongoffset.com",
                "address": "Sangkat Svay Dangkum, Siem Reap",
            },
        )
        TenantMembership.objects.get_or_create(
            tenant=mekong_tenant,
            user=mekong_owner,
            defaults={"role": TenantRole.TENANT_OWNER, "is_active": True},
        )
        sub_b, _ = TenantSubscription.objects.get_or_create(
            tenant=mekong_tenant,
            defaults={
                "plan": starter_plan,
                "billing_cycle": BillingCycle.MONTHLY,
                "status": SubscriptionStatus.PENDING_PAYMENT,
            },
        )
        SubscriptionPayment.objects.get_or_create(
            idempotency_key="seed-mekong-pending-payment",
            defaults={
                "tenant": mekong_tenant,
                "subscription": sub_b,
                "amount_usd": starter_plan.monthly_price_usd,
                "provider": PaymentProvider.MANUAL_TRANSFER,
                "provider_reference": "ACLEDA-TXN-889900",
                "status": PaymentStatus.PENDING,
                "notes": "Awaiting Super Admin verification",
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Successfully seeded PBMS demo data (Super Admin, Angkor Printing House, Mekong Offset Press)."
            )
        )
