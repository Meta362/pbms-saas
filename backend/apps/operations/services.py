from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from rest_framework.exceptions import ValidationError
from apps.core.models import AuditEvent
from apps.operations.models import (
    CustomerInvoice,
    CustomerPayment,
    InventoryTransaction,
    InventoryTransactionType,
    InvoiceStatus,
    Material,
    OrderStatus,
    ProductionJob,
    ProductionStage,
    Quotation,
    QuotationStatus,
    SalesOrder,
)
from apps.tenants.models import Tenant


def round_usd(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def round_khr_nearest_100(usd_amount: Decimal, exchange_rate: Decimal) -> Decimal:
    """
    DOM-01: Converts USD to KHR and rounds to the nearest 100 Riel.
    """
    raw_khr = usd_amount * exchange_rate
    hundreds = (raw_khr / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return hundreds * Decimal("100")


def calculate_quotation_totals(
    *,
    tenant: Tenant,
    quantity: int,
    setup_fee_usd: Decimal,
    unit_price_usd: Decimal,
    finishing_fee_usd: Decimal,
    discount_usd: Decimal,
) -> dict[str, Decimal]:
    """
    REQ-PRINT-01: Deterministic quotation pricing calculation.
    """
    subtotal = round_usd(
        setup_fee_usd + (Decimal(quantity) * unit_price_usd) + finishing_fee_usd
    )
    if discount_usd > subtotal:
        raise ValidationError("Discount cannot exceed quotation subtotal.")

    taxable = subtotal - discount_usd
    tax_amount = round_usd(taxable * (tenant.tax_rate_percent / Decimal("100.00")))
    total_usd = round_usd(taxable + tax_amount)
    total_khr = round_khr_nearest_100(total_usd, tenant.khr_exchange_rate)

    return {
        "subtotal_usd": subtotal,
        "tax_amount_usd": tax_amount,
        "total_usd": total_usd,
        "total_khr": total_khr,
    }


@transaction.atomic
def record_inventory_movement(
    *,
    tenant: Tenant,
    material_id: str,
    transaction_type: str,
    quantity_delta: Decimal,
    reference_note: str,
    actor_user,
) -> InventoryTransaction:
    """
    REQ-PRINT-04: Atomically updates material stock via an immutable ledger entry.
    Prevents negative available stock.
    """
    try:
        material = Material.objects.select_for_update().get(
            id=material_id,
            tenant=tenant,
        )
    except Material.DoesNotExist as exc:
        raise ValidationError("Material not found in this tenant.") from exc

    if quantity_delta == Decimal("0.000"):
        raise ValidationError("Quantity delta cannot be zero.")

    if transaction_type in (
        InventoryTransactionType.CONSUMPTION,
        InventoryTransactionType.WASTE,
    ) and quantity_delta > Decimal("0.000"):
        quantity_delta = -quantity_delta

    new_balance = material.current_stock + quantity_delta
    if new_balance < Decimal("0.000"):
        raise ValidationError(
            f"Insufficient stock for '{material.name}'. Available: {material.current_stock}, Requested change: {quantity_delta}."
        )

    material.current_stock = new_balance
    material.save(update_fields=["current_stock", "updated_at"])

    entry = InventoryTransaction.objects.create(
        tenant=tenant,
        material=material,
        transaction_type=transaction_type,
        quantity_delta=quantity_delta,
        balance_after=new_balance,
        reference_note=reference_note,
        created_by=actor_user,
    )

    AuditEvent.objects.create(
        actor_user=actor_user,
        tenant=tenant,
        event_type=f"INVENTORY_{transaction_type}",
        target_model="operations.Material",
        target_id=str(material.id),
        metadata={
            "sku": material.sku,
            "quantity_delta": str(quantity_delta),
            "balance_after": str(new_balance),
        },
    )
    return entry


@transaction.atomic
def convert_quotation_to_order_and_invoice(
    *,
    tenant: Tenant,
    quotation_id: str,
    artwork_file_name: str,
    actor_user,
) -> SalesOrder:
    """
    REQ-PRINT-02, REQ-PRINT-03, REQ-PRINT-05:
    Converts a Quotation into a SalesOrder, spawns a ProductionJob, and issues a CustomerInvoice.
    """
    try:
        quote = (
            Quotation.objects.select_for_update()
            .select_related("customer")
            .get(id=quotation_id, tenant=tenant)
        )
    except Quotation.DoesNotExist as exc:
        raise ValidationError("Quotation not found in this tenant.") from exc

    if quote.status == QuotationStatus.CONVERTED:
        raise ValidationError("Quotation has already been converted to a Sales Order.")

    quote.status = QuotationStatus.CONVERTED
    quote.save(update_fields=["status", "updated_at"])

    seq_num = SalesOrder.objects.filter(tenant=tenant).count() + 1
    order_number = f"SO-{seq_num:04d}"
    job_code = f"JOB-{seq_num:04d}"
    invoice_number = f"INV-{seq_num:04d}"

    order = SalesOrder.objects.create(
        tenant=tenant,
        customer=quote.customer,
        quotation=quote,
        order_number=order_number,
        title=quote.title,
        specification_summary=quote.specification_summary,
        quantity=quote.quantity,
        artwork_file_name=artwork_file_name or "pending_artwork.pdf",
        total_usd=quote.total_usd,
        total_khr=quote.total_khr,
        status=OrderStatus.CONFIRMED,
        created_by=actor_user,
    )

    ProductionJob.objects.create(
        tenant=tenant,
        sales_order=order,
        job_Code=job_code,
        stage=ProductionStage.PENDING,
        updated_by=actor_user,
    )

    CustomerInvoice.objects.create(
        tenant=tenant,
        sales_order=order,
        invoice_number=invoice_number,
        total_usd=order.total_usd,
        total_khr=order.total_khr,
        paid_usd=Decimal("0.00"),
        balance_due_usd=order.total_usd,
        status=InvoiceStatus.ISSUED,
    )

    AuditEvent.objects.create(
        actor_user=actor_user,
        tenant=tenant,
        event_type="QUOTATION_CONVERTED_TO_ORDER",
        target_model="operations.SalesOrder",
        target_id=str(order.id),
        metadata={"order_number": order_number, "total_usd": str(order.total_usd)},
    )
    return order


@transaction.atomic
def record_customer_invoice_payment(
    *,
    tenant: Tenant,
    invoice_id: str,
    amount_usd: Decimal,
    payment_method: str,
    reference_number: str,
    actor_user,
) -> CustomerPayment:
    """
    REQ-PRINT-05: Allocates deposit or final payment against a CustomerInvoice.
    """
    try:
        invoice = CustomerInvoice.objects.select_for_update().get(
            id=invoice_id,
            tenant=tenant,
        )
    except CustomerInvoice.DoesNotExist as exc:
        raise ValidationError("Invoice not found in this tenant.") from exc

    if invoice.status == InvoiceStatus.VOIDED:
        raise ValidationError("Cannot record payment on a voided invoice.")

    amount_usd = round_usd(amount_usd)
    if amount_usd <= Decimal("0.00"):
        raise ValidationError("Payment amount must be greater than zero.")
    if amount_usd > invoice.balance_due_usd:
        raise ValidationError(
            f"Payment amount (${amount_usd}) exceeds remaining balance due (${invoice.balance_due_usd})."
        )

    payment = CustomerPayment.objects.create(
        tenant=tenant,
        invoice=invoice,
        amount_usd=amount_usd,
        payment_method=payment_method,
        reference_number=reference_number,
        recorded_by=actor_user,
    )

    invoice.paid_usd = round_usd(invoice.paid_usd + amount_usd)
    invoice.balance_due_usd = round_usd(invoice.total_usd - invoice.paid_usd)
    invoice.status = (
        InvoiceStatus.PAID
        if invoice.balance_due_usd == Decimal("0.00")
        else InvoiceStatus.PARTIALLY_PAID
    )
    invoice.save(update_fields=["paid_usd", "balance_due_usd", "status", "updated_at"])

    AuditEvent.objects.create(
        actor_user=actor_user,
        tenant=tenant,
        event_type="INVOICE_PAYMENT_ALLOCATED",
        target_model="operations.CustomerInvoice",
        target_id=str(invoice.id),
        metadata={
            "invoice_number": invoice.invoice_number,
            "amount_usd": str(amount_usd),
            "balance_due_usd": str(invoice.balance_due_usd),
            "status": invoice.status,
        },
    )
    return payment
