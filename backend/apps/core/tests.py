from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from apps.accounts.models import AuthSession, PlatformRole
from apps.core.models import AuditEvent
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus

User = get_user_model()


from unittest.mock import patch

class SeedPbmsDemoCommandTests(TestCase):
    """Regression tests for the seed_pbms_demo command safeguard."""

    @override_settings(DEBUG=False)
    def test_seed_demo_fails_in_production(self):
        """Ensure the seed command raises a CommandError when DEBUG is False."""
        with self.assertRaisesMessage(
            CommandError, "This command can only be run in local development mode (DEBUG=True)."
        ):
            call_command("seed_pbms_demo")

    @override_settings(DEBUG=True)
    def test_seed_demo_succeeds_in_development(self):
        """Ensure the seed command executes without raising CommandError when DEBUG is True.
        This runs in the isolated Django test database and rolls back automatically.
        """
        try:
            call_command("seed_pbms_demo")
        except CommandError:
            self.fail("seed_pbms_demo raised CommandError unexpectedly with DEBUG=True.")


class CoreHealthAndSecurityBaselineTests(TestCase):
    """Verifies REQ-AUTH-01, PostgreSQL Models, Constraints, and Audit Trail."""

    def setUp(self) -> None:
        self.client = APIClient()

    def test_health_check_endpoint_returns_200_and_argon2_status(self) -> None:
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["argon2id_enabled"])

    def test_password_hasher_uses_argon2id_by_default(self) -> None:
        hashed = make_password("StrongPrintingPass#2026")
        self.assertTrue(hashed.startswith("argon2$argon2id$"))

    def test_user_tenant_membership_session_and_audit_constraints(self) -> None:
        owner = User.objects.create_user(
            email="owner@angkorprint.com",
            password="StrongPassword#2026",
            full_name="Sokha Owner",
        )
        self.assertEqual(owner.platform_role, PlatformRole.NONE)
        self.assertTrue(owner.password.startswith("argon2$argon2id$"))

        tenant = Tenant.objects.create(
            name="Angkor Printing House",
            slug="angkor-printing",
            status=TenantStatus.ACTIVE,
            khr_exchange_rate=Decimal("4100.00"),
        )
        membership = TenantMembership.objects.create(
            tenant=tenant,
            user=owner,
            role=TenantRole.TENANT_OWNER,
        )
        self.assertEqual(membership.role, TenantRole.TENANT_OWNER)

        # Duplicate membership in same tenant must violate UniqueConstraint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TenantMembership.objects.create(
                    tenant=tenant,
                    user=owner,
                    role=TenantRole.SALES_STAFF,
                )

        # AuthSession creation
        session = AuthSession.objects.create(
            user=owner,
            current_refresh_jti_hash="a" * 64,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(session.is_revoked)

        # AuditEvent creation
        event = AuditEvent.objects.create(
            actor_user=owner,
            tenant=tenant,
            event_type="TENANT_CREATED",
            target_model="tenants.Tenant",
            target_id=str(tenant.id),
            metadata={"slug": tenant.slug},
        )
        self.assertIsNotNone(event.id)


class ProductionSettingsHardeningTests(TestCase):
    """Verifies that production settings are secure and fail-safe."""

    def test_production_fails_with_insecure_secret(self):
        import subprocess
        import os

        env = os.environ.copy()
        env["DJANGO_DEBUG"] = "False"
        env["DJANGO_SECRET_KEY"] = "dev-only-insecure-secret-key-replace-in-env-immediately-9876543210"

        result = subprocess.run(
            ["python", "manage.py", "check"],
            env=env,
            capture_output=True,
            text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Production settings require a securely configured DJANGO_SECRET_KEY.", result.stderr)

    def test_production_fails_with_empty_secret(self):
        import subprocess
        import os

        env = os.environ.copy()
        env["DJANGO_DEBUG"] = "False"
        env["DJANGO_SECRET_KEY"] = ""

        result = subprocess.run(
            ["python", "manage.py", "check"],
            env=env,
            capture_output=True,
            text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Production settings require a securely configured DJANGO_SECRET_KEY.", result.stderr)

    def test_production_succeeds_with_secure_secret(self):
        import subprocess
        import os

        env = os.environ.copy()
        env["DJANGO_DEBUG"] = "False"
        env["DJANGO_SECRET_KEY"] = "a-secure-random-string-for-production-use"

        result = subprocess.run(
            ["python", "manage.py", "check"],
            env=env,
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("System check identified no issues", result.stderr + result.stdout)

    def test_development_succeeds_with_insecure_secret(self):
        import subprocess
        import os

        env = os.environ.copy()
        env["DJANGO_DEBUG"] = "True"
        env["DJANGO_SECRET_KEY"] = "dev-only-insecure-secret-key-replace-in-env-immediately-9876543210"

        result = subprocess.run(
            ["python", "manage.py", "check"],
            env=env,
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("System check identified no issues", result.stderr + result.stdout)
