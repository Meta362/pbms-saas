from decimal import Decimal
from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedUUIDModel
from apps.tenants.models import Tenant


class SubscriptionStatus(models.TextChoices):
    TRIALING = "TRIALING", "Trialing"
    PENDING_PAYMENT = "PENDING_PAYMENT", "Pending Payment Verification"
    ACTIVE = "ACTIVE", "Active"
    PAST_DUE = "PAST_DUE", "Past Due"
    SUSPENDED = "SUSPENDED", "Suspended"
    CANCELED = "CANCELED", "Canceled"


class BillingCycle(models.TextChoices):
    MONTHLY = "MONTHLY", "Monthly"
    ANNUAL = "ANNUAL", "Annual"


class PaymentProvider(models.TextChoices):
    MOCK_LOCAL = "MOCK_LOCAL", "Mock Local Provider (Dev/Test Only)"
    MANUAL_TRANSFER = "MANUAL_TRANSFER", "Manual Bank / KHQR Transfer"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending Verification"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    REJECTED = "REJECTED", "Rejected"


class Plan(TimeStampedUUIDModel):
    code = models.SlugField(max_length=50, unique=True, db_index=True)
    name_en = models.CharField(max_length=100)
    name_km = models.CharField(max_length=100)
    description_en = models.TextField(blank=True, default="")
    description_km = models.TextField(blank=True, default="")
    monthly_price_usd = models.DecimalField(max_digits=12, decimal_places=2)
    annual_price_usd = models.DecimalField(max_digits=12, decimal_places=2)
    max_staff_users = models.PositiveIntegerField(default=5)
    max_orders_per_month = models.PositiveIntegerField(default=500)
    is_public = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = "subscriptions_plan"
        ordering = ["sort_order", "monthly_price_usd"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monthly_price_usd__gte=Decimal("0.00"))
                & models.Q(annual_price_usd__gte=Decimal("0.00")),
                name="chk_plan_prices_non_negative",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name_en} (${self.monthly_price_usd}/mo)"


class TenantSubscription(TimeStampedUUIDModel):
    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="subscription",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.RESTRICT,
        related_name="subscriptions",
    )
    billing_cycle = models.CharField(
        max_length=16,
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
    )
    status = models.CharField(
        max_length=24,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.PENDING_PAYMENT,
        db_index=True,
    )
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "subscriptions_tenantsubscription"

    def __str__(self) -> str:
        return f"{self.tenant.slug} -> {self.plan.code} [{self.status}]"


class SubscriptionPayment(TimeStampedUUIDModel):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.RESTRICT,
        related_name="subscription_payments",
    )
    subscription = models.ForeignKey(
        TenantSubscription,
        on_delete=models.RESTRICT,
        related_name="payments",
    )
    amount_usd = models.DecimalField(max_digits=12, decimal_places=2)
    provider = models.CharField(
        max_length=24,
        choices=PaymentProvider.choices,
        default=PaymentProvider.MANUAL_TRANSFER,
    )
    provider_reference = models.CharField(max_length=120, blank=True, default="")
    idempotency_key = models.CharField(max_length=100, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="verified_subscription_payments",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "subscriptions_subscriptionpayment"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_usd__gt=Decimal("0.00")),
                name="chk_sub_payment_amount_positive",
            )
        ]
