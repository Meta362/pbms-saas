from decimal import Decimal
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedUUIDModel
from apps.tenants.models import Tenant


class MaterialUnit(models.TextChoices):
    SHEET = "SHEET", "Sheet (សន្លឹក)"
    ROLL = "ROLL", "Roll (ដុំ/រមូរ)"
    SQM = "SQM", "Square Meter (ម៉ែត្រការ៉េ)"
    LITER = "LITER", "Liter (លីត្រ)"
    PIECE = "PIECE", "Piece (គ្រាប់/ដើម)"


class InventoryTransactionType(models.TextChoices):
    STOCK_IN = "STOCK_IN", "Stock In (នាំចូល)"
    CONSUMPTION = "CONSUMPTION", "Production Consumption (ប្រើប្រាស់ក្នុងផលិតកម្ម)"
    WASTE = "WASTE", "Production Waste (ខូចខាត)"
    OFFCUT_RETURN = "OFFCUT_RETURN", "Reusable Offcut Return (សំណល់ប្រើឡើងវិញបាន)"
    ADJUSTMENT = "ADJUSTMENT", "Manual Audited Adjustment (កែតម្រូវស្តុក)"


class QuotationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    APPROVED = "APPROVED", "Customer Approved"
    CONVERTED = "CONVERTED", "Converted to Sales Order"
    REJECTED = "REJECTED", "Rejected"


class OrderStatus(models.TextChoices):
    CONFIRMED = "CONFIRMED", "Confirmed"
    IN_PRODUCTION = "IN_PRODUCTION", "In Production"
    READY_FOR_DELIVERY = "READY_FOR_DELIVERY", "Ready for Delivery"
    COMPLETED = "COMPLETED", "Delivered & Completed"
    CANCELED = "CANCELED", "Canceled"


class ProductionStage(models.TextChoices):
    PENDING = "PENDING", "Pending Queue"
    PRE_PRESS = "PRE_PRESS", "Pre-Press & Artwork Check"
    PRINTING = "PRINTING", "Printing on Press"
    FINISHING = "FINISHING", "Cutting, Lamination & Binding"
    QC = "QC", "Quality Control"
    COMPLETED = "COMPLETED", "Production Completed"


class InvoiceStatus(models.TextChoices):
    ISSUED = "ISSUED", "Issued (Unpaid)"
    PARTIALLY_PAID = "PARTIALLY_PAID", "Partially Paid (Deposit)"
    PAID = "PAID", "Paid in Full"
    VOIDED = "VOIDED", "Voided"


class Customer(TimeStampedUUIDModel):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="customers",
    )
    name = models.CharField(max_length=150)
    company_name = models.CharField(max_length=150, blank=True, default="")
    phone = models.CharField(max_length=32)
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")

    class Meta:
        db_table = "operations_customer"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.tenant.slug})"


class Material(TimeStampedUUIDModel):
    """
    REQ-PRINT-04: Material catalog item. `current_stock` is strictly managed by
    atomic InventoryTransaction ledger operations and protected by DB CheckConstraint.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="materials",
    )
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=150)
    unit = models.CharField(
        max_length=16,
        choices=MaterialUnit.choices,
        default=MaterialUnit.SHEET,
    )
    current_stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("0.000"),
    )
    reorder_level = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("50.000"),
    )
    unit_cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        db_table = "operations_material"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sku"],
                name="uq_material_tenant_sku",
            ),
            models.CheckConstraint(
                condition=models.Q(current_stock__gte=Decimal("0.000")),
                name="chk_material_stock_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku} - {self.name} ({self.current_stock} {self.unit})"


class InventoryTransaction(TimeStampedUUIDModel):
    """
    REQ-PRINT-04: Immutable inventory ledger record.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="inventory_transactions",
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.RESTRICT,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=24,
        choices=InventoryTransactionType.choices,
    )
    quantity_delta = models.DecimalField(max_digits=12, decimal_places=3)
    balance_after = models.DecimalField(max_digits=12, decimal_places=3)
    reference_note = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="inventory_transactions",
    )

    class Meta:
        db_table = "operations_inventorytransaction"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "material", "-created_at"])]


class Quotation(TimeStampedUUIDModel):
    """
    REQ-PRINT-01 & REQ-PRINT-02: Auditable printing quotation with deterministic pricing.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="quotations",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.RESTRICT,
        related_name="quotations",
    )
    quote_number = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    specification_summary = models.TextField(blank=True, default="")
    quantity = models.PositiveIntegerField(default=1)
    setup_fee_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    unit_price_usd = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"))
    finishing_fee_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    subtotal_usd = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount_usd = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    total_usd = models.DecimalField(max_digits=14, decimal_places=2)
    total_khr = models.DecimalField(max_digits=16, decimal_places=0)
    status = models.CharField(
        max_length=20,
        choices=QuotationStatus.choices,
        default=QuotationStatus.DRAFT,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_quotations",
    )

    class Meta:
        db_table = "operations_quotation"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "quote_number"],
                name="uq_tenant_quote_number",
            )
        ]

class QuotationItem(TimeStampedUUIDModel):
    """
    DOM-001 & docs/DATABASE.md Section 2.4:
    Individual itemized line item belonging to a Quotation.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="quotation_items",
    )
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="items",
    )
    item_title = models.CharField(max_length=200)
    specification_summary = models.TextField(blank=True, default="")
    quantity = models.PositiveIntegerField(default=1)
    setup_fee_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    unit_price_usd = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"))
    finishing_fee_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    subtotal_usd = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        db_table = "operations_quotationitem"
        ordering = ["created_at"]



class SalesOrder(TimeStampedUUIDModel):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="sales_orders",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.RESTRICT,
        related_name="sales_orders",
    )
    quotation = models.OneToOneField(
        Quotation,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="sales_order",
    )
    order_number = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    specification_summary = models.TextField(blank=True, default="")
    quantity = models.PositiveIntegerField(default=1)
    artwork_file_name = models.CharField(max_length=255, blank=True, default="")
    total_usd = models.DecimalField(max_digits=14, decimal_places=2)
    total_khr = models.DecimalField(max_digits=16, decimal_places=0)
    status = models.CharField(
        max_length=24,
        choices=OrderStatus.choices,
        default=OrderStatus.CONFIRMED,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_sales_orders",
    )

    class Meta:
        db_table = "operations_salesorder"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "order_number"],
                name="uq_tenant_order_number",
            )
        ]

class SalesOrderItem(TimeStampedUUIDModel):
    """
    DOM-001 & docs/DATABASE.md Section 2.4:
    Individual itemized line item belonging to a confirmed SalesOrder.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="sales_order_items",
    )
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    quotation_item = models.ForeignKey(
        QuotationItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_order_items",
    )
    item_title = models.CharField(max_length=200)
    specification_summary = models.TextField(blank=True, default="")
    quantity = models.PositiveIntegerField(default=1)
    setup_fee_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    unit_price_usd = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000"))
    finishing_fee_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    subtotal_usd = models.DecimalField(max_digits=14, decimal_places=2)
    artwork_file_name = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "operations_salesorderitem"
        ordering = ["created_at"]



class ProductionJob(TimeStampedUUIDModel):
    """
    REQ-PRINT-03: Tracks printing production workflow stages and responsible actors.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="production_jobs",
    )
    sales_order = models.OneToOneField(
        SalesOrder,
        on_delete=models.RESTRICT,
        related_name="production_job",
    )
    job_Code = models.CharField(max_length=40)
    stage = models.CharField(
        max_length=20,
        choices=ProductionStage.choices,
        default=ProductionStage.PENDING,
        db_index=True,
    )
    operator_notes = models.TextField(blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="updated_production_jobs",
    )

    class Meta:
        db_table = "operations_productionjob"
        ordering = ["-created_at"]


class CustomerInvoice(TimeStampedUUIDModel):
    """
    REQ-PRINT-05: Financial invoice and payment allocation tracking.
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="invoices",
    )
    sales_order = models.OneToOneField(
        SalesOrder,
        on_delete=models.RESTRICT,
        related_name="invoice",
    )
    invoice_number = models.CharField(max_length=40)
    total_usd = models.DecimalField(max_digits=14, decimal_places=2)
    total_khr = models.DecimalField(max_digits=16, decimal_places=0)
    paid_usd = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    balance_due_usd = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.ISSUED,
        db_index=True,
    )

    class Meta:
        db_table = "operations_customerinvoice"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "invoice_number"],
                name="uq_tenant_invoice_number",
            ),
            models.CheckConstraint(
                condition=models.Q(balance_due_usd__gte=Decimal("0.00")),
                name="chk_invoice_balance_non_negative",
            ),
        ]


class CustomerPayment(TimeStampedUUIDModel):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="customer_payments",
    )
    invoice = models.ForeignKey(
        CustomerInvoice,
        on_delete=models.RESTRICT,
        related_name="payments",
    )
    amount_usd = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=32, default="KHQR_ABA")
    reference_number = models.CharField(max_length=100, blank=True, default="")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="recorded_customer_payments",
    )

    class Meta:
        db_table = "operations_customerpayment"
        ordering = ["-created_at"]
