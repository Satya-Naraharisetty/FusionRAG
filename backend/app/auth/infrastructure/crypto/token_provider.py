import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.auth.domain.interfaces import TokenProvider
from app.core.config import settings


class JWTTokenProvider(TokenProvider):
    def __init__(self) -> None:
        self._secret = settings.JWT_SECRET
        self._algorithm = settings.JWT_ALGORITHM
        self._access_expiry = settings.ACCESS_TOKEN_EXPIRE_MINUTES

    def create_access_token(self, claims: dict[str, Any]) -> str:
        """
        Create a cryptographically signed JWT access token.
        """
        payload = claims.copy()
        now = datetime.now(UTC)
        payload["iat"] = int(now.timestamp())
        payload["exp"] = int((now + timedelta(minutes=self._access_expiry)).timestamp())
        payload["iss"] = settings.PROJECT_NAME
        if "aud" not in payload:
            payload["aud"] = settings.PROJECT_NAME
        if "jti" not in payload:
            payload["jti"] = secrets.token_hex(16)

        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def create_refresh_token(self, claims: dict[str, Any] | None = None) -> str:
        """
        Create a cryptographically secure random refresh token string (URL-safe).
        """
        # Refresh tokens are random strings, stored hashed on the server.
        return secrets.token_urlsafe(32)

    def decode_token(self, token: str) -> dict[str, Any]:
        """
        Decode and verify a JWT token signature and claims.
        """
        return jwt.decode(
            token,
            self._secret,
            algorithms=[self._algorithm],
            audience=settings.PROJECT_NAME,
            issuer=settings.PROJECT_NAME,
        )
