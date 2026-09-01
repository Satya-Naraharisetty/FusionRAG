import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update

from app.core.config import ConfigurationError, settings

logger = logging.getLogger(__name__)


def run_startup_validations() -> None:
    """
    Validates that required system settings are non-empty and well-formed.
    """
    logger.info("Auditing environment settings configurations...")

    # Validate core infrastructure parameters
    infra_vars: dict[str, str | None] = {
        "JWT_SECRET": settings.JWT_SECRET,
    }
    if settings.is_production:
        infra_vars["ENCRYPTION_MASTER_KEY"] = getattr(
            settings, "ENCRYPTION_MASTER_KEY", None
        )
    if not settings.DATABASE_URL:
        infra_vars["POSTGRES_SERVER"] = settings.POSTGRES_SERVER
        infra_vars["POSTGRES_DB"] = settings.POSTGRES_DB

    empty_infra = [k for k, v in infra_vars.items() if not v or not str(v).strip()]

    # On Vercel serverless, skip presence checks for Redis and Qdrant
    if os.getenv("VERCEL") != "1":
        # Validate Redis config
        if not settings.REDIS_URL and not settings.REDIS_HOST:
            empty_infra.append("REDIS_HOST or REDIS_URL")

        # Validate Qdrant config
        if not settings.QDRANT_URL and not settings.QDRANT_HOST:
            empty_infra.append("QDRANT_HOST or QDRANT_URL")

    if empty_infra:
        raise ConfigurationError(
            f"Startup aborted due to empty required infrastructure parameters: "
            f"{', '.join(empty_infra)}"
        )

    # Validate API keys based on configured providers
    key_vars: dict[str, str | None] = {
        "GEMINI_FALLBACK_API_KEY": settings.get_gemini_fallback_api_key()
        or settings.GEMINI_LLM_API_KEY
    }

    empty_keys = [k for k, v in key_vars.items() if not v or not str(v).strip()]
    if empty_keys:
        msg = f"Empty required API key parameters: {', '.join(empty_keys)}"
        if settings.is_production and os.getenv("VERCEL") != "1":
            raise ConfigurationError(f"Startup aborted due to: {msg}")
        else:
            logger.warning(
                f"{msg}. This is allowed in development mode, but LLM or cloud embedding calls will fail."
            )


async def verify_postgres_connectivity(engine) -> None:
    """
    Verifies that the PostgreSQL database container is online and accepting connections.
    """
    if (
        settings.is_testing
        or os.getenv("VERCEL") == "1"
        or type(engine).__name__ in ("MagicMock", "Mock")
    ):
        logger.info("Skipping PostgreSQL connectivity check.")
        return

    logger.info("Testing PostgreSQL connection readiness...")
    for attempt in range(1, 6):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("PostgreSQL database connection verified.")
            return
        except Exception as e:
            logger.warning(
                f"PostgreSQL connection verification attempt {attempt}/5 failed: {e}. "
                "Retrying in 2.0 seconds..."
            )
            if attempt < 5:
                await asyncio.sleep(2.0)

    raise ConfigurationError("PostgreSQL database connection could not be established.")


async def verify_alembic_migrations(engine) -> None:
    """
    Verifies that the database schema is up-to-date with the latest Alembic migration.
    Fails startup if it isn't.
    """
    if (
        settings.is_testing
        or os.getenv("VERCEL") == "1"
        or os.getenv("SKIP_DB_MIGRATION_CHECK", "false").lower() in ("true", "1", "yes")
        or type(engine).__name__ in ("MagicMock", "Mock")
    ):
        logger.info("Skipping database migration check.")
        return

    logger.info("Verifying database schema migrations are up-to-date...")
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    try:
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        ini_path = os.path.join(base_dir, "alembic.ini")
        if not os.path.exists(ini_path):
            logger.warning(
                f"Alembic config not found at {ini_path}. Skipping migration check."
            )
            return

        config = Config(ini_path)
        script = ScriptDirectory.from_config(config)
        head_revision = script.get_current_head()

        if not head_revision:
            logger.info("No migrations defined. Skipping migration check.")
            return
    except Exception as e:
        logger.warning(
            f"Could not load Alembic config or migrations: {e}. Skipping check."
        )
        return

    def get_revision(conn):
        context = MigrationContext.configure(conn)
        return context.get_current_revision()

    try:
        async with engine.connect() as conn:
            current_revision = await conn.run_sync(get_revision)
    except Exception as e:
        raise ConfigurationError(
            f"Database migrations check failed. Unable to read current revision: {e}"
        ) from e

    logger.info(
        f"Database migration check: DB revision={current_revision}, Code head revision={head_revision}"
    )
    if current_revision != head_revision:
        raise ConfigurationError(
            f"Database schema is out of date. Current DB revision: {current_revision}, "
            f"Latest application migration head: {head_revision}. "
            "Please run migrations using scripts/migrate.sh."
        )


async def seed_admin_user(session_factory) -> None:
    """
    Enforces a single admin account seeded from environment variables.
    """
    if settings.is_testing or not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return

    logger.info("Enforcing single default admin account seeding...")
    async with session_factory() as db_session:
        try:
            from app.auth.infrastructure.crypto.password_hasher import (
                Argon2PasswordHasher,
            )
            from app.auth.infrastructure.persistence.models import (
                SQLAlchemyUser,
            )

            email = settings.ADMIN_EMAIL.strip().lower()

            # Demote any other admin users
            await db_session.execute(
                update(SQLAlchemyUser)
                .where(
                    SQLAlchemyUser.role == "admin",
                    SQLAlchemyUser.email != email,
                )
                .values(role="user")
            )

            existing_admin_res = await db_session.execute(
                select(SQLAlchemyUser).where(SQLAlchemyUser.email == email)
            )
            existing_admin = existing_admin_res.scalar_one_or_none()

            if not existing_admin:
                hasher = Argon2PasswordHasher()
                hashed_pwd = hasher.hash(settings.ADMIN_PASSWORD)
                new_admin = SQLAlchemyUser(
                    id=uuid.uuid4(),
                    email=email,
                    hashed_password=hashed_pwd,
                    role="admin",
                    is_active=True,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                db_session.add(new_admin)
                logger.info(f"Successfully seeded default admin account: {email}")
            else:
                if existing_admin.role != "admin":
                    existing_admin.role = "admin"
                    logger.info(
                        f"Successfully promoted existing user {email} to admin."
                    )

            await db_session.commit()
        except Exception as e:
            logger.error(f"Failed to seed/enforce default admin account: {e}")
            await db_session.rollback()


async def cleanup_stale_unverified_signups(session_factory) -> int:
    """
    Purges unverified user accounts created older than UNVERIFIED_USER_CLEANUP_DAYS.
    """
    if settings.is_testing or not settings.REQUIRE_EMAIL_VERIFICATION:
        return 0

    async with session_factory() as db_session:
        try:
            from app.auth.infrastructure.persistence.repositories.user_repository import (
                SQLAlchemyUserRepository,
            )

            user_repo = SQLAlchemyUserRepository(db_session)
            cutoff = datetime.now(UTC) - timedelta(
                days=settings.UNVERIFIED_USER_CLEANUP_DAYS
            )
            count = await user_repo.delete_unverified_older_than(cutoff)
            await db_session.commit()
            if count > 0:
                logger.info(
                    "Startup cleanup: purged %d unverified user account(s) older than %d days.",
                    count,
                    settings.UNVERIFIED_USER_CLEANUP_DAYS,
                )
            return count
        except Exception as e:
            logger.warning("Startup cleanup of unverified users failed: %s", e)
            await db_session.rollback()
            return 0
