import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


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
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
