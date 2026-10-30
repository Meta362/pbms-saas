from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from apps.accounts.models import LanguagePreference
from apps.tenants.models import TenantMembership, TenantRole

User = get_user_model()


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RefreshTokenRequestSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(write_only=True)


class TenantMembershipSerializer(serializers.ModelSerializer):
    tenant_id = serializers.UUIDField(read_only=True)
    user_id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)

    class Meta:
        model = TenantMembership
        fields = [
            "id",
            "tenant_id",
            "user_id",
            "email",
            "full_name",
            "phone",
            "role",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class TenantMembershipCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    password = serializers.CharField(
        min_length=10,
        write_only=True,
        required=False,
        trim_whitespace=False,
    )
    role = serializers.ChoiceField(choices=TenantRole.choices, default=TenantRole.SALES_STAFF)
    preferred_language = serializers.ChoiceField(
        choices=LanguagePreference.choices,
        required=False,
        default=LanguagePreference.KHMER,
    )

    def validate(self, attrs: dict) -> dict:
        forbidden_keys = {"platform_role", "is_platform_staff", "is_superuser", "is_staff"}
        if isinstance(self.initial_data, dict):
            injected = forbidden_keys.intersection(self.initial_data.keys())
            if injected:
                raise serializers.ValidationError(
                    {"detail": "Platform privilege fields cannot be set via tenant membership APIs."}
                )

        email = attrs["email"].lower().strip()
        attrs["email"] = email
        existing_user = User.objects.filter(email=email).first()
        attrs["existing_user"] = existing_user

        password = attrs.get("password")
        full_name = attrs.get("full_name", "").strip()
        attrs["full_name"] = full_name

        if existing_user is None:
            if not full_name:
                raise serializers.ValidationError(
                    {"full_name": "Full name is required when creating a new staff user."}
                )
            if not password:
                raise serializers.ValidationError(
                    {"password": "Password is required when creating a new staff user."}
                )

        if password:
            candidate_user = existing_user or User(
                email=email,
                full_name=full_name or email,
            )
            try:
                validate_password(password, user=candidate_user)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)}) from exc

        return attrs


class TenantMembershipUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=TenantRole.choices, required=False)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        forbidden_keys = {"platform_role", "is_platform_staff", "is_superuser", "is_staff"}
        if isinstance(self.initial_data, dict):
            injected = forbidden_keys.intersection(self.initial_data.keys())
            if injected:
                raise serializers.ValidationError(
                    {"detail": "Platform privilege fields cannot be modified via tenant membership APIs."}
                )
        if "role" not in attrs and "is_active" not in attrs:
            raise serializers.ValidationError(
                {"detail": "At least one of 'role' or 'is_active' must be provided."}
            )
        return attrs
