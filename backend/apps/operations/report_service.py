import csv
import io
from decimal import Decimal
from typing import Any, Dict, List, Optional
from django.utils import timezone
from apps.operations.models import CustomerInvoice, InvoiceStatus


def generate_gdt_vat_sales_journal(
    tenant: Any,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> Dict[str, Any]:
    """
    REP-001: Commercial GDT (General Department of Taxation) VAT Sales Journal.
    Generates official monthly VAT sales report for Cambodian tax declarations.
    """
    now = timezone.now()
    target_year = int(year) if year else now.year
    target_month = int(month) if month else now.month

    invoices = (
        CustomerInvoice.objects.filter(
            tenant=tenant,
            created_at__year=target_year,
            created_at__month=target_month,
        )
        .select_related("sales_order__customer")
        .order_by("created_at", "invoice_number")
    )

    is_tax_registered = getattr(tenant, "is_tax_registered", True)
    rate = tenant.khr_exchange_rate or Decimal("4100.00")
    tax_rate = (tenant.tax_rate_percent or Decimal("10.00")) if is_tax_registered else Decimal("0.00")
    vat_multiplier = tax_rate / Decimal("100.00")

    total_sales_usd = Decimal("0.00")
    total_sales_khr = Decimal("0")
    total_vat_usd = Decimal("0.00")
    total_vat_khr = Decimal("0")
    total_taxable_usd = Decimal("0.00")
    total_taxable_khr = Decimal("0")

    rows: List[Dict[str, Any]] = []
    for idx, inv in enumerate(invoices, start=1):
        cust = inv.sales_order.customer
        grand_total_usd = inv.total_usd
        grand_total_khr = inv.total_khr

        # Calculate base taxable and VAT amount
        # Standard GDT: Grand Total = Taxable + VAT => Taxable = Grand / (1 + vat_rate)
        if vat_multiplier > Decimal("0.00"):
            taxable_usd = (grand_total_usd / (Decimal("1.00") + vat_multiplier)).quantize(Decimal("0.01"))
            vat_usd = (grand_total_usd - taxable_usd).quantize(Decimal("0.01"))
        else:
            taxable_usd = grand_total_usd
            vat_usd = Decimal("0.00")

        taxable_khr = (taxable_usd * rate).quantize(Decimal("1"))
        vat_khr = (vat_usd * rate).quantize(Decimal("1"))

        total_sales_usd += grand_total_usd
        total_sales_khr += grand_total_khr
        total_taxable_usd += taxable_usd
        total_taxable_khr += taxable_khr
        total_vat_usd += vat_usd
        total_vat_khr += vat_khr

        rows.append(
            {
                "line_no": idx,
                "invoice_id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "date": inv.created_at.strftime("%Y-%m-%d"),
                "customer_name": cust.name,
                "customer_phone": cust.phone,
                "customer_tin": "Consumer" if not cust.company_name else "VATTIN-REG",
                "taxable_amount_usd": str(taxable_usd),
                "taxable_amount_khr": str(taxable_khr),
                "vat_amount_usd": str(vat_usd),
                "vat_amount_khr": str(vat_khr),
                "total_amount_usd": str(grand_total_usd),
                "total_amount_khr": str(grand_total_khr),
                "status": inv.status,
            }
        )

    return {
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
        "is_tax_registered": is_tax_registered,
        "tax_id_number": getattr(tenant, "tax_id_number", ""),
        "report_period": f"{target_year:04d}-{target_month:02d}",
        "khr_exchange_rate": str(rate),
        "tax_rate_percent": str(tax_rate),
        "invoice_count": len(rows),
        "total_taxable_amount_usd": str(total_taxable_usd),
        "total_taxable_amount_khr": str(total_taxable_khr),
        "total_vat_amount_usd": str(total_vat_usd),
        "total_vat_amount_khr": str(total_vat_khr),
        "total_sales_amount_usd": str(total_sales_usd),
        "total_sales_amount_khr": str(total_sales_khr),
        "invoices": rows,
    }


def generate_vat_sales_journal_csv(journal: Dict[str, Any]) -> str:
    """
    Renders official UTF-8 CSV with BOM for Cambodian GDT sales journal export.
    """
    output = io.StringIO()
    # Write UTF-8 BOM so Excel opens Khmer text correctly
    output.write("\ufeff")

    writer = csv.writer(output)
    writer.writerow(["GDT VAT SALES JOURNAL / សៀវភៅកំណត់ហេតុលក់"])
    writer.writerow(["Taxpayer / ឈ្មោះសហគ្រាស", journal["tenant_name"]])
    writer.writerow([
        "Tax Regime / របបសារពើពន្ធ",
        "អ្នកជាប់ពន្ធរបបស្វ័យប្រកាស (VAT Registered)" if journal.get("is_tax_registered") else "អាជីវកម្មខ្នាតតូច/គ្រួសារ (Non-VAT Family Business)"
    ])
    if journal.get("tax_id_number"):
        writer.writerow(["Tax ID (TIN) / លេខអត្តសញ្ញាណកម្ម", journal["tax_id_number"]])
    writer.writerow(["Tax Period / ការិយបរិច្ឆេទ", journal["report_period"]])
    writer.writerow(["Exchange Rate / អត្រាប្តូរប្រាក់", f"1 USD = {journal['khr_exchange_rate']} KHR"])
    writer.writerow(["VAT Rate / អត្រាអាករ", f"{journal['tax_rate_percent']}%"])
    writer.writerow([])

    # Table Header
    writer.writerow(
        [
            "No.",
            "Invoice #",
            "Date",
            "Customer Name",
            "Phone",
            "TIN",
            "Taxable (USD)",
            "Taxable (KHR)",
            "VAT (USD)",
            "VAT (KHR)",
            "Total (USD)",
            "Total (KHR)",
            "Status",
        ]
    )

    for item in journal["invoices"]:
        writer.writerow(
            [
                item["line_no"],
                item["invoice_number"],
                item["date"],
                item["customer_name"],
                item["customer_phone"],
                item["customer_tin"],
                item["taxable_amount_usd"],
                item["taxable_amount_khr"],
                item["vat_amount_usd"],
                item["vat_amount_khr"],
                item["total_amount_usd"],
                item["total_amount_khr"],
                item["status"],
            ]
        )

    # Summary Row
    writer.writerow([])
    writer.writerow(
        [
            "TOTAL",
            f"{journal['invoice_count']} Invoices",
            "",
            "",
            "",
            "",
            journal["total_taxable_amount_usd"],
            journal["total_taxable_amount_khr"],
            journal["total_vat_amount_usd"],
            journal["total_vat_amount_khr"],
            journal["total_sales_amount_usd"],
            journal["total_sales_amount_khr"],
            "",
        ]
    )

    return output.getvalue()


def generate_daily_sales_report(
    tenant: Any,
    date_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    REP-002: Daily sales and register reconciliation summary.
    """
    from django.db.models import Sum, Count
    from apps.operations.models import CustomerPayment, SalesOrder, OrderStatus

    now = timezone.now()
    if date_str:
        try:
            target_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            target_date = now.date()
    else:
        target_date = now.date()

    rate = tenant.khr_exchange_rate or Decimal("4100.00")

    orders = SalesOrder.objects.filter(
        tenant=tenant,
        created_at__date=target_date,
    ).exclude(status=OrderStatus.CANCELED)

    invoices = CustomerInvoice.objects.filter(
        tenant=tenant,
        created_at__date=target_date,
    ).exclude(status=InvoiceStatus.VOIDED)

    payments = CustomerPayment.objects.filter(
        tenant=tenant,
        created_at__date=target_date,
    )

    total_invoiced_usd = invoices.aggregate(s=Sum("total_usd"))["s"] or Decimal("0.00")
    total_invoiced_khr = invoices.aggregate(s=Sum("total_khr"))["s"] or Decimal("0")

    total_collected_usd = payments.aggregate(s=Sum("amount_usd"))["s"] or Decimal("0.00")
    total_collected_khr = (total_collected_usd * rate).quantize(Decimal("1"))

    # Breakdown by payment method
    methods_data = (
        payments.values("payment_method")
        .annotate(count=Count("id"), total=Sum("amount_usd"))
        .order_by("-total")
    )
    methods_breakdown = [
        {
            "payment_method": m["payment_method"],
            "count": m["count"],
            "total_usd": str(m["total"]),
            "total_khr": str((m["total"] * rate).quantize(Decimal("1"))),
        }
        for m in methods_data
    ]

    return {
        "tenant_id": str(tenant.id),
        "report_date": target_date.strftime("%Y-%m-%d"),
        "khr_exchange_rate": str(rate),
        "orders_count": orders.count(),
        "invoices_count": invoices.count(),
        "total_invoiced_usd": str(total_invoiced_usd),
        "total_invoiced_khr": str(total_invoiced_khr),
        "payments_count": payments.count(),
        "total_collected_usd": str(total_collected_usd),
        "total_collected_khr": str(total_collected_khr),
        "payment_methods": methods_breakdown,
    }


def generate_inventory_alerts_report(tenant: Any) -> Dict[str, Any]:
    """
    REP-003: Inventory stock alerts and reorder warning list.
    """
    from django.db.models import F
    from apps.operations.models import Material

    low_stock_materials = Material.objects.filter(
        tenant=tenant,
        current_stock__lte=F("reorder_level"),
    ).order_by("current_stock")

    items = []
    total_estimated_reorder_usd = Decimal("0.00")
    for mat in low_stock_materials:
        deficit = max(Decimal("0.000"), mat.reorder_level - mat.current_stock)
        est_cost = (deficit * mat.unit_cost_usd).quantize(Decimal("0.01"))
        total_estimated_reorder_usd += est_cost
        items.append(
            {
                "material_id": str(mat.id),
                "sku": mat.sku,
                "name": mat.name,
                "unit": mat.unit,
                "current_stock": str(mat.current_stock),
                "reorder_level": str(mat.reorder_level),
                "deficit_quantity": str(deficit),
                "unit_cost_usd": str(mat.unit_cost_usd),
                "estimated_reorder_cost_usd": str(est_cost),
            }
        )

    return {
        "tenant_id": str(tenant.id),
        "alerts_count": len(items),
        "total_estimated_reorder_cost_usd": str(total_estimated_reorder_usd),
        "materials": items,
    }


def generate_customer_receivables_report(tenant: Any) -> Dict[str, Any]:
    """
    REP-004: Customer debt aging and outstanding receivables report.
    """
    from django.utils import timezone
    from apps.operations.models import CustomerInvoice, InvoiceStatus

    now = timezone.now()
    rate = tenant.khr_exchange_rate or Decimal("4100.00")

    unpaid_invoices = (
        CustomerInvoice.objects.filter(
            tenant=tenant,
            balance_due_usd__gt=Decimal("0.00"),
        )
        .exclude(status=InvoiceStatus.VOIDED)
        .select_related("sales_order__customer")
        .order_by("-created_at")
    )

    customers_map = {}
    total_receivables_usd = Decimal("0.00")
    aging_summary = {
        "days_0_30_usd": Decimal("0.00"),
        "days_31_60_usd": Decimal("0.00"),
        "days_over_60_usd": Decimal("0.00"),
    }

    for inv in unpaid_invoices:
        cust = inv.sales_order.customer
        cust_id = str(cust.id)
        bal = inv.balance_due_usd
        total_receivables_usd += bal

        age_days = (now.date() - inv.created_at.date()).days
        if age_days <= 30:
            aging_summary["days_0_30_usd"] += bal
        elif age_days <= 60:
            aging_summary["days_31_60_usd"] += bal
        else:
            aging_summary["days_over_60_usd"] += bal

        if cust_id not in customers_map:
            customers_map[cust_id] = {
                "customer_id": cust_id,
                "customer_name": cust.name,
                "customer_phone": cust.phone,
                "company_name": cust.company_name,
                "unpaid_invoices_count": 0,
                "total_balance_usd": Decimal("0.00"),
                "total_balance_khr": Decimal("0"),
            }
        customers_map[cust_id]["unpaid_invoices_count"] += 1
        customers_map[cust_id]["total_balance_usd"] += bal
        customers_map[cust_id]["total_balance_khr"] = (
            customers_map[cust_id]["total_balance_usd"] * rate
        ).quantize(Decimal("1"))

    customer_list = [
        {
            **v,
            "total_balance_usd": str(v["total_balance_usd"]),
            "total_balance_khr": str(v["total_balance_khr"]),
        }
        for v in customers_map.values()
    ]
    customer_list.sort(key=lambda x: Decimal(x["total_balance_usd"]), reverse=True)

    return {
        "tenant_id": str(tenant.id),
        "total_receivables_usd": str(total_receivables_usd),
        "total_receivables_khr": str((total_receivables_usd * rate).quantize(Decimal("1"))),
        "customers_count": len(customer_list),
        "aging_breakdown": {
            k: str(v) for k, v in aging_summary.items()
        },
        "debtors": customer_list,
    }


def generate_production_queue_report(tenant: Any) -> Dict[str, Any]:
    """
    REP-005: Real-time production queue grouped by stage.
    """
    from apps.operations.models import ProductionJob, ProductionStage

    jobs = (
        ProductionJob.objects.filter(tenant=tenant)
        .exclude(stage=ProductionStage.COMPLETED)
        .select_related("sales_order__customer")
        .order_by("created_at")
    )

    stage_groups = {s.value: [] for s in ProductionStage if s != ProductionStage.COMPLETED}
    for job in jobs:
        stage_groups[job.stage].append(
            {
                "job_id": str(job.id),
                "job_code": job.job_Code,
                "stage": job.stage,
                "order_number": job.sales_order.order_number,
                "customer_name": job.sales_order.customer.name,
                "target_delivery_date": (
                    job.sales_order.target_delivery_date.strftime("%Y-%m-%d")
                    if job.sales_order.target_delivery_date
                    else None
                ),
                "created_at": job.created_at.isoformat(),
            }
        )

    return {
        "tenant_id": str(tenant.id),
        "active_jobs_count": jobs.count(),
        "stages": {
            stage: {"count": len(items), "jobs": items}
            for stage, items in stage_groups.items()
        },
    }
