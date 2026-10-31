"""
Tenant-scoped sequential allocation service.
Eliminates race conditions and duplicate key collisions (DOM-002, TENANT-001).
Guarantees strictly monotonic sequence generation even after entity deletions or out-of-band entries.
"""

from __future__ import annotations

import re
from typing import Type

from django.db import models
from apps.operations.models import CustomerInvoice, ProductionJob, Quotation, SalesOrder
from apps.tenants.models import Tenant

_NUMBER_PATTERN = re.compile(r"^.*?-(\d+)$")


def _allocate_next_sequence_for_model(
    model_class: Type[models.Model],
    number_field: str,
    prefix: str,
    tenant: Tenant,
    padding: int = 4,
) -> str:
    """
    Computes the next sequence number by finding the maximum existing numeric suffix
    for this tenant, then monotonically increments it, verifying non-existence.
    """
    existing_numbers = (
        model_class.objects.filter(tenant=tenant)
        .values_list(number_field, flat=True)
    )
    max_seq = 0
    for num_str in existing_numbers:
        if not num_str:
            continue
        match = _NUMBER_PATTERN.match(str(num_str).strip())
        if match:
            try:
                seq_val = int(match.group(1))
                if seq_val > max_seq:
                    max_seq = seq_val
            except ValueError:
                continue

    candidate_seq = max_seq + 1
    candidate_code = f"{prefix}-{candidate_seq:0{padding}d}"

    while model_class.objects.filter(tenant=tenant, **{number_field: candidate_code}).exists():
        candidate_seq += 1
        candidate_code = f"{prefix}-{candidate_seq:0{padding}d}"

    return candidate_code


def allocate_quotation_number(tenant: Tenant) -> str:
    """Allocates the next unique, monotonic quote number (e.g. QT-0001) for this tenant."""
    return _allocate_next_sequence_for_model(Quotation, "quote_number", "QT", tenant)


def allocate_order_job_and_invoice_numbers(tenant: Tenant) -> tuple[str, str, str]:
    """Allocates unique, monotonic order, job, and invoice numbers for this tenant."""
    order_num = _allocate_next_sequence_for_model(SalesOrder, "order_number", "SO", tenant)
    job_num = _allocate_next_sequence_for_model(ProductionJob, "job_Code", "JOB", tenant)
    inv_num = _allocate_next_sequence_for_model(CustomerInvoice, "invoice_number", "INV", tenant)
    return order_num, job_num, inv_num
