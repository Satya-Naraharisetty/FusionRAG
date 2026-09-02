#!/usr/bin/env python3
"""
create_admin.py
Utility script to create or promote an admin account in FusionRAG.

Secrets are NOT hardcoded. Credentials can be passed via:
  1. CLI arguments: --email and --password
  2. Environment variables: ADMIN_EMAIL and ADMIN_PASSWORD
  3. Interactive prompt (getpass) if not provided.

Usage:
  # Interactive mode (prompts for email & password securely):
  uv run python scripts/create_admin.py

  # Using environment variables from .env:
  uv run python scripts/create_admin.py --from-env

  # Explicit CLI arguments (e.g. in CI or provisioning scripts):
  uv run python scripts/create_admin.py --email admin@example.com --password "SecureSecret123!"
"""

import argparse
import asyncio
import getpass
import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.auth.infrastructure.crypto.password_hasher import (  # noqa: E402
    Argon2PasswordHasher,
)
from app.auth.infrastructure.persistence.models import (  # noqa: E402
    SQLAlchemyUser,
)
from app.core.config import settings  # noqa: E402
from app.db.session import init_postgres_engine  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("create_admin")


async def create_or_update_admin(
    email: str, password: str | None = None, update_password_if_exists: bool = True
) -> None:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError(f"Invalid email address: '{email}'")

    engine = init_postgres_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    hasher = Argon2PasswordHasher()

    async with session_factory() as session:
        try:
            stmt = select(SQLAlchemyUser).where(SQLAlchemyUser.email == email)
            result = await session.execute(stmt)
            existing_user = result.scalar_one_or_none()

            if existing_user:
                logger.info("Found existing user with email: %s", email)
                existing_user.role = "admin"
                existing_user.is_active = True
                existing_user.is_verified = True
                existing_user.updated_at = datetime.now(UTC)

                if password and update_password_if_exists:
                    existing_user.hashed_password = hasher.hash(password)
                    logger.info("Updated password for admin user: %s", email)

                await session.commit()
                logger.info(
                    "User '%s' is now configured as active verified admin (ID: %s).",
                    email,
                    existing_user.id,
                )
            else:
                if not password:
                    raise ValueError(
                        f"A password is required to create a new admin account for '{email}'."
                    )

                hashed_password = hasher.hash(password)
                new_user = SQLAlchemyUser(
                    id=uuid.uuid4(),
                    email=email,
                    hashed_password=hashed_password,
                    role="admin",
                    is_active=True,
                    is_verified=True,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.add(new_user)
                await session.commit()
                logger.info(
                    "Created new active verified admin account: %s (ID: %s)",
                    email,
                    new_user.id,
                )
        except Exception as e:
            await session.rollback()
            logger.error("Failed to create/update admin user: %s", e)
            raise
        finally:
            await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or promote an admin account in FusionRAG without hardcoded secrets."
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Email address for the admin account.",
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="Password for the admin account (optional; if omitted, you will be prompted securely).",
    )
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Read ADMIN_EMAIL and ADMIN_PASSWORD directly from environment/.env.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    email = args.email
    password = args.password

    if args.from_env:
        email = email or settings.ADMIN_EMAIL
        password = password or settings.ADMIN_PASSWORD

    if not email:
        email = input("Enter admin email: ").strip()

    if not password:
        # Prompt securely using getpass
        password = getpass.getpass("Enter admin password: ").strip()
        if not password:
            print("Error: Password cannot be empty.", file=sys.stderr)
            sys.exit(1)
        confirm = getpass.getpass("Confirm admin password: ").strip()
        if password != confirm:
            print("Error: Passwords do not match.", file=sys.stderr)
            sys.exit(1)

    asyncio.run(create_or_update_admin(email=email, password=password))


if __name__ == "__main__":
    main()
