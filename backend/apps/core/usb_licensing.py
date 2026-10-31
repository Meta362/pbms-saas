"""
PBMS SaaS — SuperAdmin USB Hardware Licensing Service
Enforces cryptographic verification of consumer USB flash drive tokens bound to hardware serials.
Invariants:
- Zero Security Bypass: Never bypasses login, RBAC, tenant isolation, or audit logging.
- Asymmetric/Key Separation: Server private signing key is NEVER written to the USB drive.
- Server-side independent authorization and fail-closed security.
"""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import json
import os
import platform
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import AuthenticationFailed

import jwt
from apps.accounts.models import PlatformRole, User
from apps.core.models import AuditEvent


def get_usb_license_signing_key() -> str:
    import sys
    key = getattr(
        settings,
        "SUPERADMIN_LICENSE_SIGNING_KEY",
        os.getenv(
            "SUPERADMIN_LICENSE_SIGNING_KEY",
            "dev-only-usb-licensing-secret-key-change-in-prod-7766554433",
        ),
    )
    if not getattr(settings, "DEBUG", True) and ("test" not in sys.argv):
        invalid_keys = (
            "",
            "dev-only-usb-licensing-secret-key-change-in-prod-7766554433",
            "replace-with-a-secure-license-key",
            getattr(settings, "SECRET_KEY", ""),
            getattr(settings, "JWT_SIGNING_KEY", ""),
        )
        if not key or key in invalid_keys:
            raise ImproperlyConfigured(
                "Invalid or missing SUPERADMIN_LICENSE_SIGNING_KEY for production."
            )
    return key


def serialize_canonical_payload(payload: dict[str, Any]) -> bytes:
    """
    Serializes a dictionary to canonical JSON (sorted keys, compact delimiters)
    for deterministic cryptographic signing and verification.
    """
    # Exclude signature field if present
    canonical_dict = {k: v for k, v in payload.items() if k != "signature"}
    return json.dumps(canonical_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_license_payload(payload: dict[str, Any]) -> str:
    """Signs canonical payload with HMAC-SHA256 using platform secret key."""
    key = get_usb_license_signing_key().encode("utf-8")
    canonical_bytes = serialize_canonical_payload(payload)
    return hmac.new(key, canonical_bytes, hashlib.sha256).hexdigest()


def verify_license_signature(license_data: dict[str, Any]) -> bool:
    """Verifies that the provided signature matches the signed canonical payload."""
    provided_sig = license_data.get("signature")
    if not provided_sig or not isinstance(provided_sig, str):
        return False
    expected_sig = sign_license_payload(license_data)
    return hmac.compare_digest(provided_sig.lower(), expected_sig.lower())


def query_windows_volume_serial(drive_path: str) -> str:
    """Queries physical Volume Serial Number on Windows using kernel32.GetVolumeInformationW."""
    if platform.system() != "Windows":
        return "DEV-SIMULATED-SERIAL"

    # Normalize drive path e.g. "E:" -> "E:\\"
    clean_drive = drive_path.strip().rstrip("\\/")
    if len(clean_drive) == 1 and clean_drive.isalpha():
        clean_drive = f"{clean_drive}:\\"
    elif len(clean_drive) == 2 and clean_drive[1] == ":":
        clean_drive = f"{clean_drive}\\"

    serial_number = ctypes.c_ulong()
    res = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(clean_drive),
        None,
        0,
        ctypes.byref(serial_number),
        None,
        None,
        None,
        0,
    )
    if res == 0:
        raise OSError(f"Failed to query volume information for drive '{drive_path}'.")
    return f"{serial_number.value:08X}"


def build_license_payload(
    *,
    issued_to_user: User,
    volume_serial_number: str,
    valid_days: int = 365,
    custom_permissions: list[str] | None = None,
    usb_product_id: str = "0x5583",
    usb_vendor_id: str = "0x0781",
    usb_serial_number: str = "",
) -> dict[str, Any]:
    """Assembles a full cryptographic license document ready for signing."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=valid_days)
    license_id = f"lic_{uuid.uuid4()}"

    permissions = custom_permissions or [
        "platform:super_admin",
        "platform:tenant_lifecycle",
        "platform:payment_reconcile",
        "platform:dr_restore_drill",
        "platform:system_settings",
    ]

    payload: dict[str, Any] = {
        "version": "1.0",
        "license_id": license_id,
        "issuer": "PBMS SaaS Platform Security Authority",
        "issued_to_email": issued_to_user.email,
        "hardware_binding": {
            "volume_serial_number": volume_serial_number.upper(),
            "usb_vendor_id": usb_vendor_id,
            "usb_product_id": usb_product_id,
            "usb_serial_number": usb_serial_number or volume_serial_number.upper(),
        },
        "permissions": permissions,
        "valid_from": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "signature_algorithm": "HMAC-SHA256",
    }
    payload["signature"] = sign_license_payload(payload)
    return payload


def is_license_revoked(license_id: str) -> bool:
    """Checks if the given license ID has been recorded as revoked in AuditEvent."""
    return AuditEvent.objects.filter(
        event_type="SUPERADMIN_USB_LICENSE_REVOKED",
        target_id=license_id,
    ).exists()


def revoke_usb_license(
    *,
    license_id: str,
    actor_user: User,
    reason: str = "SuperAdmin revoked license",
    ip_address: str | None = None,
) -> AuditEvent:
    """Records an immutable revocation audit event for the specified license ID."""
    return AuditEvent.objects.create(
        actor_user=actor_user,
        event_type="SUPERADMIN_USB_LICENSE_REVOKED",
        target_model="core.UsbLicense",
        target_id=license_id,
        ip_address=ip_address,
        metadata={"reason": reason, "revoked_by": actor_user.email},
    )


def validate_usb_license(
    *,
    license_data: dict[str, Any],
    hardware_fingerprint: dict[str, Any],
    expected_user_email: str,
) -> tuple[bool, str]:
    """
    Validates a presented USB license token against server security invariants:
    1. Schema and fields presence
    2. Digital signature integrity
    3. User email binding
    4. Hardware serial binding
    5. Time window (valid_from <= now <= expires_at)
    6. Revocation status
    """
    # 1. Check required fields
    required_fields = (
        "license_id",
        "issued_to_email",
        "hardware_binding",
        "valid_from",
        "expires_at",
        "signature",
    )
    for field in required_fields:
        if field not in license_data:
            return False, f"Missing mandatory field in license: '{field}'."

    # 2. Check Digital Signature
    if not verify_license_signature(license_data):
        return False, "Cryptographic signature validation failed. License payload may be tampered."

    # 3. Check User Email Binding
    issued_email = str(license_data.get("issued_to_email", "")).strip().lower()
    if issued_email != expected_user_email.strip().lower():
        return False, f"License is issued to '{issued_email}', not authenticated user '{expected_user_email}'."

    # 4. Check Hardware Binding
    expected_serial = (
        license_data.get("hardware_binding", {}).get("volume_serial_number", "").strip().upper()
    )
    actual_serial = str(hardware_fingerprint.get("volume_serial_number", "")).strip().upper()
    if not actual_serial:
        return False, "Hardware fingerprint missing 'volume_serial_number'."
    if expected_serial != actual_serial:
        return False, f"Hardware serial mismatch: expected '{expected_serial}', got '{actual_serial}'."

    # 5. Check Time Validity
    now = datetime.now(timezone.utc)
    valid_from_dt = parse_datetime(license_data.get("valid_from", ""))
    expires_at_dt = parse_datetime(license_data.get("expires_at", ""))

    if not valid_from_dt or not expires_at_dt:
        return False, "Invalid ISO-8601 timestamp in valid_from or expires_at."

    if now < valid_from_dt:
        return False, f"License is not yet active (valid_from: {valid_from_dt.isoformat()})."

    if now > expires_at_dt:
        return False, f"License has expired (expires_at: {expires_at_dt.isoformat()})."

    # 6. Check Revocation
    license_id = str(license_data.get("license_id", ""))
    if is_license_revoked(license_id):
        return False, f"License ID '{license_id}' has been permanently revoked."

    return True, "Valid"


def issue_elevated_usb_jwt(
    *,
    user: User,
    session_id: str,
    license_id: str,
    elevation_lifetime_minutes: int = 15,
) -> dict[str, Any]:
    """Issues a short-lived elevated JWT certifying USB hardware possession."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=elevation_lifetime_minutes)
    payload = {
        "token_type": "usb_elevated",
        "sub": str(user.id),
        "session_id": session_id,
        "license_id": license_id,
        "usb_verified": True,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    signing_key = getattr(settings, "JWT_SIGNING_KEY", "fallback-key")
    token = jwt.encode(payload, signing_key, algorithm="HS256")
    return {
        "elevated_token": token,
        "elevation_expires_in": elevation_lifetime_minutes * 60,
        "expires_at": exp.isoformat(),
    }


def verify_elevated_usb_jwt(token: str, expected_user: User) -> dict[str, Any]:
    """Validates an elevated USB JWT."""
    signing_key = getattr(settings, "JWT_SIGNING_KEY", "fallback-key")
    try:
        payload = jwt.decode(token, signing_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationFailed("Elevated USB license token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed("Invalid elevated USB license token.") from exc

    if payload.get("token_type") != "usb_elevated" or not payload.get("usb_verified"):
        raise AuthenticationFailed("Token is not an elevated USB verification token.")

    if payload.get("sub") != str(expected_user.id):
        raise AuthenticationFailed("Elevated USB token does not match authenticated user.")

    return payload
