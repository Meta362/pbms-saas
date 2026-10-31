from decimal import Decimal
from rest_framework import serializers
from apps.operations.models import (
    Customer,
    CustomerInvoice,
    InventoryTransaction,
    InventoryTransactionType,
    Material,
    ProductionJob,
    ProductionStage,
    Quotation,
    QuotationItem,
    SalesOrder,
    SalesOrderItem,
)


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "name", "company_name", "phone", "email", "address", "created_at"]
        read_only_fields = ["id", "created_at"]


class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = [
            "id",
            "sku",
            "name",
            "unit",
            "current_stock",
            "reorder_level",
            "unit_cost_usd",
            "created_at",
        ]
        read_only_fields = ["id", "current_stock", "created_at"]


class InventoryMovementCreateSerializer(serializers.Serializer):
    material_id = serializers.UUIDField()
    transaction_type = serializers.ChoiceField(choices=InventoryTransactionType.choices)
    quantity_delta = serializers.DecimalField(max_digits=12, decimal_places=3)
    reference_note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class InventoryTransactionSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source="material.name", read_only=True)
    material_sku = serializers.CharField(source="material.sku", read_only=True)

    class Meta:
        model = InventoryTransaction
        fields = [
            "id",
            "material",
            "material_sku",
            "material_name",
            "transaction_type",
            "quantity_delta",
            "balance_after",
            "reference_note",
            "created_at",
        ]


class QuotationItemCreateSerializer(serializers.Serializer):
    item_title = serializers.CharField(max_length=200)
    specification_summary = serializers.CharField(required=False, allow_blank=True, default="")
    quantity = serializers.IntegerField(min_value=1)
    unit_price_usd = serializers.DecimalField(
        max_digits=12, decimal_places=4, min_value=Decimal("0.00")
    )
    setup_fee_usd = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    finishing_fee_usd = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )


class QuotationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationItem
        fields = [
            "id",
            "item_title",
            "specification_summary",
            "quantity",
            "setup_fee_usd",
            "unit_price_usd",
            "finishing_fee_usd",
            "subtotal_usd",
        ]


class SalesOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrderItem
        fields = [
            "id",
            "item_title",
            "specification_summary",
            "quantity",
            "setup_fee_usd",
            "unit_price_usd",
            "finishing_fee_usd",
            "subtotal_usd",
            "artwork_file_name",
        ]


class QuotationCreateSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    title = serializers.CharField(max_length=200)
    specification_summary = serializers.CharField(required=False, allow_blank=True, default="")
    quantity = serializers.IntegerField(min_value=1, required=False, default=1)
    setup_fee_usd = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    unit_price_usd = serializers.DecimalField(
        max_digits=12, decimal_places=4, min_value=Decimal("0.00"), default=Decimal("0.0000")
    )
    finishing_fee_usd = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    discount_usd = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.00"), default=Decimal("0.00")
    )
    items = QuotationItemCreateSerializer(many=True, required=False, default=list)


class QuotationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    items = QuotationItemSerializer(many=True, read_only=True)

    class Meta:
        model = Quotation
        fields = [
            "id",
            "quote_number",
            "customer",
            "customer_name",
            "title",
            "specification_summary",
            "quantity",
            "setup_fee_usd",
            "unit_price_usd",
            "finishing_fee_usd",
            "discount_usd",
            "subtotal_usd",
            "tax_amount_usd",
            "total_usd",
            "total_khr",
            "status",
            "items",
            "created_at",
        ]


class SalesOrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    production_stage = serializers.CharField(source="production_job.stage", read_only=True)
    production_job_id = serializers.UUIDField(source="production_job.id", read_only=True)
    invoice_id = serializers.UUIDField(source="invoice.id", read_only=True)
    invoice_status = serializers.CharField(source="invoice.status", read_only=True)
    balance_due_usd = serializers.DecimalField(
        source="invoice.balance_due_usd", max_digits=14, decimal_places=2, read_only=True
    )

    items = SalesOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = SalesOrder
        fields = [
            "id",
            "order_number",
            "customer",
            "customer_name",
            "title",
            "specification_summary",
            "quantity",
            "artwork_file_name",
            "total_usd",
            "total_khr",
            "status",
            "production_job_id",
            "production_stage",
            "invoice_id",
            "invoice_status",
            "balance_due_usd",
            "items",
            "created_at",
        ]


class ProductionStageUpdateSerializer(serializers.Serializer):
    stage = serializers.ChoiceField(choices=ProductionStage.choices)
    operator_notes = serializers.CharField(required=False, allow_blank=True, default="")


class CustomerInvoiceSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="sales_order.order_number", read_only=True)
    customer_name = serializers.CharField(source="sales_order.customer.name", read_only=True)

    class Meta:
        model = CustomerInvoice
        fields = [
            "id",
            "invoice_number",
            "order_number",
            "customer_name",
            "total_usd",
            "total_khr",
            "paid_usd",
            "balance_due_usd",
            "status",
            "created_at",
        ]


class InvoicePaymentCreateSerializer(serializers.Serializer):
    amount_usd = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )
    payment_method = serializers.CharField(max_length=32, default="KHQR_ABA")
    reference_number = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
