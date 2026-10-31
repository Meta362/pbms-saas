"""
Management command to provision a standard consumer USB Flash Drive as a SuperAdmin hardware dongle.
Usage:
  python manage.py provision_usb_flash --drive E: --email admin@pbms.local [--valid-days 365]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from apps.accounts.models import PlatformRole, User
from apps.core.models import AuditEvent
from apps.core.usb_licensing import (
    build_license_payload,
    query_windows_volume_serial,
)


class Command(BaseCommand):
    help = "Provisions a consumer USB Flash Drive as a cryptographically signed SuperAdmin hardware security dongle."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--drive",
            required=True,
            type=str,
            help="Drive letter or mount path of the target USB Flash Drive (e.g. 'E:' or 'E:\\').",
        )
        parser.add_argument(
            "--email",
            required=True,
            type=str,
            help="SuperAdmin user email to bind this hardware token to.",
        )
        parser.add_argument(
            "--valid-days",
            type=int,
            default=365,
            help="Number of days before the USB license expires (default: 365).",
        )
        parser.add_argument(
            "--hardware-serial",
            type=str,
            default="",
            help="Optional manual override for the hardware Volume Serial Number (useful for CI or non-Windows).",
        )
        parser.add_argument(
            "--output-file",
            type=str,
            default="",
            help="Optional exact path to write the license file (defaults to '<drive>/license.dat').",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        email = options["email"].strip().lower()
        drive = options["drive"].strip()
        valid_days = options["valid_days"]
        manual_serial = options["hardware_serial"].strip()
        custom_out = options["output_file"].strip()

        # 1. Verify user exists and has SUPER_ADMIN role
        try:
            admin_user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise CommandError(f"User with email '{email}' does not exist.")

        if admin_user.platform_role != PlatformRole.SUPER_ADMIN or not admin_user.is_platform_staff:
            raise CommandError(
                f"User '{email}' is not a SuperAdmin (role: {admin_user.platform_role}, staff: {admin_user.is_platform_staff}). "
                "USB security dongles can only be provisioned for authorized Platform SuperAdmins."
            )

        # 2. Extract hardware volume serial number
        if manual_serial:
            volume_serial = manual_serial.upper()
            self.stdout.write(f"Using manually specified volume serial: {volume_serial}")
        else:
            try:
                volume_serial = query_windows_volume_serial(drive)
                self.stdout.write(f"Detected USB volume serial for drive '{drive}': {volume_serial}")
            except Exception as exc:
                raise CommandError(
                    f"Unable to query hardware serial for drive '{drive}': {exc}\n"
                    "Ensure the USB drive is properly inserted or provide --hardware-serial."
                ) from exc

        # 3. Assemble and cryptographically sign the license payload
        license_doc = build_license_payload(
            issued_to_user=admin_user,
            volume_serial_number=volume_serial,
            valid_days=valid_days,
        )

        # 4. Determine destination path
        if custom_out:
            dest_path = Path(custom_out)
        else:
            clean_drive = drive.rstrip("\\/")
            if len(clean_drive) == 1 and clean_drive.isalpha():
                clean_drive = f"{clean_drive}:"
            dest_path = Path(f"{clean_drive}/license.dat")

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            formatted_json = json.dumps(license_doc, indent=2)
            dest_path.write_text(formatted_json, encoding="utf-8")
        except Exception as exc:
            raise CommandError(f"Failed to write license file to '{dest_path}': {exc}") from exc

        # 5. Record immutable audit event
        AuditEvent.objects.create(
            actor_user=admin_user,
            event_type="SUPERADMIN_USB_LICENSE_PROVISIONED",
            target_model="core.UsbLicense",
            target_id=license_doc["license_id"],
            metadata={
                "issued_to_email": admin_user.email,
                "volume_serial": volume_serial,
                "valid_from": license_doc["valid_from"],
                "expires_at": license_doc["expires_at"],
                "destination_path": str(dest_path),
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully provisioned SuperAdmin USB Security Dongle!\n"
                f"  License ID:       {license_doc['license_id']}\n"
                f"  Issued To:        {admin_user.email}\n"
                f"  Hardware Serial:  {volume_serial}\n"
                f"  Valid Until:      {license_doc['expires_at']}\n"
                f"  Destination File: {dest_path}\n"
                f"  Signature (Ed/HM):{license_doc['signature'][:16]}..."
            )
        )
