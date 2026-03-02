import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import Base  # noqa: E402
import models.db  # noqa: E402,F401
import models.rag  # noqa: E402,F401
import models.scenario  # noqa: E402,F401


async def clear_database() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))
            await session.commit()
        print("Database cleared successfully.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(clear_database())
