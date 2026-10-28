from rest_framework import serializers
from apps.subscriptions.models import BillingCycle, PaymentProvider, Plan


class PublicPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name_en",
            "name_km",
            "description_en",
            "description_km",
            "monthly_price_usd",
            "annual_price_usd",
            "max_staff_users",
            "max_orders_per_month",
        ]


class PublicTenantRegistrationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=10, write_only=True, trim_whitespace=False)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    business_name = serializers.CharField(max_length=150)
    business_slug = serializers.SlugField(max_length=100)
    plan_code = serializers.SlugField(max_length=50)
    billing_cycle = serializers.ChoiceField(
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
    )
    payment_provider = serializers.ChoiceField(
        choices=PaymentProvider.choices,
        default=PaymentProvider.MANUAL_TRANSFER,
    )
    provider_reference = serializers.CharField(
        max_length=120,
        required=False,
        allow_blank=True,
        default="",
    )
    idempotency_key = serializers.CharField(max_length=100)


class PaymentReconcileSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=[("APPROVE", "Approve"), ("REJECT", "Reject")])
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class TenantStatusActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=[("SUSPEND", "Suspend"), ("ACTIVATE", "Activate")])
    reason = serializers.CharField(required=False, allow_blank=True, default="")
