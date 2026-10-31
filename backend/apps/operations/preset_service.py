from decimal import Decimal
from typing import Any, Dict
from django.db import transaction
from apps.core.models import AuditEvent
from apps.operations.models import Customer, Material, MaterialUnit
from apps.tenants.models import Tenant


@transaction.atomic
def seed_tenant_master_presets(
    tenant: Tenant,
    actor_user: Any,
    pack_type: str = "ALL",
) -> Dict[str, Any]:
    """
    PROD-PRESETS: 1-Click Master Catalog Seeder.
    Supports:
    - 'DIGITAL': Small & Quick Print Shop (A4 reams, A3+ digital sheets, flash stamps, sqm stickers, card boxes)
    - 'OFFSET': Commercial Offset Press (790x1090, 650x900 parent sheets, 3.2m flex vinyl rolls)
    - 'ALL': Complete printing inventory preset
    """
    created_materials = 0
    created_customers = 0

    digital_materials = [
        {
            "name": "Double A Copy Paper 80gsm A4 (500s/ream)",
            "sku": "MAT-A4-80-COPY",
            "unit": MaterialUnit.PIECE,
            "unit_cost_usd": Decimal("3.50"),
            "current_stock": Decimal("50.000"),
            "reorder_level": Decimal("10.000"),
        },
        {
            "name": "Digital Art Card 300gsm A3+ (480x330mm)",
            "sku": "MAT-A3-300-CARD",
            "unit": MaterialUnit.SHEET,
            "unit_cost_usd": Decimal("0.15"),
            "current_stock": Decimal("500.000"),
            "reorder_level": Decimal("100.000"),
        },
        {
            "name": "Trodat Self-Inking Flash Stamp Mount 47x18mm",
            "sku": "MAT-STAMP-FLASH-TRODAT",
            "unit": MaterialUnit.PIECE,
            "unit_cost_usd": Decimal("2.50"),
            "current_stock": Decimal("30.000"),
            "reorder_level": Decimal("5.000"),
        },
        {
            "name": "PP Synthetic Waterproof Sticker ($/m²)",
            "sku": "MAT-PP-STICKER",
            "unit": MaterialUnit.SQM,
            "unit_cost_usd": Decimal("3.20"),
            "current_stock": Decimal("100.000"),
            "reorder_level": Decimal("20.000"),
        },
        {
            "name": "Matte Laminated Business Card Box (100 cards)",
            "sku": "MAT-BOX-NAMECARD-BLANK",
            "unit": MaterialUnit.PIECE,
            "unit_cost_usd": Decimal("1.80"),
            "current_stock": Decimal("200.000"),
            "reorder_level": Decimal("50.000"),
        },
    ]

    offset_materials = [
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
            "name": "Outdoor Flex Vinyl Banner 380gsm Roll",
            "sku": "MAT-VINYL-380",
            "unit": MaterialUnit.ROLL,
            "unit_cost_usd": Decimal("1.20"),
            "current_stock": Decimal("100.000"),
            "reorder_level": Decimal("20.000"),
        },
    ]

    pack_upper = (pack_type or "ALL").upper()
    selected_materials = []
    if pack_upper in ("DIGITAL", "ALL"):
        selected_materials.extend(digital_materials)
    if pack_upper in ("OFFSET", "ALL"):
        selected_materials.extend(offset_materials)

    for item in selected_materials:
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
            "pack_type": pack_upper,
            "materials_created": created_materials,
            "customers_created": created_customers,
        },
    )

    return {
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
        "pack_type": pack_upper,
        "materials_seeded": created_materials,
        "customers_seeded": created_customers,
        "message": f"Successfully seeded {created_materials} materials ({pack_upper} pack) and default customer.",
    }
