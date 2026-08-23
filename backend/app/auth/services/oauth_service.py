"""
OAuthService — handles the Google OAuth 2.0 Authorization Code Flow.

Flow:
  1. get_google_authorization_url() / get_github_authorization_url()  → builds consent URL + state
  2. exchange_*_code()  → exchanges code for profile via httpx.AsyncClient, upserts user, returns UserDomain.
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

# ─── GitHub OAuth endpoints ────────────────────────────────────────────────────
_GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_GITHUB_USERINFO_URL = "https://api.github.com/user"
_GITHUB_EMAILS_URL = "https://api.github.com/user/emails"
_GITHUB_SCOPES = "read:user user:email"


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
        }

        url = f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return url, state

    def get_github_authorization_url(self) -> tuple[str, str]:
        """
        Return ``(authorization_url, state)`` for the GitHub consent page.

        The caller must store *state* in a short-lived HttpOnly cookie and
        validate it when GitHub redirects back.
        """
        state = secrets.token_urlsafe(32)
        callback_url = (
            f"{settings.OAUTH_REDIRECT_BASE_URL}"
            f"{settings.API_V1_STR}/auth/oauth/github/callback"
        )
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": callback_url,
            "scope": _GITHUB_SCOPES,
            "state": state,
        }
        url = f"{_GITHUB_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return url, state

    # ── 2. Exchange code → upsert user ────────────────────────────────────────

    async def exchange_google_code(self, code: str, state: str) -> UserDomain:
        """
        Exchange the authorization *code* for a Google profile, then upsert
        and return the local user record.

        Raises ``InvalidCredentialsException`` on any provider-level error.
        """
        try:
            profile = await self._fetch_google_profile(code)
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

        return await self._upsert_user(provider="google", sub=sub, email=email)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _fetch_google_profile(self, code: str) -> dict:
        """Exchange authorization code for an access token, then fetch profile."""
        callback_url = (
            f"{settings.OAUTH_REDIRECT_BASE_URL}"
            f"{settings.API_V1_STR}/auth/oauth/google/callback"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            # Step 1: exchange code → tokens
            token_resp = await client.post(
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
            profile_resp = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            profile_resp.raise_for_status()
            return profile_resp.json()

    async def exchange_github_code(self, code: str, state: str) -> UserDomain:
        """
        Exchange the authorization *code* for a GitHub profile, then upsert
        and return the local user record.

        Raises ``InvalidCredentialsException`` on any provider-level error.
        """
        try:
            profile = await self._fetch_github_profile(code)
        except Exception as exc:
            logger.warning("GitHub OAuth token exchange failed: %s", exc)
            raise InvalidCredentialsException(
                "Failed to authenticate with GitHub. Please try again."
            )

        github_id = profile.get("id")
        if github_id is None:
            raise InvalidCredentialsException("GitHub did not return a valid user ID.")
        sub = str(github_id)
        email = profile.get("email")

        if not email:
            raise InvalidCredentialsException(
                "GitHub did not return a valid email address."
            )

        return await self._upsert_user(provider="github", sub=sub, email=email)

    async def _fetch_github_profile(self, code: str) -> dict:
        """Exchange authorization code for an access token, then fetch profile and emails."""
        callback_url = (
            f"{settings.OAUTH_REDIRECT_BASE_URL}"
            f"{settings.API_V1_STR}/auth/oauth/github/callback"
        )
        headers = {
            "Accept": "application/json",
            "User-Agent": "Hybrid-RAG-Chatbot",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            # Step 1: exchange code → tokens
            token_resp = await client.post(
                _GITHUB_TOKEN_URL,
                headers=headers,
                data={
                    "code": code,
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "redirect_uri": callback_url,
                },
            )
            token_resp.raise_for_status()
            resp_data = token_resp.json()

            if "error" in resp_data:
                error_msg = resp_data.get("error_description") or resp_data["error"]
                raise InvalidCredentialsException(
                    f"GitHub token exchange error: {error_msg}"
                )

            access_token: str = resp_data["access_token"]

            # Step 2: fetch user profile
            profile_headers = {
                **headers,
                "Authorization": f"Bearer {access_token}",
            }
            profile_resp = await client.get(
                _GITHUB_USERINFO_URL,
                headers=profile_headers,
            )
            profile_resp.raise_for_status()
            profile = profile_resp.json()

            # Step 3: fetch emails (in case primary email is private)
            emails_resp = await client.get(
                _GITHUB_EMAILS_URL,
                headers=profile_headers,
            )
            if emails_resp.status_code == 200:
                emails = emails_resp.json()
                extracted_email = None

                # 1. Look for primary & verified
                for entry in emails:
                    if entry.get("primary") and entry.get("verified"):
                        extracted_email = entry.get("email")
                        break

                # 2. Look for primary
                if not extracted_email:
                    for entry in emails:
                        if entry.get("primary"):
                            extracted_email = entry.get("email")
                            break

                # 3. Look for verified
                if not extracted_email:
                    for entry in emails:
                        if entry.get("verified"):
                            extracted_email = entry.get("email")
                            break

                # 4. Fallback to first email
                if not extracted_email and emails:
                    extracted_email = emails[0].get("email")

                if extracted_email:
                    profile["email"] = extracted_email.strip().lower()

            if "email" in profile and profile["email"]:
                profile["email"] = profile["email"].strip().lower()

            return profile

    async def _upsert_user(self, provider: str, sub: str, email: str) -> UserDomain:
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
            user = await self._user_repo.get_by_oauth_sub(provider, sub)

            if user:
                # Touch updated_at so the DB record stays fresh
                updated = UserDomain(
                    **{
                        **user.model_dump(),
                        "updated_at": now,
                    }
                )
                saved = await self._user_repo.save(updated)
                await self._uow.commit()
                return saved

            # 2. Look up by email (merge with existing account)
            user = await self._user_repo.get_by_email(email)
            if user:
                updated = UserDomain(
                    **{
                        **user.model_dump(),
                        "oauth_provider": provider,
                        "oauth_sub": sub,
                        "updated_at": now,
                    }
                )
                saved = await self._user_repo.save(updated)
                await self._uow.commit()
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
            saved = await self._user_repo.save(new_user)
            await self._uow.commit()
            return saved

        except Exception:
            await self._uow.rollback()
            raise
