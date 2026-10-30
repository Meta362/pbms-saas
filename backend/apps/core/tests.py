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

import os
import importlib
from django.core.exceptions import ImproperlyConfigured

class ProductionSettingsSecurityTests(TestCase):
    """Verifies that production settings (DEBUG=False) strictly validate secrets and allowed hosts."""

    def test_missing_or_invalid_secret_key_in_production(self):
        with patch.dict(os.environ, {"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": ""}):
            with self.assertRaisesMessage(ImproperlyConfigured, "Invalid or missing DJANGO_SECRET_KEY for production."):
                import config.settings
                importlib.reload(config.settings)

        with patch.dict(os.environ, {"DJANGO_DEBUG": "False", "DJANGO_SECRET_KEY": "replace-with-a-secure-50-char-random-string"}):
            with self.assertRaisesMessage(ImproperlyConfigured, "Invalid or missing DJANGO_SECRET_KEY for production."):
                import config.settings
                importlib.reload(config.settings)

    def test_local_only_allowed_hosts_in_production(self):
        with patch.dict(os.environ, {
            "DJANGO_DEBUG": "False",
            "DJANGO_SECRET_KEY": "a-valid-production-secret-key-that-is-long-enough",
            "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1"
        }):
            with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_ALLOWED_HOSTS cannot be local-only in production."):
                import config.settings
                importlib.reload(config.settings)

    def test_valid_production_settings_pass(self):
        try:
            with patch.dict(os.environ, {
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "a-valid-production-secret-key-that-is-long-enough",
                "DJANGO_ALLOWED_HOSTS": "pbms.example.com",
                "DJANGO_SECURE_SSL_REDIRECT": "True"
            }):
                import config.settings
                importlib.reload(config.settings)

                # Check HTTPS settings were applied
                self.assertTrue(config.settings.SECURE_SSL_REDIRECT)
                self.assertTrue(config.settings.SESSION_COOKIE_SECURE)
                self.assertTrue(config.settings.CSRF_COOKIE_SECURE)
                self.assertEqual(config.settings.SECURE_HSTS_SECONDS, 31536000)
                self.assertTrue(config.settings.SECURE_HSTS_INCLUDE_SUBDOMAINS)
                self.assertTrue(config.settings.SECURE_HSTS_PRELOAD)
                self.assertEqual(config.settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))
        except ImproperlyConfigured:
            self.fail("Valid production settings raised ImproperlyConfigured unexpectedly.")
        finally:
            # Reload settings back to normal
            import config.settings
            importlib.reload(config.settings)

    def test_development_settings_pass_with_defaults(self):
        try:
            with patch.dict(os.environ, {
                "DJANGO_DEBUG": "True",
                "DJANGO_SECRET_KEY": "replace-with-a-secure-50-char-random-string",
                "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1"
            }):
                import config.settings
                importlib.reload(config.settings)
        except ImproperlyConfigured:
            self.fail("Development settings raised ImproperlyConfigured unexpectedly.")
        finally:
            # Reload settings back to normal
            import config.settings
            importlib.reload(config.settings)


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
