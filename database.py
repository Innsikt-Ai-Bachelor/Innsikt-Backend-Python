import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError


class Base(DeclarativeBase):
    pass


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _init_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        return
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    _engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


async def get_session():
    if _sessionmaker is None:
        _init_engine()
    async with _sessionmaker() as session:
        yield session


async def init_db() -> None:
    import models.db
    import models.gamification
    import models.history
    import models.rag
    import models.scenario
    if _engine is None:
        _init_engine()
    try:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except OSError as exc:
        raise RuntimeError(
            "Could not connect to PostgreSQL. Ensure the database is running and DATABASE_URL is correct."
        ) from exc
    except SQLAlchemyError as exc:
        raise RuntimeError(
            "Database initialization failed. Check DATABASE_URL and PostgreSQL configuration."
        ) from exc
    # Best-effort backfill for databases created before detailed_description was added.
    # Failures here (e.g. insufficient privileges, column already exists) are non-fatal.
    try:
        async with _engine.begin() as conn:
            # Add gamification columns to the users table for existing deployments.
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS xp INTEGER NOT NULL DEFAULT 0")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS level INTEGER NOT NULL DEFAULT 1")
            )
    except SQLAlchemyError:
        pass
    try:
        async with _engine.begin() as conn:
            await conn.execute(
                text(
                    "ALTER TABLE scenarios "
                    "ADD COLUMN IF NOT EXISTS detailed_description TEXT"
                )
            )

            column_type_result = await conn.execute(
                text(
                    "SELECT udt_name "
                    "FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'scenarios' "
                    "AND column_name = 'detailed_description'"
                )
            )
            column_type = column_type_result.scalar_one_or_none()

            # Legacy installs may still have JSON/JSONB for this column; coerce to
            # TEXT so ORM inserts/updates continue to work with string payloads.
            if column_type in {"json", "jsonb"}:
                await conn.execute(
                    text(
                        "ALTER TABLE scenarios "
                        "ALTER COLUMN detailed_description TYPE TEXT "
                        "USING CASE "
                        "WHEN detailed_description IS NULL THEN NULL "
                        "WHEN jsonb_typeof(detailed_description::jsonb) = 'object' "
                        "AND (detailed_description::jsonb ? 'summary') "
                        "THEN detailed_description::jsonb ->> 'summary' "
                        "WHEN jsonb_typeof(detailed_description::jsonb) = 'string' "
                        "THEN detailed_description::jsonb #>> '{}' "
                        "ELSE detailed_description::text "
                        "END"
                    )
                )
    except SQLAlchemyError:
        # Non-fatal: the column may already exist, or the DB role may lack ALTER
        # TABLE privileges.  The app can continue normally in either case.
        pass
