from rest_framework import serializers


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RefreshTokenRequestSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(write_only=True)
