from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.dependencies import get_auth_service, get_current_user_context
from app.auth.domain.schemas import (
    TokenResponseSchema,
    UserCreateSchema,
    UserLoginSchema,
    UserResponseSchema,
)
from app.auth.services.auth_service import AuthService
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register", response_model=UserResponseSchema, status_code=status.HTTP_201_CREATED
)
def register(
    payload: UserCreateSchema, auth_service: AuthService = Depends(get_auth_service)
):
    """
    Register a new user account canonicalizing their email and enforcing credentials checks.
    """
    user = auth_service.register_user(payload.email, payload.password)
    return user


@router.post("/login", response_model=TokenResponseSchema)
def login(
    response: Response,
    request: Request,
    payload: UserLoginSchema,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Authenticate user credentials and configure secure HTTP-only refresh cookies.
    """
    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None

    # Authenticate credentials
    user = auth_service.authenticate_user(payload.email, payload.password)

    # Establish session
    access_token, refresh_token = auth_service.create_session(
        user_id=user.id, user_agent=user_agent, ip_address=ip_address
    )

    # Configure secure browser cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=refresh_token,
        max_age=settings.COOKIE_MAX_AGE,
        expires=settings.COOKIE_MAX_AGE,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )

    return {
        "access_token": access_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/refresh", response_model=TokenResponseSchema)
def refresh(
    response: Response,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Rotate the session, returning a new access token and setting a new refresh token cookie.
    """
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session refresh cookie is missing",
        )

    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None

    access_token, new_refresh_token = auth_service.refresh_session(
        raw_refresh_token=token, user_agent=user_agent, ip_address=ip_address
    )

    # Configure rotated cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=new_refresh_token,
        max_age=settings.COOKIE_MAX_AGE,
        expires=settings.COOKIE_MAX_AGE,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )

    return {
        "access_token": access_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout")
def logout(
    response: Response,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Terminate user session and clear browser session cookies.
    """
    token = request.cookies.get(settings.COOKIE_NAME)
    if token:
        auth_service.revoke_session(token)

    # Instruct client browser to clear cookies
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponseSchema)
def get_me(
    current_user: dict[str, Any] = Depends(get_current_user_context),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Retrieve profile details for the currently authenticated user.
    """
    user_id = UUID(current_user["user_id"])
    user = auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account no longer exists",
        )
    return user
