from django.core.management.base import BaseCommand
from apps.core.models import AuditEvent


class Command(BaseCommand):
    help = "Records a BACKUP_RESTORE_VERIFIED immutable AuditEvent in PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--archive", required=True, help="Filename of the verified encrypted backup archive.")
        parser.add_argument("--sha256", required=True, help="SHA-256 digest of the backup archive.")
        parser.add_argument("--users", type=int, default=0, help="Count of restored accounts_user rows.")
        parser.add_argument("--tenants", type=int, default=0, help="Count of restored tenants_tenant rows.")
        parser.add_argument("--orders", type=int, default=0, help="Count of restored operations_salesorder rows.")
        parser.add_argument("--audits", type=int, default=0, help="Count of restored core_auditevent rows.")

    def handle(self, *args, **options):
        archive = options["archive"]
        sha256_hash = options["sha256"]
        users_count = options["users"]
        tenants_count = options["tenants"]
        orders_count = options["orders"]
        audits_count = options["audits"]

        metadata = {
            "sha256": sha256_hash,
            "restored_tables": {
                "accounts_user": users_count,
                "tenants_tenant": tenants_count,
                "operations_salesorder": orders_count,
                "core_auditevent": audits_count,
            },
            "status": "VERIFIED",
        }

        event = AuditEvent.objects.create(
            event_type="BACKUP_RESTORE_VERIFIED",
            target_model="ops.BackupArchive",
            target_id=archive[:64],
            metadata=metadata,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully recorded BACKUP_RESTORE_VERIFIED event (id: {event.id}) for archive: {archive}"
            )
        )

