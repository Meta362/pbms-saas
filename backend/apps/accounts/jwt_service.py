import hashlib
import os
import uuid
from datetime import timedelta
from typing import Any
import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from apps.accounts.models import AuthSession, User
from apps.core.models import AuditEvent


def _get_signing_key() -> str:
    key = getattr(settings, "JWT_SIGNING_KEY", None) or os.getenv("JWT_SIGNING_KEY")
    if not key:
        if not settings.DEBUG:
            raise ImproperlyConfigured("Invalid or missing JWT_SIGNING_KEY for production.")
        return settings.SECRET_KEY
    if not settings.DEBUG and key == settings.SECRET_KEY:
        raise ImproperlyConfigured("JWT_SIGNING_KEY must be distinct from DJANGO_SECRET_KEY in production.")
    return key


def _get_access_lifetime() -> timedelta:
    minutes = int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "15"))
    return timedelta(minutes=minutes)


def _get_refresh_lifetime() -> timedelta:
    days = int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))
    return timedelta(days=days)


def hash_jti(raw_jti: str) -> str:
    """Returns SHA-256 hex digest of a token JTI."""
    return hashlib.sha256(raw_jti.encode("utf-8")).hexdigest()


def _encode_jwt(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, _get_signing_key(), algorithm="HS256")


def decode_jwt(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _get_signing_key(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationFailed("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed("Invalid authentication token.") from exc


@transaction.atomic
def create_session_and_issue_tokens(
    *,
    user: User,
    ip_address: str | None = None,
    user_agent: str = "",
) -> dict[str, Any]:
    """
    REQ-AUTH-02: Creates a PostgreSQL AuthSession and issues initial Access + Refresh JWTs.
    """
    now = timezone.now()
    access_exp = now + _get_access_lifetime()
    refresh_exp = now + _get_refresh_lifetime()

    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())

    session = AuthSession.objects.create(
        user=user,
        current_refresh_jti_hash=hash_jti(refresh_jti),
        previous_refresh_jti_hash="",
        ip_address=ip_address,
        user_agent=user_agent[:500],
        expires_at=refresh_exp,
    )

    access_payload = {
        "token_type": "access",
        "sub": str(user.id),
        "session_id": str(session.id),
        "jti": access_jti,
        "platform_role": user.platform_role,
        "iat": int(now.timestamp()),
        "exp": int(access_exp.timestamp()),
    }
    refresh_payload = {
        "token_type": "refresh",
        "sub": str(user.id),
        "session_id": str(session.id),
        "jti": refresh_jti,
        "iat": int(now.timestamp()),
        "exp": int(refresh_exp.timestamp()),
    }

    AuditEvent.objects.create(
        actor_user=user,
        event_type="AUTH_LOGIN_SUCCESS",
        target_model="accounts.AuthSession",
        target_id=str(session.id),
        ip_address=ip_address,
    )

    return {
        "access_token": _encode_jwt(access_payload),
        "refresh_token": _encode_jwt(refresh_payload),
        "session_id": str(session.id),
        "expires_in": int(_get_access_lifetime().total_seconds()),
    }


def rotate_refresh_token(
    *,
    raw_refresh_token: str,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """
    REQ-AUTH-02 & REQ-AUTH-03:
    Atomically rotates a valid Refresh Token.
    If reuse of a rotated token is detected, immediately revokes the entire session family
    and commits that revocation to PostgreSQL before raising AuthenticationFailed.
    """
    payload = decode_jwt(raw_refresh_token)
    if payload.get("token_type") != "refresh":
        raise AuthenticationFailed("Invalid token type for refresh.")

    session_id = payload.get("session_id")
    incoming_jti = payload.get("jti")
    if not session_id or not incoming_jti:
        raise AuthenticationFailed("Malformed refresh token claims.")

    incoming_hash = hash_jti(str(incoming_jti))
    now = timezone.now()
    result: dict[str, Any] = {}

    with transaction.atomic():
        try:
            session = (
                AuthSession.objects.select_for_update()
                .select_related("user")
                .get(id=session_id)
            )
        except AuthSession.DoesNotExist as exc:
            raise AuthenticationFailed("Session not found.") from exc

        if session.is_revoked:
            raise AuthenticationFailed("Session has been revoked.")

        if session.expires_at <= now or not session.user.is_active:
            session.is_revoked = True
            session.revoked_at = now
            session.revoked_reason = "SESSION_EXPIRED_OR_USER_INACTIVE"
            session.save(update_fields=["is_revoked", "revoked_at", "revoked_reason", "updated_at"])
            session_unusable = True
        else:
            session_unusable = False

        if not session_unusable and incoming_hash != session.current_refresh_jti_hash:
            session.is_revoked = True
            session.revoked_at = now
            session.revoked_reason = "REFRESH_TOKEN_REUSE_DETECTED"
            session.save(update_fields=["is_revoked", "revoked_at", "revoked_reason", "updated_at"])

            AuditEvent.objects.create(
                actor_user=session.user,
                event_type="AUTH_REFRESH_REUSE_DETECTED",
                target_model="accounts.AuthSession",
                target_id=str(session.id),
                ip_address=ip_address,
                metadata={"reused_jti_hash_prefix": incoming_hash[:12]},
            )
            reuse_detected = True
        else:
            reuse_detected = False

        if not session_unusable and not reuse_detected:
            new_access_jti = str(uuid.uuid4())
            new_refresh_jti = str(uuid.uuid4())
            access_exp = now + _get_access_lifetime()
            refresh_exp = now + _get_refresh_lifetime()

            session.previous_refresh_jti_hash = session.current_refresh_jti_hash
            session.current_refresh_jti_hash = hash_jti(new_refresh_jti)
            session.expires_at = refresh_exp
            session.save(
                update_fields=[
                    "previous_refresh_jti_hash",
                    "current_refresh_jti_hash",
                    "expires_at",
                    "updated_at",
                ]
            )

            access_payload = {
                "token_type": "access",
                "sub": str(session.user.id),
                "session_id": str(session.id),
                "jti": new_access_jti,
                "platform_role": session.user.platform_role,
                "iat": int(now.timestamp()),
                "exp": int(access_exp.timestamp()),
            }
            refresh_payload = {
                "token_type": "refresh",
                "sub": str(session.user.id),
                "session_id": str(session.id),
                "jti": new_refresh_jti,
                "iat": int(now.timestamp()),
                "exp": int(refresh_exp.timestamp()),
            }

            result = {
                "access_token": _encode_jwt(access_payload),
                "refresh_token": _encode_jwt(refresh_payload),
                "session_id": str(session.id),
                "expires_in": int(_get_access_lifetime().total_seconds()),
            }

    if session_unusable:
        raise AuthenticationFailed("Session expired or user inactive.")
    if reuse_detected:
        raise AuthenticationFailed("Refresh token reuse detected. Session family revoked.")

    return result
