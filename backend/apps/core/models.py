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
