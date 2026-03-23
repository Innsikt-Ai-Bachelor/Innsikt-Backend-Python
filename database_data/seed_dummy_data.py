import asyncio
import os
import sys
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import Base  # noqa: E402
import models.db  # noqa: E402,F401
import models.rag  # noqa: E402,F401
import models.scenario  # noqa: E402,F401
from models.db import User  # noqa: E402
from models.rag import RagChunk  # noqa: E402
from models.scenario import Scenario  # noqa: E402
from models.users import hash_password  # noqa: E402
from services.rag_pipeline import ingest_documents  # noqa: E402


RAG_DOC_FILENAME = "samtalemetodikk_foreldre_rag.pdf"


def _extract_pdf_text(pdf_path: Path) -> str:
    raw = pdf_path.read_bytes()
    reader = PdfReader(BytesIO(raw))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if not text:
        raise RuntimeError(f"No extractable text found in PDF: {pdf_path.name}")
    return text


async def seed_dummy_data() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set (expected in environment or .env)")

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
                        system_prompt=(
                        "Du er et barn (ca. 7 år) som ikke vil legge deg på hverdager. "
                        "Du vil heller leke/se skjerm og synes det er urettferdig. "
                        "Du svarer KUN som barnet. 1–2 setninger. Ingen råd eller voksenforklaringer."
                        ),
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

            pdf_path = Path(__file__).resolve().parent / RAG_DOC_FILENAME
            if not pdf_path.exists():
                raise RuntimeError(f"Missing required RAG PDF: {pdf_path}")

            pdf_text = _extract_pdf_text(pdf_path)

            # Keep seeding idempotent by replacing existing chunks for this doc_id.
            await session.execute(delete(RagChunk).where(RagChunk.doc_id == RAG_DOC_FILENAME))
            await session.commit()

            chunks_added = await ingest_documents(
                session=session,
                items=[
                    (
                        RAG_DOC_FILENAME,
                        pdf_text,
                        {
                            "filename": RAG_DOC_FILENAME,
                            "source": RAG_DOC_FILENAME,
                            "seeded_by": "seed_dummy_data.py",
                        },
                    )
                ],
            )
            print(f"RAG PDF ingested: {RAG_DOC_FILENAME} ({chunks_added} chunk(s)).")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_dummy_data())
