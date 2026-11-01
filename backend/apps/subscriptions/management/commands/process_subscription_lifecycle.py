from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.core.models import AuditEvent
from apps.subscriptions.models import SubscriptionStatus, TenantSubscription
from apps.tenants.models import TenantStatus


class Command(BaseCommand):
    help = "Processes subscription lifecycle transitions (ACTIVE -> PAST_DUE -> SUSPENDED) based on expiration and grace period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--grace-days",
            type=int,
            default=7,
            help="Grace period days after period end before suspending tenant (default: 7).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate execution without writing changes to the database.",
        )
        parser.add_argument(
            "--as-of",
            type=str,
            default=None,
            help="Evaluation timestamp (ISO-8601 or YYYY-MM-DD) for time-travel verification.",
        )

    def handle(self, *args, **options):
        grace_days = options["grace_days"]
        dry_run = options["dry_run"]
        as_of_str = options["as_of"]

        if as_of_str:
            parsed = parse_datetime(as_of_str)
            if not parsed:
                parsed_d = parse_date(as_of_str)
                if parsed_d:
                    parsed = datetime.combine(parsed_d, datetime.min.time())
            if not parsed:
                raise CommandError(
                    f"Invalid --as-of timestamp: '{as_of_str}'. Use ISO-8601 or YYYY-MM-DD."
                )
            if timezone.is_naive(parsed):
                eval_now = timezone.make_aware(parsed)
            else:
                eval_now = parsed
        else:
            eval_now = timezone.now()

        grace_cutoff = eval_now - timedelta(days=grace_days)

        self.stdout.write(
            self.style.NOTICE(
                f"Starting subscription lifecycle check [eval_now={eval_now.isoformat()}, grace_days={grace_days}, dry_run={dry_run}]"
            )
        )

        # 1. Past due transition: ACTIVE/TRIALING subscriptions whose current_period_end < eval_now
        with transaction.atomic():
            expired_subs = list(
                TenantSubscription.objects.select_for_update()
                .filter(
                    status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
                    current_period_end__isnull=False,
                    current_period_end__lt=eval_now,
                )
            )

            past_due_count = len(expired_subs)
            if not dry_run and past_due_count > 0:
                for sub in expired_subs:
                    sub.status = SubscriptionStatus.PAST_DUE
                    sub.save(update_fields=["status", "updated_at"])
                    AuditEvent.objects.create(
                        tenant=sub.tenant,
                        event_type="SAAS_SUBSCRIPTION_PAST_DUE",
                        target_model="subscriptions.TenantSubscription",
                        target_id=str(sub.id),
                        metadata={
                            "current_period_end": (
                                sub.current_period_end.isoformat()
                                if sub.current_period_end
                                else None
                            ),
                            "eval_now": eval_now.isoformat(),
                        },
                    )

        # 2. Suspension transition: PAST_DUE subscriptions whose current_period_end < grace_cutoff
        with transaction.atomic():
            grace_expired_subs = list(
                TenantSubscription.objects.select_for_update()
                .select_related("tenant")
                .filter(
                    status=SubscriptionStatus.PAST_DUE,
                    current_period_end__isnull=False,
                    current_period_end__lt=grace_cutoff,
                )
            )

            suspended_count = len(grace_expired_subs)
            if not dry_run and suspended_count > 0:
                for sub in grace_expired_subs:
                    sub.status = SubscriptionStatus.SUSPENDED
                    sub.save(update_fields=["status", "updated_at"])

                    tenant = sub.tenant
                    if tenant.status != TenantStatus.OFFBOARDED:
                        tenant.status = TenantStatus.SUSPENDED
                        tenant.save(update_fields=["status", "updated_at"])

                    AuditEvent.objects.create(
                        tenant=tenant,
                        event_type="SAAS_TENANT_AUTO_SUSPENDED_GRACE_EXPIRED",
                        target_model="tenants.Tenant",
                        target_id=str(tenant.id),
                        metadata={
                            "subscription_id": str(sub.id),
                            "current_period_end": (
                                sub.current_period_end.isoformat()
                                if sub.current_period_end
                                else None
                            ),
                            "grace_cutoff": grace_cutoff.isoformat(),
                            "grace_days": grace_days,
                        },
                    )

        summary = (
            f"Subscription Lifecycle Results: "
            f"{past_due_count} transitioned to PAST_DUE, "
            f"{suspended_count} transitioned to SUSPENDED. "
            f"({'SIMULATION - DRY RUN' if dry_run else 'COMMITTED'})"
        )
        self.stdout.write(self.style.SUCCESS(summary))
        return summary
