import hashlib
from decimal import Decimal
from typing import Any, Dict, Optional
from urllib.parse import quote_plus
from qrcodegen import QrCode


def compute_emv_crc16(data: str) -> str:
    """
    Computes standard EMVCo CRC-16 (CCITT-FALSE) checksum.
    Polynomial: 0x1021, Seed: 0xFFFF, Final XOR: 0x0000.
    Calculates over the ASCII/UTF-8 representation of the string.
    """
    crc = 0xFFFF
    for char in data:
        crc ^= (ord(char) << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def format_tlv(tag: str, value: str) -> str:
    """
    Formats a Tag-Length-Value object per EMVCo QR Code Specification.
    Tag: 2 digits
    Length: 2 digits zero-padded (length of value)
    Value: string
    """
    length = f"{len(value):02d}"
    return f"{tag}{length}{value}"


def generate_khqr_payload(
    bakong_account_id: str,
    merchant_name: str,
    merchant_city: str,
    amount: Decimal,
    currency: str = "USD",
    bill_number: str = "",
    store_label: str = "PBMS",
    terminal_label: str = "CASHIER-01",
) -> Dict[str, str]:
    """
    Generates standard NBC Bakong KHQR dynamic payload conforming to EMVCo MPM specification.
    """
    # 1. Payload Format Indicator (Tag 00 = "01")
    p00 = format_tlv("00", "01")

    # 2. Point of Initiation Method (Tag 01 = "12" for Dynamic transaction QR)
    p01 = format_tlv("01", "12")

    # 3. Merchant Account Information (Tag 29 for Individual / Solo Merchant)
    # Subtag 00: Account ID / Proxy
    sub00 = format_tlv("00", bakong_account_id)
    p29 = format_tlv("29", sub00)

    # 4. Merchant Category Code (Tag 52 = "0000" or "5999")
    p52 = format_tlv("52", "0000")

    # 5. Transaction Currency (Tag 53: 840 for USD, 116 for KHR)
    currency_code = "840" if currency.upper() == "USD" else "116"
    p53 = format_tlv("53", currency_code)

    # 6. Transaction Amount (Tag 54)
    if currency.upper() == "USD":
        formatted_amount = f"{Decimal(amount):.2f}"
    else:
        formatted_amount = str(int(Decimal(amount)))
    p54 = format_tlv("54", formatted_amount)

    # 7. Country Code (Tag 58 = "KH")
    p58 = format_tlv("58", "KH")

    # 8. Merchant Name (Tag 59, max 25 chars)
    sanitized_name = merchant_name[:25] or "PBMS Merchant"
    p59 = format_tlv("59", sanitized_name)

    # 9. Merchant City (Tag 60, max 15 chars)
    sanitized_city = merchant_city[:15] or "Phnom Penh"
    p60 = format_tlv("60", sanitized_city)

    # 10. Additional Data Field Template (Tag 62)
    # Subtag 01: Bill / Reference Number
    # Subtag 03: Store Label
    # Subtag 07: Terminal Label
    sub_data = ""
    if bill_number:
        sub_data += format_tlv("01", bill_number[:25])
    if store_label:
        sub_data += format_tlv("03", store_label[:20])
    if terminal_label:
        sub_data += format_tlv("07", terminal_label[:20])
    p62 = format_tlv("62", sub_data) if sub_data else ""

    # Assemble payload without CRC tag (Tag 63 length is 04)
    raw_partial = f"{p00}{p01}{p29}{p52}{p53}{p54}{p58}{p59}{p60}{p62}6304"

    # Compute CRC16
    crc_hex = compute_emv_crc16(raw_partial)
    full_payload = f"{raw_partial}{crc_hex}"

    # MD5 hash for Bakong Open API status lookup
    md5_hash = hashlib.md5(full_payload.encode("utf-8")).hexdigest()

    # Mobile banking deep link
    deep_link = f"https://bakong.nbc.org.kh/pay?qr={quote_plus(full_payload)}"

    return {
        "currency": currency.upper(),
        "amount": formatted_amount,
        "qr_payload": full_payload,
        "md5_hash": md5_hash,
        "deep_link": deep_link,
    }


def generate_khqr_svg(qr_payload: str, size: int = 300, border: int = 4) -> str:
    """
    Renders pure vector SVG for any QR code string using Project Nayuki's qrcodegen.
    """
    qr = QrCode.encode_text(qr_payload, QrCode.Ecc.MEDIUM)
    grid_size = qr.get_size()
    total_modules = grid_size + (border * 2)

    path_commands = []
    for y in range(grid_size):
        for x in range(grid_size):
            if qr.get_module(x, y):
                path_commands.append(f"M{x + border},{y + border}h1v1h-1z")

    path_data = " ".join(path_commands)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_modules} {total_modules}" '
        f'width="{size}" height="{size}" shape-rendering="crispEdges">\n'
        f'  <rect width="100%" height="100%" fill="#FFFFFF" rx="4"/>\n'
        f'  <path d="{path_data}" fill="#0F172A"/>\n'
        f'</svg>'
    )
    return svg


def get_invoice_khqr_bundle(invoice: Any) -> Dict[str, Any]:
    """
    Builds complete dual-currency NBC Bakong KHQR bundle for a given CustomerInvoice.
    """
    tenant = invoice.tenant
    rate = tenant.khr_exchange_rate or Decimal("4100.00")
    usd_due = invoice.balance_due_usd
    khr_due = (usd_due * rate).quantize(Decimal("1"))

    # Determine Bakong account ID (use tenant phone / account or default)
    bakong_id = f"{tenant.slug}@pbms"
    if tenant.phone:
        clean_phone = "".join(filter(str.isdigit, tenant.phone))
        if clean_phone:
            bakong_id = f"{clean_phone}@aclb"

    # USD Payload
    usd_pkg = generate_khqr_payload(
        bakong_account_id=bakong_id,
        merchant_name=tenant.name,
        merchant_city="Phnom Penh",
        amount=usd_due,
        currency="USD",
        bill_number=invoice.invoice_number,
        store_label="PBMS",
        terminal_label="POS-1",
    )
    usd_pkg["qr_svg"] = generate_khqr_svg(usd_pkg["qr_payload"], size=280)

    # KHR Payload
    khr_pkg = generate_khqr_payload(
        bakong_account_id=bakong_id,
        merchant_name=tenant.name,
        merchant_city="Phnom Penh",
        amount=khr_due,
        currency="KHR",
        bill_number=invoice.invoice_number,
        store_label="PBMS",
        terminal_label="POS-1",
    )
    khr_pkg["qr_svg"] = generate_khqr_svg(khr_pkg["qr_payload"], size=280)

    return {
        "invoice_id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "order_number": invoice.sales_order.order_number,
        "customer_name": invoice.sales_order.customer.name,
        "merchant_name": tenant.name,
        "merchant_city": "Phnom Penh",
        "bakong_account_id": bakong_id,
        "khr_exchange_rate": str(rate),
        "balance_due_usd": str(usd_due),
        "balance_due_khr": str(khr_due),
        "usd": usd_pkg,
        "khr": khr_pkg,
    }
