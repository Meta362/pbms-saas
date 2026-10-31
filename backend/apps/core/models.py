import uuid
from django.conf import settings
from django.db import models


class TimeStampedUUIDModel(models.Model):
    """Abstract base model providing UUIDv4 primary key and UTC timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditEvent(models.Model):
    """
    REQ-NFR-01: Immutable audit trail for security, platform, and tenant events.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    event_type = models.CharField(max_length=100, db_index=True)
    target_model = models.CharField(max_length=100, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "core_auditevent"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.created_at.isoformat()}] {self.event_type}"


class PlatformAnnouncement(TimeStampedUUIDModel):
    """
    SuperAdmin Global Broadcast / Maintenance Notification for all tenants.
    """
    title = models.CharField(max_length=200)
    message_km = models.TextField()
    message_en = models.TextField()
    level = models.CharField(
        max_length=20,
        choices=[("INFO", "Info"), ("WARNING", "Warning"), ("URGENT", "Urgent")],
        default="INFO",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="announcements",
    )

    class Meta:
        db_table = "core_platformannouncement"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.level}) [{'ACTIVE' if self.is_active else 'INACTIVE'}]"
