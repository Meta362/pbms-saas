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
