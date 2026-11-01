from decimal import Decimal
from rest_framework import serializers
from apps.tenants.models import StaffInvitation, Tenant, TenantRole


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
            "is_tax_registered",
            "tax_id_number",
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
    - is_tax_registered enables/disables VAT
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
    is_tax_registered = serializers.BooleanField(required=False)
    tax_id_number = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                "At least one setting field must be provided."
            )
        if attrs.get("is_tax_registered") is False and "tax_rate_percent" not in attrs:
            attrs["tax_rate_percent"] = Decimal("0.00")
        return attrs


class StaffInvitationSerializer(serializers.ModelSerializer):
    invited_by_email = serializers.EmailField(source="invited_by.email", read_only=True)

    class Meta:
        model = StaffInvitation
        fields = [
            "id",
            "email",
            "role",
            "invited_by_email",
            "expires_at",
            "accepted_at",
            "is_revoked",
            "created_at",
        ]
        read_only_fields = fields


class StaffInvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=TenantRole.choices, default=TenantRole.SALES_STAFF)

    def validate_email(self, value: str) -> str:
        return value.lower().strip()
