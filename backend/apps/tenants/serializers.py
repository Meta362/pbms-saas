from decimal import Decimal
from rest_framework import serializers
from apps.tenants.models import Tenant


class TenantSettingsSerializer(serializers.ModelSerializer):
    """
    Read serializer for tenant business settings.
    """

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "slug",
            "base_currency",
            "khr_exchange_rate",
            "tax_rate_percent",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "slug",
            "base_currency",
            "updated_at",
        ]


class TenantSettingsUpdateSerializer(serializers.Serializer):
    """
    Update serializer for tenant business settings.
    Enforces domain constraints matching Tenant check constraints:
    - khr_exchange_rate must be > 0 (min_value 0.01)
    - tax_rate_percent must be between 0.00 and 100.00
    """

    khr_exchange_rate = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
    )
    tax_rate_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.00"),
        max_value=Decimal("100.00"),
        required=False,
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "At least one setting field (khr_exchange_rate or tax_rate_percent) must be provided."
            )
        return attrs

