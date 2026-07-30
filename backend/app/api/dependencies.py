from typing import Any, Dict
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.auth.domain.interfaces import TokenProvider
from app.auth.infrastructure.crypto.password_hasher import Argon2PasswordHasher
from app.auth.infrastructure.crypto.token_provider import JWTTokenProvider
from app.auth.infrastructure.persistence.repositories.session_repository import (
    SQLAlchemySessionRepository,
)
from app.auth.infrastructure.persistence.repositories.user_repository import (
    SQLAlchemyUserRepository,
)
from app.auth.infrastructure.providers import (
    SQLAlchemyUnitOfWork,
    SystemTimeProvider,
    SystemUUIDGenerator,
)
from app.auth.services.auth_service import AuthService
from app.db.session import get_db

# Security header scheme helper
security_scheme = HTTPBearer(auto_error=False)


def get_token_provider() -> TokenProvider:
    return JWTTokenProvider()


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """
    Composition Root for Dependency Injection.
    Wires domain interfaces to concrete infrastructure implementations.
    """
    user_repo = SQLAlchemyUserRepository(db)
    session_repo = SQLAlchemySessionRepository(db)
    hasher = Argon2PasswordHasher()
    token_provider = JWTTokenProvider()
    time_provider = SystemTimeProvider()
    uuid_generator = SystemUUIDGenerator()
    uow = SQLAlchemyUnitOfWork(db)

    return AuthService(
        user_repo=user_repo,
        session_repo=session_repo,
        hasher=hasher,
        token_provider=token_provider,
        time_provider=time_provider,
        uuid_generator=uuid_generator,
        uow=uow,
    )


class AuthenticationGuard:
    def __init__(
        self, token_provider: TokenProvider | None = None
    ) -> None:
        self._token_provider = token_provider or JWTTokenProvider()

    async def __call__(
        self,
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    ) -> Dict[str, Any]:
        """
        Stateless authentication check. Signature verified in-memory.
        """
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        token = credentials.credentials
        try:
            claims = self._token_provider.decode_token(token)
            return claims
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError) as e:
            import logging
            logging.getLogger(__name__).warning(f"JWT Verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
            )


async def get_current_user_context(
    claims: Dict[str, Any] = Depends(AuthenticationGuard()),
) -> Dict[str, Any]:
    """
    CurrentUserProvider implementation.
    Extracts user details from claims context.
    """
    user_id = claims.get("sub")
    role = claims.get("role")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing subject identity",
        )
    return {"user_id": user_id, "role": role}
