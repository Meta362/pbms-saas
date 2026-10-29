from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.models import AuditEvent
from apps.operations.models import (
    Customer,
    CustomerInvoice,
    InventoryTransaction,
    InventoryTransactionType,
    Material,
    OrderStatus,
    ProductionJob,
    ProductionStage,
    Quotation,
    SalesOrder,
)
from apps.operations.serializers import (
    CustomerInvoiceSerializer,
    CustomerSerializer,
    InventoryMovementCreateSerializer,
    InventoryTransactionSerializer,
    InvoicePaymentCreateSerializer,
    MaterialSerializer,
    ProductionStageUpdateSerializer,
    QuotationCreateSerializer,
    QuotationSerializer,
    SalesOrderSerializer,
)
from apps.operations.services import (
    calculate_quotation_totals,
    convert_quotation_to_order_and_invoice,
    record_customer_invoice_payment,
    record_inventory_movement,
    round_usd,
)
from apps.tenants.models import TenantRole
from apps.tenants.permissions import HasActiveTenantMembership


class TenantDashboardSummaryAPIView(APIView):
    """Frontend B: Operational summary metrics scoped strictly to `request.tenant`."""

    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.SALES_STAFF,
            TenantRole.FINANCE_STAFF,
            TenantRole.INVENTORY_STAFF,
            TenantRole.PRODUCTION_STAFF,
        },
    }

    def get(self, request: Request) -> Response:
        tenant = request.tenant
        customers_count = Customer.objects.filter(tenant=tenant).count()
        quotations_count = Quotation.objects.filter(tenant=tenant).count()
        orders_count = SalesOrder.objects.filter(tenant=tenant).count()
        active_jobs_count = (
            ProductionJob.objects.filter(tenant=tenant)
            .exclude(stage=ProductionStage.COMPLETED)
            .count()
        )
        total_invoiced_usd = round_usd(
            CustomerInvoice.objects.filter(tenant=tenant).aggregate(s=Sum("total_usd"))["s"]
            or Decimal("0.00")
        )
        total_collected_usd = round_usd(
            CustomerInvoice.objects.filter(tenant=tenant).aggregate(s=Sum("paid_usd"))["s"]
            or Decimal("0.00")
        )
        outstanding_usd = round_usd(
            CustomerInvoice.objects.filter(tenant=tenant).aggregate(s=Sum("balance_due_usd"))["s"]
            or Decimal("0.00")
        )

        return Response(
            {
                "tenant_name": tenant.name,
                "khr_exchange_rate": str(tenant.khr_exchange_rate),
                "metrics": {
                    "customers_count": customers_count,
                    "quotations_count": quotations_count,
                    "orders_count": orders_count,
                    "active_jobs_count": active_jobs_count,
                    "total_invoiced_usd": str(total_invoiced_usd),
                    "total_collected_usd": str(total_collected_usd),
                    "outstanding_balance_usd": str(outstanding_usd),
                },
            }
        )


class CustomerListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.SALES_STAFF,
            TenantRole.FINANCE_STAFF,
            TenantRole.DESIGNER,
            TenantRole.PRODUCTION_STAFF,
        },
        "POST": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.SALES_STAFF,
        },
    }

    def get(self, request: Request) -> Response:
        customers = Customer.objects.filter(tenant=request.tenant)
        return Response(CustomerSerializer(customers, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = CustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save(tenant=request.tenant)
        return Response(CustomerSerializer(customer).data, status=status.HTTP_201_CREATED)


class MaterialListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.INVENTORY_STAFF,
            TenantRole.PRODUCTION_STAFF,
            TenantRole.SALES_STAFF,
        },
        "POST": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.INVENTORY_STAFF,
        },
    }

    def get(self, request: Request) -> Response:
        materials = Material.objects.filter(tenant=request.tenant)
        return Response(MaterialSerializer(materials, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = MaterialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        material = serializer.save(tenant=request.tenant)
        return Response(MaterialSerializer(material).data, status=status.HTTP_201_CREATED)


class InventoryMovementListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.INVENTORY_STAFF,
            TenantRole.PRODUCTION_STAFF,
        },
        "POST": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.INVENTORY_STAFF,
            TenantRole.PRODUCTION_STAFF,
        },
    }

    def get(self, request: Request) -> Response:
        txns = InventoryTransaction.objects.select_related("material").filter(
            tenant=request.tenant
        )[:50]
        return Response(InventoryTransactionSerializer(txns, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = InventoryMovementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        role = request.tenant_membership.role
        tx_type = data["transaction_type"]
        qty_delta = data["quantity_delta"]

        if role == TenantRole.PRODUCTION_STAFF and tx_type not in (
            InventoryTransactionType.CONSUMPTION,
            InventoryTransactionType.WASTE,
            InventoryTransactionType.OFFCUT_RETURN,
        ):
            raise PermissionDenied(
                "Production staff may only log material consumption, waste, or offcut returns."
            )

        if (
            role == TenantRole.INVENTORY_STAFF
            and tx_type == InventoryTransactionType.ADJUSTMENT
            and qty_delta < Decimal("0.000")
        ):
            raise PermissionDenied(
                "Manual negative stock adjustments require TENANT_OWNER or TENANT_MANAGER approval."
            )

        entry = record_inventory_movement(
            tenant=request.tenant,
            material_id=str(data["material_id"]),
            transaction_type=tx_type,
            quantity_delta=qty_delta,
            reference_note=data["reference_note"],
            actor_user=request.user,
        )
        return Response(
            InventoryTransactionSerializer(entry).data,
            status=status.HTTP_201_CREATED,
        )


class QuotationListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.SALES_STAFF,
            TenantRole.FINANCE_STAFF,
        },
        "POST": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.SALES_STAFF,
        },
    }

    def get(self, request: Request) -> Response:
        quotes = Quotation.objects.select_related("customer").filter(tenant=request.tenant)
        return Response(QuotationSerializer(quotes, many=True).data)

    @transaction.atomic
    def post(self, request: Request) -> Response:
        serializer = QuotationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer = get_object_or_404(
            Customer,
            id=data["customer_id"],
            tenant=request.tenant,
        )
        totals = calculate_quotation_totals(
            tenant=request.tenant,
            quantity=data["quantity"],
            setup_fee_usd=data["setup_fee_usd"],
            unit_price_usd=data["unit_price_usd"],
            finishing_fee_usd=data["finishing_fee_usd"],
            discount_usd=data["discount_usd"],
        )

        seq = Quotation.objects.filter(tenant=request.tenant).count() + 1
        quote = Quotation.objects.create(
            tenant=request.tenant,
            customer=customer,
            quote_number=f"QT-{seq:04d}",
            title=data["title"],
            specification_summary=data["specification_summary"],
            quantity=data["quantity"],
            setup_fee_usd=data["setup_fee_usd"],
            unit_price_usd=data["unit_price_usd"],
            finishing_fee_usd=data["finishing_fee_usd"],
            discount_usd=data["discount_usd"],
            subtotal_usd=totals["subtotal_usd"],
            tax_amount_usd=totals["tax_amount_usd"],
            total_usd=totals["total_usd"],
            total_khr=totals["total_khr"],
            created_by=request.user,
        )
        return Response(QuotationSerializer(quote).data, status=status.HTTP_201_CREATED)


class QuotationConvertAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "POST": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.SALES_STAFF,
        },
    }

    def post(self, request: Request, quotation_id: str) -> Response:
        artwork_file_name = str(request.data.get("artwork_file_name", "artwork_print_ready.pdf"))
        order = convert_quotation_to_order_and_invoice(
            tenant=request.tenant,
            quotation_id=quotation_id,
            artwork_file_name=artwork_file_name,
            actor_user=request.user,
        )
        return Response(SalesOrderSerializer(order).data, status=status.HTTP_201_CREATED)


class SalesOrderListAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.SALES_STAFF,
            TenantRole.DESIGNER,
            TenantRole.PRODUCTION_STAFF,
            TenantRole.FINANCE_STAFF,
        },
    }

    def get(self, request: Request) -> Response:
        orders = SalesOrder.objects.select_related(
            "customer", "production_job", "invoice"
        ).filter(tenant=request.tenant)
        return Response(SalesOrderSerializer(orders, many=True).data)


class ProductionJobStageUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "POST": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.DESIGNER,
            TenantRole.PRODUCTION_STAFF,
        },
    }

    @transaction.atomic
    def post(self, request: Request, job_id: str) -> Response:
        serializer = ProductionStageUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job = get_object_or_404(
            ProductionJob.objects.select_for_update().select_related("sales_order"),
            id=job_id,
            tenant=request.tenant,
        )
        new_stage = serializer.validated_data["stage"]
        role = request.tenant_membership.role

        if role == TenantRole.DESIGNER:
            if job.stage != ProductionStage.PENDING or new_stage != ProductionStage.PRE_PRESS:
                raise PermissionDenied(
                    "Designers are only permitted to transition jobs from PENDING to PRE_PRESS."
                )
        elif role == TenantRole.PRODUCTION_STAFF:
            if new_stage == ProductionStage.PENDING:
                raise PermissionDenied(
                    "Production staff cannot revert a job stage to PENDING."
                )

        job.stage = new_stage
        job.operator_notes = serializer.validated_data["operator_notes"]
        job.updated_by = request.user
        job.save()

        order = job.sales_order
        if new_stage == ProductionStage.COMPLETED:
            order.status = OrderStatus.READY_FOR_DELIVERY
        else:
            order.status = OrderStatus.IN_PRODUCTION
        order.save(update_fields=["status", "updated_at"])

        AuditEvent.objects.create(
            actor_user=request.user,
            tenant=request.tenant,
            event_type="PRODUCTION_JOB_STAGE_UPDATED",
            target_model="operations.ProductionJob",
            target_id=str(job.id),
            metadata={"job_code": job.job_Code, "new_stage": new_stage},
        )
        return Response(
            {
                "job_id": str(job.id),
                "job_code": job.job_Code,
                "stage": job.stage,
                "order_status": order.status,
            }
        )


class CustomerInvoiceListAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "GET": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.FINANCE_STAFF,
            TenantRole.SALES_STAFF,
        },
    }

    def get(self, request: Request) -> Response:
        invoices = CustomerInvoice.objects.select_related(
            "sales_order__customer"
        ).filter(tenant=request.tenant)
        return Response(CustomerInvoiceSerializer(invoices, many=True).data)


class CustomerInvoicePaymentAPIView(APIView):
    permission_classes = [IsAuthenticated, HasActiveTenantMembership]
    allowed_tenant_roles_by_method = {
        "POST": {
            TenantRole.TENANT_OWNER,
            TenantRole.TENANT_MANAGER,
            TenantRole.FINANCE_STAFF,
        },
    }

    def post(self, request: Request, invoice_id: str) -> Response:
        serializer = InvoicePaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment = record_customer_invoice_payment(
            tenant=request.tenant,
            invoice_id=invoice_id,
            amount_usd=data["amount_usd"],
            payment_method=data["payment_method"],
            reference_number=data["reference_number"],
            actor_user=request.user,
        )
        invoice = payment.invoice
        return Response(
            CustomerInvoiceSerializer(invoice).data,
            status=status.HTTP_200_OK,
        )
