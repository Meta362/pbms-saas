from typing import Any
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from apps.accounts.jwt_service import decode_jwt
from apps.accounts.models import AuthSession, User


class PBMSJWTAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[User, AuthSession] | None:
        auth_header = get_authorization_header(request).split()
        if not auth_header:
            return None

        if auth_header[0].decode("utf-8").lower() != self.keyword.lower():
            return None

        if len(auth_header) == 1:
            raise AuthenticationFailed("Invalid Authorization header. No credentials provided.")
        if len(auth_header) > 2:
            raise AuthenticationFailed("Invalid Authorization header. Token string contains spaces.")

        raw_token = auth_header[1].decode("utf-8")
        payload: dict[str, Any] = decode_jwt(raw_token)

        if payload.get("token_type") != "access":
            raise AuthenticationFailed("Invalid token type. Access token required.")

        session_id = payload.get("session_id")
        user_id = payload.get("sub")
        if not session_id or not user_id:
            raise AuthenticationFailed("Token missing required session claims.")

        try:
            session = AuthSession.objects.select_related("user").get(
                id=session_id,
                user_id=user_id,
            )
        except AuthSession.DoesNotExist as exc:
            raise AuthenticationFailed("Session not found.") from exc

        if session.is_revoked or session.expires_at <= timezone.now():
            raise AuthenticationFailed("Session has been revoked or expired.")

        if not session.user.is_active:
            raise AuthenticationFailed("User account is disabled.")

        request.auth_session = session
        return (session.user, session)

    def authenticate_header(self, request: Request) -> str:
        return self.keyword
