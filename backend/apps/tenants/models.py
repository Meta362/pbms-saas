from decimal import Decimal
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedUUIDModel


class TenantStatus(models.TextChoices):
    PENDING_REVIEW = "PENDING_REVIEW", "Pending Super Admin Review"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"
    OFFBOARDED = "OFFBOARDED", "Offboarded"


class TenantRole(models.TextChoices):
    TENANT_OWNER = "TENANT_OWNER", "Tenant Owner"
    TENANT_MANAGER = "TENANT_MANAGER", "Tenant Manager"
    SALES_STAFF = "SALES_STAFF", "Sales Staff"
    DESIGNER = "DESIGNER", "Designer"
    PRODUCTION_STAFF = "PRODUCTION_STAFF", "Production Staff"
    INVENTORY_STAFF = "INVENTORY_STAFF", "Inventory Staff"
    FINANCE_STAFF = "FINANCE_STAFF", "Finance Staff"


class Tenant(TimeStampedUUIDModel):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    status = models.CharField(
        max_length=24,
        choices=TenantStatus.choices,
        default=TenantStatus.PENDING_REVIEW,
        db_index=True,
    )
    phone = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    base_currency = models.CharField(max_length=3, default="USD", editable=False)
    khr_exchange_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("4100.00"),
    )
    tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    is_tax_registered = models.BooleanField(
        default=True,
        help_text="True if registered with GDT for 10% VAT. False for non-registered family/small print shops.",
    )
    tax_id_number = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Official GDT Tax Identification Number (TIN).",
    )

    class Meta:
        db_table = "tenants_tenant"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(khr_exchange_rate__gt=Decimal("0.00")),
                name="chk_tenant_khr_rate_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_rate_percent__gte=Decimal("0.00"))
                & models.Q(tax_rate_percent__lte=Decimal("100.00")),
                name="chk_tenant_tax_rate_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class TenantMembership(TimeStampedUUIDModel):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant_memberships",
    )
    role = models.CharField(
        max_length=32,
        choices=TenantRole.choices,
        default=TenantRole.SALES_STAFF,
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "tenants_tenantmembership"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user"],
                name="uq_tenant_user_membership",
            )
        ]
        indexes = [
            models.Index(fields=["user", "tenant", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} -> {self.tenant.slug} [{self.role}]"
