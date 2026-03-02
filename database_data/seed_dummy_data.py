import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import Base  # noqa: E402
import models.db  # noqa: E402,F401
import models.rag  # noqa: E402,F401
import models.scenario  # noqa: E402,F401
from models.db import User  # noqa: E402
from models.scenario import Scenario  # noqa: E402
from models.users import hash_password  # noqa: E402


async def seed_dummy_data() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            scenario_exists = await session.execute(select(Scenario.id).limit(1))
            if scenario_exists.first() is None:
                scenarios = [
                    Scenario(
                        title="Uenighet om leggetid",
                        description="Forelder og barn er uenige om leggetid på hverdager.",
                        difficulty="easy",
                        category="skjermtid",
                        system_prompt="Du er en hjelpsom coach som hjelper foreldre med rolig og tydelig kommunikasjon rundt leggetid.",
                        is_active=True,
                    ),
                    Scenario(
                        title="Konflikt om lekser",
                        description="Samtale med ungdom som unngår lekser og blir defensiv.",
                        difficulty="medium",
                        category="skole",
                        system_prompt="Du er en veileder som bruker åpne spørsmål og validering for å redusere konflikt og øke samarbeid.",
                        is_active=True,
                    ),
                    Scenario(
                        title="Morgensituasjon med tidspress",
                        description="Familien kommer for sent, og stemningen blir stresset.",
                        difficulty="hard",
                        category="rutiner",
                        system_prompt="Du hjelper brukeren å planlegge korte, konkrete grep for å skape ro i hektiske morgenrutiner.",
                        is_active=True,
                    ),
                ]
                session.add_all(scenarios)
                print("Dummy scenario data prepared.")
            else:
                print("Skipped scenarios: table already contains data.")

            dummy_users = [
                {
                    "username": "testuser1",
                    "email": "testuser1@example.com",
                    "full_name": "Test User One",
                    "password": "Test1234!",
                },
                {
                    "username": "testuser2",
                    "email": "testuser2@example.com",
                    "full_name": "Test User Two",
                    "password": "Test1234!",
                },
            ]

            added_users = 0
            for user_data in dummy_users:
                existing_user = await session.execute(
                    select(User.id).where(User.username == user_data["username"]).limit(1)
                )
                if existing_user.first() is not None:
                    continue

                session.add(
                    User(
                        username=user_data["username"],
                        email=user_data["email"],
                        full_name=user_data["full_name"],
                        password_hash=hash_password(user_data["password"]),
                    )
                )
                added_users += 1

            await session.commit()
            print(f"Dummy user data inserted: {added_users} user(s).")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_dummy_data())
