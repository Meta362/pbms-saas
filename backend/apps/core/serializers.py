from rest_framework import serializers
from apps.core.models import PlatformAnnouncement


class PlatformAnnouncementSerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = PlatformAnnouncement
        fields = [
            "id",
            "title",
            "message_km",
            "message_en",
            "level",
            "is_active",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by_email", "created_at", "updated_at"]
