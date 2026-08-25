import asyncio
import logging
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import (  # noqa: E402
    init_postgres_engine,
    init_qdrant_client,
    init_redis_client,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("reset_all_data")


async def reset_postgres():
    logger.info(
        "Connecting to PostgreSQL: %s",
        settings.POSTGRES_SERVER or settings.DATABASE_URL[:25] + "...",
    )
    engine = init_postgres_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        # Check existing tables in public schema
        result = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        )
        existing_tables = {row[0] for row in result.fetchall()}
        logger.info(
            "Existing database tables in public schema: %s", sorted(existing_tables)
        )

        admin_email = (settings.ADMIN_EMAIL or "").strip().lower()

        # Find admin IDs to preserve
        admin_ids = []
        if "users" in existing_tables:
            admin_stmt = text(
                "SELECT id, email FROM users WHERE role = 'admin' OR LOWER(email) = :email"
            )
            admin_result = await session.execute(admin_stmt, {"email": admin_email})
            admin_rows = admin_result.fetchall()
            admin_ids = [str(row[0]) for row in admin_rows]
            admin_emails = [row[1] for row in admin_rows]
            logger.info(
                "Preserving %d admin user(s): %s",
                len(admin_ids),
                admin_emails if admin_emails else f"({admin_email} not present in DB)",
            )

        # Truncate / delete tables in dependent order
        tables_to_clear_completely = [
            "benchmark_runs",
            "evaluation_results",
            "evaluation_runs",
            "conversation_summaries",
            "conversation_messages",
            "conversations",
            "document_embeddings",
            "document_chunks",
            "document_files",
            "documents",
            "durable_cleanup_jobs",
        ]

        for table in tables_to_clear_completely:
            if table in existing_tables:
                try:
                    res = await session.execute(text(f"DELETE FROM {table}"))
                    logger.info(
                        "Cleared table '%s' (rows deleted: %s)", table, res.rowcount
                    )
                except Exception as e:
                    logger.warning("Could not clear table '%s': %s", table, e)

        # Clear non-admin user-related records
        if "refresh_sessions" in existing_tables:
            if admin_ids:
                formatted_ids = "'" + "','".join(admin_ids) + "'"
                res = await session.execute(
                    text(
                        f"DELETE FROM refresh_sessions WHERE user_id::text NOT IN ({formatted_ids})"
                    )
                )
            else:
                res = await session.execute(text("DELETE FROM refresh_sessions"))
            logger.info(
                "Cleared non-admin sessions from 'refresh_sessions' (rows deleted: %s)",
                res.rowcount,
            )

        if "user_encryption_keys" in existing_tables:
            if admin_ids:
                formatted_ids = "'" + "','".join(admin_ids) + "'"
                res = await session.execute(
                    text(
                        f"DELETE FROM user_encryption_keys WHERE user_id::text NOT IN ({formatted_ids})"
                    )
                )
            else:
                res = await session.execute(text("DELETE FROM user_encryption_keys"))
            logger.info(
                "Cleared non-admin keys from 'user_encryption_keys' (rows deleted: %s)",
                res.rowcount,
            )

        if "users" in existing_tables:
            if admin_ids:
                formatted_ids = "'" + "','".join(admin_ids) + "'"
                res = await session.execute(
                    text(f"DELETE FROM users WHERE id::text NOT IN ({formatted_ids})")
                )
            else:
                res = await session.execute(text("DELETE FROM users"))
            logger.info(
                "Cleared non-admin users from 'users' (rows deleted: %s)", res.rowcount
            )

        await session.commit()
        logger.info("PostgreSQL database cleanup committed successfully.")

    await engine.dispose()


async def reset_qdrant():
    logger.info(
        "Connecting to Qdrant: %s",
        settings.QDRANT_URL or f"{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
    )
    try:
        qdrant_client = init_qdrant_client(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY,
            url=settings.QDRANT_URL,
        )
        collections_response = await qdrant_client.get_collections()
        if not collections_response.collections:
            logger.info("No collections found in Qdrant.")
        for col in collections_response.collections:
            col_name = col.name
            logger.info("Deleting Qdrant collection: %s", col_name)
            await qdrant_client.delete_collection(collection_name=col_name)
            logger.info("Qdrant collection '%s' deleted successfully.", col_name)
        await qdrant_client.close()
    except Exception as e:
        logger.warning("Could not reset Qdrant: %s", e)


async def reset_redis():
    logger.info("Connecting to Redis...")
    try:
        redis_client = init_redis_client(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_SSL,
            url=settings.REDIS_URL,
        )
        await redis_client.flushdb()
        logger.info("Redis DB flushed successfully.")
        await redis_client.aclose()
    except Exception as e:
        logger.warning("Could not flush Redis: %s", e)


async def reset_local_files():
    data_dir = backend_dir / "data"
    if data_dir.exists():
        for item in data_dir.iterdir():
            if item.is_file() and not item.name.startswith(".gitkeep"):
                try:
                    item.unlink()
                    logger.info("Deleted local file: %s", item.name)
                except Exception as e:
                    logger.warning("Failed to delete %s: %s", item, e)


async def main():
    logger.info("=== STARTING FULL DATABASE & DATA RESET ===")
    await reset_postgres()
    await reset_qdrant()
    await reset_redis()
    await reset_local_files()
    logger.info("=== FULL DATA RESET COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    asyncio.run(main())
