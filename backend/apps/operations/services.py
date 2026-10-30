from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone
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
from apps.subscriptions.models import SubscriptionStatus, TenantSubscription
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
    REQ-PRINT-02, REQ-PRINT-03, REQ-PRINT-05, REQ-SAAS-02:
    Converts a Quotation into a SalesOrder, spawns a ProductionJob, and issues a CustomerInvoice.
    Enforces Plan.max_orders_per_month atomically under a tenant row lock.
    """
    locked_tenant = Tenant.objects.select_for_update().get(id=tenant.id)
    subscription = (
        TenantSubscription.objects.select_for_update()
        .select_related("plan")
        .filter(tenant=locked_tenant)
        .first()
    )
    if subscription is None or subscription.status not in (
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.TRIALING,
    ):
        raise ValidationError(
            "Tenant does not have an active subscription required to create orders."
        )
    now = timezone.now()
    if (
        subscription.current_period_end is None
        or subscription.current_period_end <= now
    ):
        raise ValidationError("Tenant subscription billing period has expired.")

    try:
        quote = (
            Quotation.objects.select_for_update()
            .select_related("customer")
            .get(id=quotation_id, tenant=locked_tenant)
        )
    except Quotation.DoesNotExist as exc:
        raise ValidationError("Quotation not found in this tenant.") from exc

    if quote.status == QuotationStatus.CONVERTED:
        raise ValidationError("Quotation has already been converted to a Sales Order.")

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)

    monthly_orders_count = (
        SalesOrder.objects.filter(
            tenant=locked_tenant,
            created_at__gte=month_start,
            created_at__lt=next_month_start,
        )
        .exclude(status=OrderStatus.CANCELED)
        .count()
    )
    max_orders = subscription.plan.max_orders_per_month
    if monthly_orders_count >= max_orders:
        raise ValidationError(
            f"Monthly order limit reached ({max_orders} orders per month for plan '{subscription.plan.code}')."
        )

    quote.status = QuotationStatus.CONVERTED
    quote.save(update_fields=["status", "updated_at"])

    seq_num = SalesOrder.objects.filter(tenant=locked_tenant).count() + 1
    order_number = f"SO-{seq_num:04d}"
    job_code = f"JOB-{seq_num:04d}"
    invoice_number = f"INV-{seq_num:04d}"

    order = SalesOrder.objects.create(
        tenant=locked_tenant,
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
        tenant=locked_tenant,
        sales_order=order,
        job_Code=job_code,
        stage=ProductionStage.PENDING,
        updated_by=actor_user,
    )

    CustomerInvoice.objects.create(
        tenant=locked_tenant,
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
        tenant=locked_tenant,
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
