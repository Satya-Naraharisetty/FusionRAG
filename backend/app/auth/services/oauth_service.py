"""
OAuthService — handles the Google OAuth 2.0 Authorization Code Flow.

Flow:
  1. get_authorization_url()  → builds the Google consent URL + state cookie value
  2. exchange_code()          → exchanges the auth code for a profile, upserts the
                                user in the DB (merging by email when an account
                                already exists), and returns the UserDomain.
"""

import logging
import secrets
import urllib.parse

import httpx

from app.auth.domain.exceptions import InvalidCredentialsException
from app.auth.domain.interfaces import (
    TimeProvider,
    UnitOfWork,
    UserRepository,
    UUIDGenerator,
)
from app.auth.domain.schemas import UserDomain
from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Google OAuth endpoints ────────────────────────────────────────────────────
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_GOOGLE_SCOPES = "openid email profile"


class OAuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        time_provider: TimeProvider,
        uuid_generator: UUIDGenerator,
        uow: UnitOfWork,
    ) -> None:
        self._user_repo = user_repo
        self._time_provider = time_provider
        self._uuid_generator = uuid_generator
        self._uow = uow

    # ── 1. Build consent-page URL ──────────────────────────────────────────────

    def get_google_authorization_url(self) -> tuple[str, str]:
        """
        Return ``(authorization_url, state)`` for the Google consent page.

        The caller must store *state* in a short-lived HttpOnly cookie and
        validate it when Google redirects back.
        """
        state = secrets.token_urlsafe(32)
        callback_url = (
            f"{settings.OAUTH_REDIRECT_BASE_URL}"
            f"{settings.API_V1_STR}/auth/oauth/google/callback"
        )
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": _GOOGLE_SCOPES,
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }
        url = f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return url, state

    # ── 2. Exchange code → upsert user ────────────────────────────────────────

    def exchange_google_code(self, code: str, state: str) -> UserDomain:
        """
        Exchange the authorization *code* for a Google profile, then upsert
        and return the local user record.

        Raises ``InvalidCredentialsException`` on any provider-level error.
        """
        try:
            profile = self._fetch_google_profile(code)
        except Exception as exc:
            logger.warning("Google OAuth token exchange failed: %s", exc)
            raise InvalidCredentialsException(
                "Failed to authenticate with Google. Please try again."
            )

        sub: str = profile.get("sub", "")
        email: str = (profile.get("email") or "").strip().lower()

        if not sub or not email:
            raise InvalidCredentialsException(
                "Google did not return a valid email address."
            )

        return self._upsert_user(provider="google", sub=sub, email=email)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fetch_google_profile(self, code: str) -> dict:
        """Exchange authorization code for an access token, then fetch profile."""
        callback_url = (
            f"{settings.OAUTH_REDIRECT_BASE_URL}"
            f"{settings.API_V1_STR}/auth/oauth/google/callback"
        )
        with httpx.Client(timeout=10) as client:
            # Step 1: exchange code → tokens
            token_resp = client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": callback_url,
                    "grant_type": "authorization_code",
                },
            )
            token_resp.raise_for_status()
            access_token: str = token_resp.json()["access_token"]

            # Step 2: fetch user profile
            profile_resp = client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            profile_resp.raise_for_status()
            return profile_resp.json()

    def _upsert_user(self, provider: str, sub: str, email: str) -> UserDomain:
        """
        Find an existing user by OAuth sub *or* by email, then create or update.

        Merge strategy (in order):
          1. Exact (provider, sub) match → update last_seen fields, return.
          2. Email match (existing email/password account) → attach OAuth creds.
          3. No match → create a new OAuth-only account.
        """
        try:
            now = self._time_provider.get_now()

            # 1. Look up by (provider, sub)
            user = self._user_repo.get_by_oauth_sub(provider, sub)

            if user:
                # Touch updated_at so the DB record stays fresh
                updated = UserDomain(
                    **{
                        **user.model_dump(),
                        "updated_at": now,
                    }
                )
                saved = self._user_repo.save(updated)
                self._uow.commit()
                return saved

            # 2. Look up by email (merge with existing account)
            user = self._user_repo.get_by_email(email)
            if user:
                updated = UserDomain(
                    **{
                        **user.model_dump(),
                        "oauth_provider": provider,
                        "oauth_sub": sub,
                        "updated_at": now,
                    }
                )
                saved = self._user_repo.save(updated)
                self._uow.commit()
                return saved

            # 3. Brand-new OAuth user — no password
            new_user = UserDomain(
                id=self._uuid_generator.generate(),
                email=email,
                hashed_password=None,
                role="user",
                is_active=True,
                created_at=now,
                updated_at=now,
                oauth_provider=provider,
                oauth_sub=sub,
            )
            saved = self._user_repo.save(new_user)
            self._uow.commit()
            return saved

        except Exception:
            self._uow.rollback()
            raise
