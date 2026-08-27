from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.dependencies import (
    check_account_delete_rate_limit,
    check_rate_limit,
    get_auth_service,
    get_current_user_context,
    get_login_failed_attempts_tracker,
    get_oauth_service,
)
from app.auth.domain.schemas import (
    DeleteAccountSchema,
    TokenResponseSchema,
    UserCreateSchema,
    UserLoginSchema,
    UserResponseSchema,
)
from app.auth.services.auth_service import AuthService
from app.auth.services.oauth_service import OAuthService
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ── OAuth state cookie name (short-lived CSRF token) ──────────────────────────
_OAUTH_STATE_COOKIE = "oauth_state"


@router.post(
    "/register",
    response_model=UserResponseSchema,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_rate_limit)],
)
async def register(
    payload: UserCreateSchema, auth_service: AuthService = Depends(get_auth_service)
):
    """
    Register a new user account canonicalizing their email and enforcing credentials checks.
    """
    user = await auth_service.register_user(payload.email, payload.password)
    return user


@router.post(
    "/login",
    response_model=TokenResponseSchema,
    dependencies=[Depends(check_rate_limit)],
)
async def login(
    response: Response,
    request: Request,
    payload: UserLoginSchema,
    auth_service: AuthService = Depends(get_auth_service),
    failed_tracker: Any = Depends(get_login_failed_attempts_tracker),
):
    """
    Authenticate user credentials and configure secure HTTP-only refresh cookies.
    Enforces a 5-attempt brute-force lockout on consecutive failed login attempts.
    """
    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None

    # Check brute-force lockout for failed credentials
    ip = ip_address or "unknown"
    email_norm = payload.email.strip().lower()
    lockout_key = f"ip:{ip}:email:{email_norm}"

    if await failed_tracker.is_locked_out(lockout_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait 5 minutes before trying again.",
        )

    # Authenticate credentials (recording failed attempts on failure, clearing on success)
    try:
        user = await auth_service.authenticate_user(payload.email, payload.password)
    except Exception:
        await failed_tracker.record_failed_attempt(lockout_key)
        raise

    await failed_tracker.reset(lockout_key)

    # Establish session
    access_token, refresh_token = await auth_service.create_session(
        user_id=user.id, user_agent=user_agent, ip_address=ip_address
    )

    # Configure secure browser cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=refresh_token,
        max_age=settings.COOKIE_MAX_AGE,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )

    return {
        "access_token": access_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post(
    "/refresh",
    response_model=TokenResponseSchema,
    dependencies=[Depends(check_rate_limit)],
)
async def refresh(
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

    access_token, new_refresh_token = await auth_service.refresh_session(
        raw_refresh_token=token, user_agent=user_agent, ip_address=ip_address
    )

    # Configure rotated cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=new_refresh_token,
        max_age=settings.COOKIE_MAX_AGE,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )

    return {
        "access_token": access_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout", dependencies=[Depends(check_rate_limit)])
async def logout(
    response: Response,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Terminate user session and clear browser session cookies.
    """
    token = request.cookies.get(settings.COOKIE_NAME)
    if token:
        await auth_service.revoke_session(token)

    # Instruct client browser to clear cookies
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponseSchema)
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_user_context),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Retrieve profile details for the currently authenticated user.
    """
    user_id = UUID(current_user["user_id"])
    user = await auth_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account no longer exists",
        )
    return user


@router.delete(
    "/account",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_account_delete_rate_limit)],
)
async def delete_account(
    response: Response,
    payload: DeleteAccountSchema,
    current_user: dict[str, Any] = Depends(get_current_user_context),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Permanently delete the authenticated user's account.

    Requires the account password to be re-entered so a stolen access token
    alone cannot destroy the account (account-takeover protection), and
    rate-limits attempts per user so the re-entry field cannot be
    brute-forced. The database ON DELETE CASCADE constraints remove the
    user's sessions, conversations, and documents. The client's refresh
    cookie is cleared so the browser no longer holds a stale session.
    """
    user_id = UUID(current_user["user_id"])
    await auth_service.verify_user_password(user_id, payload.password)
    await auth_service.delete_user(user_id)

    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )


# ── Google OAuth ───────────────────────────────────────────────────────────────


@router.get("/oauth/google", tags=["OAuth"])
def google_oauth_initiate(response: Response):
    """
    Redirect the user to Google's consent page.

    A short-lived HttpOnly state cookie is set for CSRF protection.
    """
    import secrets
    import urllib.parse

    state = secrets.token_urlsafe(32)
    callback_url = (
        f"{settings.OAUTH_REDIRECT_BASE_URL}"
        f"{settings.API_V1_STR}/auth/oauth/google/callback"
    )
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    google_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    )

    redirect = RedirectResponse(url=google_url, status_code=302)
    # Store state in a short-lived HttpOnly cookie for CSRF validation
    redirect.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,  # 10 minutes — enough time for user to approve
        path=settings.API_V1_STR + "/auth",
        domain=settings.COOKIE_DOMAIN or None,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    return redirect


@router.get("/oauth/google/callback", tags=["OAuth"])
async def google_oauth_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    oauth_service: OAuthService = Depends(get_oauth_service),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Handle Google's redirect after user consent.

    Validates the CSRF state, exchanges the authorization code, upserts the
    user, creates a session, and redirects to the frontend with the access token.
    """
    frontend_base = settings.FRONTEND_URL

    # ── Error from Google ──────────────────────────────────────────────────────
    if error:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error={error}",
            status_code=302,
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error=missing_params",
            status_code=302,
        )

    # ── CSRF state validation ──────────────────────────────────────────────────
    stored_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    if not stored_state or stored_state != state:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error=invalid_state",
            status_code=302,
        )

    # ── Exchange code → user ───────────────────────────────────────────────────
    try:
        user = await oauth_service.exchange_google_code(code=code, state=state)
    except Exception:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error=exchange_failed",
            status_code=302,
        )

    # ── Create session ─────────────────────────────────────────────────────────
    try:
        user_agent = request.headers.get("User-Agent")
        ip_address = request.client.host if request.client else None
        access_token, refresh_token = await auth_service.create_session(
            user_id=user.id, user_agent=user_agent, ip_address=ip_address
        )
    except Exception:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error=session_failed",
            status_code=302,
        )

    # ── Redirect to frontend cleanly with access_token fragment for cross-origin SPAs ───
    redirect = RedirectResponse(
        url=f"{frontend_base}/oauth/callback#token={access_token}",
        status_code=302,
    )

    # Set the long-lived refresh cookie
    redirect.set_cookie(
        key=settings.COOKIE_NAME,
        value=refresh_token,
        max_age=settings.COOKIE_MAX_AGE,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    # Clear the CSRF state cookie
    redirect.delete_cookie(
        key=_OAUTH_STATE_COOKIE,
        path=settings.API_V1_STR + "/auth",
        domain=settings.COOKIE_DOMAIN or None,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    return redirect


# ── GitHub OAuth ───────────────────────────────────────────────────────────────


@router.get("/oauth/github", tags=["OAuth"])
def github_oauth_initiate(
    response: Response,
    oauth_service: OAuthService = Depends(get_oauth_service),
):
    """
    Redirect the user to GitHub's consent page.

    A short-lived HttpOnly state cookie is set for CSRF protection.
    """
    github_url, state = oauth_service.get_github_authorization_url()

    redirect = RedirectResponse(url=github_url, status_code=302)
    # Store state in a short-lived HttpOnly cookie for CSRF validation
    redirect.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,  # 10 minutes — enough time for user to approve
        path=settings.API_V1_STR + "/auth",
        domain=settings.COOKIE_DOMAIN or None,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    return redirect


@router.get("/oauth/github/callback", tags=["OAuth"])
async def github_oauth_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    oauth_service: OAuthService = Depends(get_oauth_service),
    auth_service: AuthService = Depends(get_auth_service),
):
    """
    Handle GitHub's redirect after user consent.

    Validates the CSRF state, exchanges the authorization code, upserts the
    user, creates a session, and redirects to the frontend with the access token.
    """
    frontend_base = settings.FRONTEND_URL

    # ── Error from GitHub ──────────────────────────────────────────────────────
    if error:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error={error}",
            status_code=302,
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error=missing_params",
            status_code=302,
        )

    # ── CSRF state validation ──────────────────────────────────────────────────
    stored_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    if not stored_state or stored_state != state:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error=invalid_state",
            status_code=302,
        )

    # ── Exchange code → user ───────────────────────────────────────────────────
    try:
        user = await oauth_service.exchange_github_code(code=code, state=state)
    except Exception:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error=exchange_failed",
            status_code=302,
        )

    # ── Create session ─────────────────────────────────────────────────────────
    try:
        user_agent = request.headers.get("User-Agent")
        ip_address = request.client.host if request.client else None
        access_token, refresh_token = await auth_service.create_session(
            user_id=user.id, user_agent=user_agent, ip_address=ip_address
        )
    except Exception:
        return RedirectResponse(
            url=f"{frontend_base}/login?oauth_error=session_failed",
            status_code=302,
        )

    # ── Redirect to frontend cleanly with access_token fragment for cross-origin SPAs ───
    redirect = RedirectResponse(
        url=f"{frontend_base}/oauth/callback#token={access_token}",
        status_code=302,
    )

    # Set the long-lived refresh cookie
    redirect.set_cookie(
        key=settings.COOKIE_NAME,
        value=refresh_token,
        max_age=settings.COOKIE_MAX_AGE,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    # Clear the CSRF state cookie
    redirect.delete_cookie(
        key=_OAUTH_STATE_COOKIE,
        path=settings.API_V1_STR + "/auth",
        domain=settings.COOKIE_DOMAIN or None,
        secure=settings.COOKIE_SECURE,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
    )
    return redirect
