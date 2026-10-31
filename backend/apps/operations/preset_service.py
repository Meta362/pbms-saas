from decimal import Decimal
from typing import Any, Dict
from django.db import transaction
from apps.core.models import AuditEvent
from apps.operations.models import Customer, Material, MaterialUnit
from apps.tenants.models import Tenant


@transaction.atomic
def seed_tenant_master_presets(tenant: Tenant, actor_user: Any) -> Dict[str, Any]:
    """
    PROD-PRESETS: 1-Click Master Catalog Seeder for newly onboarded or existing print shops.
    Populates standard Cambodian paper stocks, synthetic substrates, and initial customer profile.
    """
    created_materials = 0
    created_customers = 0

    standard_materials = [
        {
            "name": "Art Card 300gsm (Couche 2-Side 790x1090mm)",
            "sku": "MAT-AC-300",
            "unit": MaterialUnit.SHEET,
            "unit_cost_usd": Decimal("0.25"),
            "current_stock": Decimal("500.000"),
            "reorder_level": Decimal("100.000"),
        },
        {
            "name": "Art Paper 150gsm (Glossy Text 650x900mm)",
            "sku": "MAT-AP-150",
            "unit": MaterialUnit.SHEET,
            "unit_cost_usd": Decimal("0.12"),
            "current_stock": Decimal("1000.000"),
            "reorder_level": Decimal("200.000"),
        },
        {
            "name": "Woodfree Paper 100gsm (Book Paper 790x1090mm)",
            "sku": "MAT-WF-100",
            "unit": MaterialUnit.SHEET,
            "unit_cost_usd": Decimal("0.08"),
            "current_stock": Decimal("2000.000"),
            "reorder_level": Decimal("500.000"),
        },
        {
            "name": "PP Synthetic Waterproof Sticker Roll",
            "sku": "MAT-PP-STICKER",
            "unit": MaterialUnit.ROLL,
            "unit_cost_usd": Decimal("1.80"),
            "current_stock": Decimal("50.000"),
            "reorder_level": Decimal("10.000"),
        },
        {
            "name": "Outdoor Flex Vinyl Banner 380gsm Roll",
            "sku": "MAT-VINYL-380",
            "unit": MaterialUnit.ROLL,
            "unit_cost_usd": Decimal("1.20"),
            "current_stock": Decimal("100.000"),
            "reorder_level": Decimal("20.000"),
        },
    ]

    for item in standard_materials:
        _, created = Material.objects.get_or_create(
            tenant=tenant,
            sku=item["sku"],
            defaults={
                "name": item["name"],
                "unit": item["unit"],
                "unit_cost_usd": item["unit_cost_usd"],
                "current_stock": item["current_stock"],
                "reorder_level": item["reorder_level"],
            },
        )
        if created:
            created_materials += 1

    # Ensure default walk-in customer exists
    _, cust_created = Customer.objects.get_or_create(
        tenant=tenant,
        phone="012000000",
        defaults={
            "name": "Walk-in Cash Customer (អតិថិជនទូទៅ)",
            "company_name": "General Retail",
            "address": "Phnom Penh",
        },
    )
    if cust_created:
        created_customers += 1

    AuditEvent.objects.create(
        actor_user=actor_user,
        tenant=tenant,
        event_type="TENANT_MASTER_PRESETS_SEEDED",
        target_model="tenants.Tenant",
        target_id=str(tenant.id),
        metadata={
            "tenant_name": tenant.name,
            "materials_created": created_materials,
            "customers_created": created_customers,
        },
    )

    return {
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
        "materials_seeded": created_materials,
        "customers_seeded": created_customers,
        "message": f"Successfully seeded {created_materials} materials and default customer.",
    }
