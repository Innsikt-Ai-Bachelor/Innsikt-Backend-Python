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
    if _engine is None:
        _init_engine()
    import models.db
    import models.rag
    import models.scenario
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
            await conn.execute(
                text(
                    "ALTER TABLE scenarios "
                    "ADD COLUMN IF NOT EXISTS detailed_description TEXT"
                )
            )
    except SQLAlchemyError:
        # Non-fatal: the column may already exist, or the DB role may lack ALTER
        # TABLE privileges.  The app can continue normally in either case.
        pass
