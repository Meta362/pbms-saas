import json
from pathlib import Path
import tempfile
import importlib
import os
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from apps.accounts.models import AuthSession, PlatformRole
from apps.core.models import AuditEvent
from apps.tenants.models import Tenant, TenantMembership, TenantRole, TenantStatus

User = get_user_model()


class ProductionSettingsSecurityTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        with patch.dict(os.environ, {"DJANGO_DEBUG": "True"}, clear=False):
            import config.settings
            importlib.reload(config.settings)

    def tearDown(self):
        super().tearDown()
        with patch.dict(os.environ, {"DJANGO_DEBUG": "True"}, clear=False):
            import config.settings
            importlib.reload(config.settings)

    """Verifies that production settings (DEBUG=False) strictly validate secrets, JWT signing keys, and allowed hosts."""

    def test_missing_or_invalid_secret_key_in_production(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "",
                "JWT_SIGNING_KEY": "a-valid-production-jwt-signing-key-distinct-from-secret",
                "SUPERADMIN_LICENSE_SIGNING_KEY": "a-valid-production-usb-license-key-distinct-12345",
            },
            clear=True,
        ):
            with self.assertRaisesMessage(ImproperlyConfigured, "Invalid or missing DJANGO_SECRET_KEY for production."):
                import config.settings
                importlib.reload(config.settings)

        with patch.dict(
            os.environ,
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "replace-with-a-secure-50-char-random-string",
                "JWT_SIGNING_KEY": "a-valid-production-jwt-signing-key-distinct-from-secret",
                "SUPERADMIN_LICENSE_SIGNING_KEY": "a-valid-production-usb-license-key-distinct-12345",
            },
            clear=True,
        ):
            with self.assertRaisesMessage(ImproperlyConfigured, "Invalid or missing DJANGO_SECRET_KEY for production."):
                import config.settings
                importlib.reload(config.settings)

    def test_missing_or_invalid_superadmin_license_signing_key_in_production(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "a-valid-production-secret-key-that-is-long-enough",
                "JWT_SIGNING_KEY": "a-valid-production-jwt-signing-key-distinct-from-secret",
                "SUPERADMIN_LICENSE_SIGNING_KEY": "",
            },
            clear=True,
        ):
            with self.assertRaisesMessage(ImproperlyConfigured, "Invalid or missing SUPERADMIN_LICENSE_SIGNING_KEY for production."):
                import config.settings
                importlib.reload(config.settings)

    def test_missing_or_invalid_jwt_signing_key_in_production(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "a-valid-production-secret-key-that-is-long-enough",
                "JWT_SIGNING_KEY": "",
                "SUPERADMIN_LICENSE_SIGNING_KEY": "a-valid-production-usb-license-key-distinct-12345",
            },
            clear=True,
        ):
            with self.assertRaisesMessage(
                ImproperlyConfigured,
                "Invalid or missing JWT_SIGNING_KEY for production. JWT signing key must be non-empty, secure, and distinct from DJANGO_SECRET_KEY.",
            ):
                import config.settings
                importlib.reload(config.settings)

        with patch.dict(
            os.environ,
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "a-valid-production-secret-key-that-is-long-enough",
                "JWT_SIGNING_KEY": "replace-with-separate-jwt-signing-secret-key",
                "SUPERADMIN_LICENSE_SIGNING_KEY": "a-valid-production-usb-license-key-distinct-12345",
            },
            clear=True,
        ):
            with self.assertRaisesMessage(
                ImproperlyConfigured,
                "Invalid or missing JWT_SIGNING_KEY for production. JWT signing key must be non-empty, secure, and distinct from DJANGO_SECRET_KEY.",
            ):
                import config.settings
                importlib.reload(config.settings)

    def test_jwt_signing_key_matching_django_secret_key_rejected(self):
        shared_key = "a-valid-production-secret-key-shared-between-django-and-jwt"
        with patch.dict(
            os.environ,
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": shared_key,
                "JWT_SIGNING_KEY": shared_key,
            },
            clear=True,
        ):
            with self.assertRaisesMessage(
                ImproperlyConfigured,
                "Invalid or missing JWT_SIGNING_KEY for production. JWT signing key must be non-empty, secure, and distinct from DJANGO_SECRET_KEY.",
            ):
                import config.settings
                importlib.reload(config.settings)

    def test_local_only_allowed_hosts_in_production(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_DEBUG": "False",
                "DJANGO_SECRET_KEY": "a-valid-production-secret-key-that-is-long-enough",
                "JWT_SIGNING_KEY": "a-valid-production-jwt-key-distinct-from-secret",
                "SUPERADMIN_LICENSE_SIGNING_KEY": "a-valid-production-usb-license-key-distinct-12345",
                "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
            },
            clear=True,
        ):
            with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_ALLOWED_HOSTS cannot be local-only in production."):
                import config.settings
                importlib.reload(config.settings)

    def test_valid_production_settings_pass(self):
        try:
            with patch.dict(
                os.environ,
                {
                    "DJANGO_DEBUG": "False",
                    "DJANGO_SECRET_KEY": "a-valid-production-secret-key-that-is-long-enough",
                    "JWT_SIGNING_KEY": "a-valid-production-jwt-signing-key-distinct-from-secret",
                "SUPERADMIN_LICENSE_SIGNING_KEY": "a-valid-production-usb-license-key-distinct-12345",
                    "DJANGO_ALLOWED_HOSTS": "pbms.example.com",
                    "DJANGO_SECURE_SSL_REDIRECT": "True",
                },
                clear=True,
            ):
                import config.settings
                importlib.reload(config.settings)

                # Check HTTPS settings were applied
                self.assertTrue(config.settings.SECURE_SSL_REDIRECT)
                self.assertTrue(config.settings.SESSION_COOKIE_SECURE)
                self.assertTrue(config.settings.CSRF_COOKIE_SECURE)
                self.assertEqual(config.settings.SECURE_HSTS_SECONDS, 31536000)
                self.assertFalse(config.settings.SECURE_HSTS_INCLUDE_SUBDOMAINS)
                self.assertFalse(config.settings.SECURE_HSTS_PRELOAD)
                self.assertEqual(config.settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))
                self.assertEqual(
                    config.settings.JWT_SIGNING_KEY,
                    "a-valid-production-jwt-signing-key-distinct-from-secret",
                )
        except ImproperlyConfigured:
            self.fail("Valid production settings raised ImproperlyConfigured unexpectedly.")
        finally:
            import config.settings
            importlib.reload(config.settings)

    def test_production_settings_hsts_overrides(self):
        try:
            with patch.dict(
                os.environ,
                {
                    "DJANGO_DEBUG": "False",
                    "DJANGO_SECRET_KEY": "a-valid-production-secret-key-that-is-long-enough",
                    "JWT_SIGNING_KEY": "a-valid-production-jwt-signing-key-distinct-from-secret",
                "SUPERADMIN_LICENSE_SIGNING_KEY": "a-valid-production-usb-license-key-distinct-12345",
                    "DJANGO_ALLOWED_HOSTS": "pbms.example.com",
                    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS": "True",
                    "DJANGO_SECURE_HSTS_PRELOAD": "True",
                },
                clear=True,
            ):
                import config.settings
                importlib.reload(config.settings)

                self.assertTrue(config.settings.SECURE_HSTS_INCLUDE_SUBDOMAINS)
                self.assertTrue(config.settings.SECURE_HSTS_PRELOAD)
        except ImproperlyConfigured:
            self.fail("Valid production settings raised ImproperlyConfigured unexpectedly with HSTS overrides.")
        finally:
            import config.settings
            importlib.reload(config.settings)

    def test_development_settings_pass_with_defaults(self):
        try:
            with patch.dict(
                os.environ,
                {
                    "DJANGO_DEBUG": "True",
                    "DJANGO_SECRET_KEY": "replace-with-a-secure-50-char-random-string",
                    "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
                },
                clear=True,
            ):
                import config.settings
                importlib.reload(config.settings)
        except ImproperlyConfigured:
            self.fail("Development settings raised ImproperlyConfigured unexpectedly.")
        finally:
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
        self.assertTrue(data["database"]["healthy"])

    def test_health_check_endpoint_returns_503_when_database_unreachable(self) -> None:
        with patch("django.db.connection.cursor", side_effect=Exception("Database connection timeout")):
            response = self.client.get("/api/v1/health/")
            self.assertEqual(response.status_code, 503)
            data = response.json()
            self.assertEqual(data["status"], "degraded")
            self.assertFalse(data["database"]["healthy"])
            self.assertIn("Database connection timeout", data["database"]["error"])

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


class RecordBackupVerifiedCommandTests(TestCase):
    """Verifies REQ-NFR-02: Automated logging of BACKUP_RESTORE_VERIFIED audit events."""

    def test_record_backup_verified_command_creates_auditevent(self):
        call_command(
            "record_backup_verified",
            archive="pbms_dev_20261031_120000.dump.enc",
            sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            users=10,
            tenants=2,
            orders=5,
            audits=20,
        )

        event = AuditEvent.objects.filter(event_type="BACKUP_RESTORE_VERIFIED").first()
        self.assertIsNotNone(event)
        self.assertEqual(event.target_model, "ops.BackupArchive")
        self.assertEqual(event.target_id, "pbms_dev_20261031_120000.dump.enc")
        self.assertEqual(event.metadata["status"], "VERIFIED")
        self.assertEqual(event.metadata["restored_tables"]["accounts_user"], 10)
        self.assertEqual(event.metadata["restored_tables"]["tenants_tenant"], 2)
        self.assertEqual(event.metadata["restored_tables"]["operations_salesorder"], 5)
        self.assertEqual(event.metadata["restored_tables"]["core_auditevent"], 20)



class SuperAdminUsbLicensingSecurityTests(TestCase):
    """
    Verifies the Mandatory SuperAdmin USB Hardware Licensing system:
    - Cryptographic HMAC-SHA256 signing of canonical JSON payload.
    - Physical hardware Volume Serial Number binding (preventing cloned USB files).
    - Email binding, expiry, and revocation checks.
    - Elevated JWT issuance and audit event logging.
    """

    def setUp(self):
        self.client = APIClient()
        self.password = "StrongSuperAdminPass#2026"
        self.super_admin = User.objects.create(
            email="superadmin@pbms.local",
            full_name="Platform Super Admin",
            password=make_password(self.password),
            is_platform_staff=True,
            is_active=True,
            platform_role=PlatformRole.SUPER_ADMIN,
        )
        self.regular_user = User.objects.create(
            email="regular@shop.com",
            full_name="Regular User",
            password=make_password(self.password),
            is_platform_staff=False,
            is_active=True,
            platform_role=PlatformRole.NONE,
        )

        login_res = self.client.post(
            "/api/v1/auth/login/",
            {"email": "superadmin@pbms.local", "password": self.password},
            format="json",
        )
        self.assertEqual(login_res.status_code, 200)
        self.token = login_res.json()["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def test_provision_usb_flash_fails_for_non_existent_or_non_superadmin_user(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = str(Path(tmpdir) / "license.dat")
            # 1. Non-existent user
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "provision_usb_flash",
                    drive="E:",
                    email="nonexistent@pbms.local",
                    hardware_serial="A4B27F91",
                    output_file=out_file,
                )
            self.assertIn("does not exist", str(ctx.exception))

            # 2. Non-superadmin user
            with self.assertRaises(CommandError) as ctx:
                call_command(
                    "provision_usb_flash",
                    drive="E:",
                    email="regular@shop.com",
                    hardware_serial="A4B27F91",
                    output_file=out_file,
                )
            self.assertIn("not a SuperAdmin", str(ctx.exception))

    def test_provision_usb_flash_generates_valid_license_file_and_audit_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = str(Path(tmpdir) / "license.dat")
            call_command(
                "provision_usb_flash",
                drive="E:",
                email="superadmin@pbms.local",
                hardware_serial="A4B27F91",
                output_file=out_file,
            )
            self.assertTrue(Path(out_file).exists())
            license_doc = json.loads(Path(out_file).read_text(encoding="utf-8"))
            self.assertEqual(license_doc["issued_to_email"], "superadmin@pbms.local")
            self.assertEqual(license_doc["hardware_binding"]["volume_serial_number"], "A4B27F91")
            self.assertIn("signature", license_doc)

            # Audit event logged
            self.assertTrue(
                AuditEvent.objects.filter(
                    event_type="SUPERADMIN_USB_LICENSE_PROVISIONED",
                    target_id=license_doc["license_id"],
                ).exists()
            )

    def test_usb_license_verification_rejects_unauthenticated_and_non_superadmin(self):
        anon_client = APIClient()
        res = anon_client.post(
            "/api/v1/super-admin/license/verify/",
            {"license_data": {}, "hardware_fingerprint": {}},
            format="json",
        )
        self.assertEqual(res.status_code, 401)

        # Regular user login
        reg_login = anon_client.post(
            "/api/v1/auth/login/",
            {"email": "regular@shop.com", "password": self.password},
            format="json",
        )
        anon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {reg_login.json()['access_token']}")
        res_forbidden = anon_client.post(
            "/api/v1/super-admin/license/verify/",
            {"license_data": {}, "hardware_fingerprint": {}},
            format="json",
        )
        self.assertEqual(res_forbidden.status_code, 403)

    def test_usb_license_verification_rejects_tampered_payload(self):
        from apps.core.usb_licensing import build_license_payload
        license_doc = build_license_payload(
            issued_to_user=self.super_admin,
            volume_serial_number="A4B27F91",
        )
        # Tamper payload (e.g. extending expiry)
        license_doc["expires_at"] = "2099-01-01T00:00:00Z"

        res = self.client.post(
            "/api/v1/super-admin/license/verify/",
            {
                "license_data": license_doc,
                "hardware_fingerprint": {"volume_serial_number": "A4B27F91"},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("signature validation failed", res.json()["detail"])
        self.assertTrue(
            AuditEvent.objects.filter(event_type="SUPERADMIN_USB_LICENSE_REJECTED").exists()
        )

    def test_usb_license_verification_rejects_hardware_serial_mismatch(self):
        from apps.core.usb_licensing import build_license_payload
        license_doc = build_license_payload(
            issued_to_user=self.super_admin,
            volume_serial_number="A4B27F91",
        )
        # Presented from a different USB drive (e.g. cloned file)
        res = self.client.post(
            "/api/v1/super-admin/license/verify/",
            {
                "license_data": license_doc,
                "hardware_fingerprint": {"volume_serial_number": "DIFFERENT-SERIAL"},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Hardware serial mismatch", res.json()["detail"])

    def test_usb_license_verification_rejects_mismatched_email(self):
        from apps.core.usb_licensing import build_license_payload
        license_doc = build_license_payload(
            issued_to_user=self.regular_user,
            volume_serial_number="A4B27F91",
        )
        res = self.client.post(
            "/api/v1/super-admin/license/verify/",
            {
                "license_data": license_doc,
                "hardware_fingerprint": {"volume_serial_number": "A4B27F91"},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("License is issued to", res.json()["detail"])

    def test_usb_license_verification_rejects_expired_license(self):
        from apps.core.usb_licensing import build_license_payload
        license_doc = build_license_payload(
            issued_to_user=self.super_admin,
            volume_serial_number="A4B27F91",
            valid_days=-10,  # Expired 10 days ago
        )
        res = self.client.post(
            "/api/v1/super-admin/license/verify/",
            {
                "license_data": license_doc,
                "hardware_fingerprint": {"volume_serial_number": "A4B27F91"},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("License has expired", res.json()["detail"])

    def test_usb_license_verification_success_issues_elevated_token_and_audits(self):
        from apps.core.usb_licensing import build_license_payload
        license_doc = build_license_payload(
            issued_to_user=self.super_admin,
            volume_serial_number="A4B27F91",
            valid_days=365,
        )
        res = self.client.post(
            "/api/v1/super-admin/license/verify/",
            {
                "license_data": license_doc,
                "hardware_fingerprint": {"volume_serial_number": "A4B27F91"},
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "verified")
        self.assertEqual(data["license_id"], license_doc["license_id"])
        self.assertIn("elevated_token", data)
        self.assertEqual(data["elevation_expires_in"], 900)

        # Audit event recorded
        self.assertTrue(
            AuditEvent.objects.filter(
                event_type="SUPERADMIN_USB_LICENSE_VERIFIED",
                target_id=license_doc["license_id"],
            ).exists()
        )

    def test_usb_license_revocation_blocks_subsequent_verification(self):
        from apps.core.usb_licensing import build_license_payload
        license_doc = build_license_payload(
            issued_to_user=self.super_admin,
            volume_serial_number="A4B27F91",
            valid_days=365,
        )
        # 1. Revoke the license
        rev_res = self.client.post(
            "/api/v1/super-admin/license/revoke/",
            {"license_id": license_doc["license_id"], "reason": "Lost USB Dongle"},
            format="json",
        )
        self.assertEqual(rev_res.status_code, 200)
        self.assertEqual(rev_res.json()["status"], "revoked")

        # 2. Attempt verification -> MUST be rejected with 403
        ver_res = self.client.post(
            "/api/v1/super-admin/license/verify/",
            {
                "license_data": license_doc,
                "hardware_fingerprint": {"volume_serial_number": "A4B27F91"},
            },
            format="json",
        )
        self.assertEqual(ver_res.status_code, 403)
        self.assertIn("permanently revoked", ver_res.json()["detail"])

    def test_has_verified_usb_license_permission_enforcement(self):
        from apps.core.usb_licensing import build_license_payload
        from apps.tenants.permissions import HasVerifiedUsbLicense
        from rest_framework.test import APIRequestFactory, force_authenticate
        from rest_framework.request import Request

        factory = APIRequestFactory()
        perm = HasVerifiedUsbLicense()

        # 1. When USB_HARDWARE_LICENSING_ENFORCED is False
        with override_settings(USB_HARDWARE_LICENSING_ENFORCED=False):
            req = factory.get("/")
            force_authenticate(req, user=self.super_admin)
            drf_req = Request(req)
            self.assertTrue(perm.has_permission(drf_req, None))

        # 2. When USB_HARDWARE_LICENSING_ENFORCED is True
        with override_settings(USB_HARDWARE_LICENSING_ENFORCED=True):
            # Without elevated token -> False
            req_no_token = factory.get("/")
            force_authenticate(req_no_token, user=self.super_admin)
            drf_req_no = Request(req_no_token)
            self.assertFalse(perm.has_permission(drf_req_no, None))

            # With valid elevated token -> True
            license_doc = build_license_payload(
                issued_to_user=self.super_admin,
                volume_serial_number="A4B27F91",
            )
            ver_res = self.client.post(
                "/api/v1/super-admin/license/verify/",
                {
                    "license_data": license_doc,
                    "hardware_fingerprint": {"volume_serial_number": "A4B27F91"},
                },
                format="json",
            )
            elevated_token = ver_res.json()["elevated_token"]

            req_with_token = factory.get("/", HTTP_X_USB_ELEVATED_TOKEN=elevated_token)
            force_authenticate(req_with_token, user=self.super_admin)
            drf_req_with = Request(req_with_token)
            self.assertTrue(perm.has_permission(drf_req_with, None))
