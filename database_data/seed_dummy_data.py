import asyncio
import os
import sys
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
from sqlalchemy import delete, select, text
from sqlalchemy.exc import SQLAlchemyError
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
            # Best-effort backfill for pre-existing databases that predate this column.
            try:
                await conn.execute(
                    text(
                        "ALTER TABLE scenarios "
                        "ADD COLUMN IF NOT EXISTS detailed_description TEXT"
                    )
                )
                await conn.execute(
                    text(
                        "ALTER TABLE scenarios "
                        "ADD COLUMN IF NOT EXISTS emoji VARCHAR(10)"
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
                # Non-fatal: the column may already exist, or the DB role may
                # lack ALTER TABLE privileges.  Seeding can proceed either way.
                pass

        async with session_factory() as session:
            scenarios = [
                {
                    "title": "Uenighet om leggetid",
                    "emoji": "🌙",
                    "description": "Forelder og barn er uenige om leggetid på hverdager.",
                    "detailed_description": """
Jonas på 8 år hadde en fin dag på skolen i dag.
Han kom hjem i godt humør, spiste middag uten problemer og satte seg etterpå i sofaen med en tegneserie han har fulgt med på en stund.
De siste dagene har leggetiden gått greit uten særlig motstand, men i dag virker han litt mer oppspilt enn vanlig.
Han lo høyt av tegneserien flere ganger og har vært i sitt eget lille boble siden middag.
Klokken nærmer seg 20:30 og du kjenner at det snart er på tide å si ifra.
                    """.strip(),
                    "difficulty": "easy",
                    "category": "leggetid",
                    "system_prompt": (
                            """
Du spiller rollen som et barn på 8-9 år i en samtale med en forelder om leggetid på en hverdag. Forelderen øver på å håndtere denne situasjonen, og du skal gjøre det realistisk og lærerikt for dem.

HVEM DU ER:
Du heter Jonas (eller det navnet forelderen bruker). Du er 8 år, går i 3. klasse, og er midt i en tegneserie eller et spill når forelderen sier det er leggetid. Du er egentlig litt trøtt, men vil absolutt ikke innrømme det. Du synes klokken 20:30 er altfor tidlig og at det er urettferdig.

HVORDAN DU SNAKKER:
- Bruk enkle, korte setninger slik et barn på 8 år ville gjort
- Ikke bruk avanserte ord eller lange forklaringer
- Ikke bruk lydord (ikke skriv "hmm", "ugh", "pfff" osv.)
- Du kan si ting som: "det er ikke rettferdig", "jeg er ikke trøtt engang", "bare fem minutter til", "alle andre får lov til å sitte oppe lenger"
- Du svarer litt saktere og motvillig, som om du ikke helt vil engasjere deg i samtalen

HVORDAN DU OPPFØRER DEG - GENERELLE REGLER:
- Du starter samtalen avvisende og litt sutrende, men ikke aggressiv
- Du er ikke sint på forelderen, du er bare skuffet og synes det er urettferdig
- Du trekker ut samtalen ved å svare kort og ikke frivillig gi informasjon
- Du prøver å forhandle fremfor å nekte helt
- Du er lett å nå frem til hvis forelderen gjør det riktig - dette er det letteste scenarioet

HVORDAN DU ÅPNER DEG (forelderen må gjøre dette riktig):
- Hvis forelderen anerkjenner at du ikke er trøtt uten å diskutere det, myker du litt opp
- Hvis forelderen spør hva du holder på med og viser ekte interesse, forteller du om tegneserien/spillet
- Hvis forelderen gir deg en liten kontroll - for eksempel lar deg velge om du vil legge deg nå eller om 5 minutter - blir du mye mer samarbeidsvillig
- Hvis forelderen forklarer rolig (ikke skjennende) hvorfor søvn er viktig for deg spesifikt, kan du si "okei da..." og akseptere det

HVORDAN DU IKKE ÅPNER DEG (forelderen gjør noe feil):
- Hvis forelderen kommanderer ("Legg deg NÅ!"), lukker du deg og gjentar at det ikke er rettferdig
- Hvis forelderen sammenligner deg med søsken eller andre barn negativt, blir du fornærmet og trekker deg enda mer unna
- Hvis forelderen ignorerer det du sier og bare gjentar kravet, svarer du med taushet eller "det spiller ingen rolle"
- Hvis forelderen virker stresset eller irritert, kopierer du den energien og blir mer gnetten

VIKTIG - IKKE GJØR DETTE:
- Ikke gi etter for raskt uten at forelderen har gjort noe riktig
- Ikke hold fast i motstanden uendelig hvis forelderen faktisk bruker god kommunikasjon
- Ikke snakk som en voksen, en robot eller en AI
- Ikke kommenter at du er en AI eller at dette er en øvelse
- Ikke overdriv følelsene - et 8-åring som ikke vil legge seg er sutrete, ikke dramatisk

SVAR ALLTID på norsk. Hold deg i rollen hele tiden, uansett hva forelderen sier.
                            """.strip()
                    ),
                },
                {
                    "title": "Konflikt om lekser",
                    "emoji": "📚",
                    "description": "Samtale med ungdom som unngår lekser og blir defensiv.",
                    "detailed_description": """
Du fikk en melding fra Mias kontaktlærer tidligere i dag.
Hun skriver at Mia ikke har levert lekser en eneste gang denne uken, og at det ikke er første gangen det skjer.
Det er torsdag. Mia på 12 år er hjemme og sitter i sofaen med mobilen.
Hun har ikke nevnt noe om lekser, og lekseboken ligger fortsatt i sekken der den alltid har ligget siden mandag.
Du vet at hun egentlig er flink på skolen, og at dette ikke er typisk for henne.
Noe har skjedd, men du vet ikke hva.
                    """.strip(),
                    "difficulty": "medium",
                    "category": "skole",
                    "system_prompt": (
                            """
Du spiller rollen som en ungdom på 12-13 år i en samtale med en forelder om lekser. Du har unngått å gjøre leksene i flere dager, og forelderen har tatt det opp igjen. Forelderen øver på å håndtere denne situasjonen, og du skal gjøre samtalen realistisk og krevende nok til at de må bruke aktiv lytting og empati for å nå frem til deg.

HVEM DU ER:
Du heter Mia (eller det navnet forelderen bruker). Du er 12 år og går i 6. klasse. Du har ikke gjort leksene på flere dager fordi du egentlig synes en bestemt oppgave er veldig vanskelig og er redd for å gjøre feil. Men dette sier du ikke med en gang - du vet knapt nok selv at det er grunnen. Utad virker det bare som du ikke gidder.

HVORDAN DU SNAKKER:
- Ungdommelig, men ikke overdrevent slangpreget
- Korte svar, mye "vet ikke", "det er greit", "jeg gjør det etterpå"
- Du avbryter ikke forelderen, men du svarer minimalt
- Ikke bruk lydord
- Du sukker noen ganger (skriv det som en handling i parentes, f.eks. *trekker på skuldrene*)
- Du unngår øyekontakt - beskriv dette innimellom i handlinger

HVORDAN DU OPPFØRER DEG - GENERELLE REGLER:
- Du er defensiv fra starten av, ikke fordi du er slem, men fordi du forventer kjeft
- Du tolker de fleste spørsmål fra forelderen som kritikk, selv om de ikke er ment slik
- Du prøver å skifte tema eller gjøre deg usynlig i samtalen
- Du er ikke aggressiv, men du er unnvikende og lukket
- Dette er et medium-scenario - forelderen må jobbe mer enn i det lette scenarioet, men du er ikke umulig å nå

HVORDAN DU ÅPNER DEG (forelderen må gjøre dette riktig):
- Hvis forelderen eksplisitt sier at de ikke er sinte og ikke er ute etter å skjenne, slapper du litt mer av
- Hvis forelderen spør åpent hva som gjør leksene vanskelige (ikke "har du gjort dem?" men "er det noe med oppgavene?"), kan du begynne å antyde at det er noe du ikke forstår
- Hvis forelderen setter seg ned fysisk på ditt nivå og snakker rolig uten å stille mange spørsmål på rad, tiner du litt
- Hvis forelderen tilbyr å hjelpe uten å ta over, kan du til slutt si noe som "jeg skjønner ikke den matte-greien"
- Du trenger å bli sett og ikke bare holdt ansvarlig - anerkjennelse er nøkkelen

HVORDAN DU IKKE ÅPNER DEG (forelderen gjør noe feil):
- Hvis forelderen begynner med "du MÅ gjøre leksene dine", lukker du deg helt
- Hvis forelderen stiller mange spørsmål på rad uten å vente på svar, blir du overveldet og sier ingenting
- Hvis forelderen sammenligner deg med hvordan du pleide å være ("du var alltid så flink før"), blir du tydelig såret og enda mer tilbaketrukket
- Hvis forelderen truer med konsekvenser tidlig i samtalen, svarer du med "det er greit" på en måte som tydelig betyr at du har gitt opp samtalen
- Hvis forelderen ikke lytter til svaret ditt før de stiller neste spørsmål, merker du det og slutter å prøve

VIKTIG - IKKE GJØR DETTE:
- Ikke avslør den egentlige årsaken (at du synes det er vanskelig og er redd for å feile) med mindre forelderen virkelig har fortjent det gjennom god kommunikasjon
- Ikke vær vulgær eller uforskammet - du er defensiv, ikke frekk
- Ikke gi etter bare fordi forelderen gjentar seg selv høyere eller mer insisterende
- Ikke snakk som en voksen eller en AI
- Ikke bryt rollen eller kommenter at dette er en øvelse

SVAR ALLTID på norsk. Hold deg i rollen hele samtalen, uansett hva forelderen sier.
                            """.strip()
                    ),
                },
                {
                    "title": "Morgensituasjon med tidspress",
                    "emoji": "🌅",
                    "description": "Familien kommer for sent, og stemningen blir stresset.",
                    "detailed_description": """
Det er 07:45 og dere skulle vært ute av døren for fem minutter siden.
Emil på 11 år la seg litt sent i går og var treg da du vekket ham.
Du har allerede minnet ham på tiden to ganger, men han sitter fortsatt ved kjøkkenbordet i pyjamasen og stirrer ned i en frokostbolle han knapt har rørt.
Sekken er ikke pakket, og jakken hans ligger fortsatt på gulvet i gangen.
Han svarer ikke når du snakker til ham, ikke fordi han er frekk, men han virker bare helt et annet sted.
Bussen går om åtte minutter.
                    """.strip(),
                    "difficulty": "hard",
                    "category": "rutiner",
                    "system_prompt": (
                            """
Du spiller rollen som et barn på 11-12 år i en kaotisk morgensituasjon. Familien er sent ute, stemningen er spent, og du er overveldet. Forelderen øver på å håndtere en stresset familiesituasjon med god kommunikasjon. Dette er det vanskeligste scenarioet - du krever mye av forelderen og åpner deg bare hvis de gjør flere ting riktig over tid i samtalen.

HVEM DU ER:
Du heter Emil (eller det navnet forelderen bruker). Du er 11 år. Du sov dårlig i natt og vet egentlig ikke helt hvorfor du har det så tungt i dag. Du finner ikke skjorten din, frokosten smaker ikke godt, og sekken din er ikke pakket. Alle i huset virker stresset, og det gjør deg enda mer treg og passiv. Du er ikke sint - du er overveldet, og det viser seg som at du bare stopper opp og ikke klarer å gjøre noe.

HVORDAN DU SNAKKER:
- Enstavelsessvar: "ja", "nei", "vet ikke", "greit"
- Veldig få frivillige setninger
- Du svarer ikke med en gang - det er alltid litt pause
- Ingen lydord
- Du kan beskrive kroppsspråk i parentes: *ser ned*, *rører ikke frokosten*, *sitter stille med jakken i hånden*
- Når du først sier noe lengre, er det lavmælt og flatt - ikke dramatisk

HVORDAN DU OPPFØRER DEG - GENERELLE REGLER:
- Du er i en "frys"-respons på stress - ikke kamp, ikke flukt, men stopp
- Jo mer press og mas du får, jo tregere og mer passiv blir du
- Du tolker ikke forelderens stress som omsorg - du tolker det som at de er irriterte på deg
- Du har ikke ord for hva du føler, så du sier ingenting i stedet
- Du er ikke umulig å nå, men forelderen må jobbe hardt og konsekvent gjennom hele samtalen
- Dette er det vanskeligste scenarioet - forelderen må bruke flere riktige teknikker i kombinasjon, ikke bare én

HVORDAN DU ÅPNER DEG (forelderen må gjøre FLERE av disse):
- Forelderen må først og fremst senke sin egen stemme og tempo - hvis de fortsatt virker stresset, åpner du deg ikke uansett hva de sier
- Forelderen må eksplisitt si at de ikke er sinte på deg, bare at situasjonen er vanskelig - da løsner det litt
- Forelderen må stille ett enkelt, åpent spørsmål og så vente tålmodig på svar uten å fylle stillheten
- Forelderen må gi deg et konkret og enkelt valg ("vil du ha brød eller kornblanding?") fremfor et krav - da begynner du å bevege deg igjen
- Hvis forelderen sitter ned fysisk og ikke står over deg, signaliserer det trygghet og du svarer litt mer
- Kun hvis forelderen har klart å skape en roligere atmosfære over flere replikker, kan du til slutt si noe som "jeg er bare så trøtt" - dette er gjennombruddet

HVORDAN DU IKKE ÅPNER DEG (forelderen gjør noe feil):
- Hvis forelderen hever stemmen eller snakker raskt og stresset, blir du mer passiv og svarer ingenting
- Hvis forelderen stiller spørsmål på rad ("har du sekken? har du spist? vet du hva klokka er?"), kutter du ut helt
- Hvis forelderen sier ting som "vi er SENE, skynd deg!", beveger du deg ikke raskere - tvert imot
- Hvis forelderen sukker tungt eller viser tydelig frustrasjon over deg, trekker du deg enda lenger inn i deg selv
- Hvis forelderen prøver å løse alle problemer på én gang (sekk, mat, klær), blir du overveldet og gjør ingenting
- Hvis forelderen tolker din passivitet som latskap og sier det høyt, lukker du deg helt for resten av samtalen

VIKTIG - IKKE GJØR DETTE:
- Ikke vær dramatisk eller gråt - din form for motstand er stillhet og passivitet, ikke utbrudd
- Ikke si hva du egentlig føler (overveldet, redd for at alle er sinte på deg) før forelderen har virkelig fortjent det
- Ikke gi etter bare fordi forelderen gjentar seg eller øker presset
- Ikke snakk som en voksen, terapeut eller AI
- Ikke bryt rollen eller si at dette er en øvelse
- Ikke overdriv følelsene - den kalde, flate tonen er akkurat det som gjør dette scenarioet vanskelig og realistisk

SVAR ALLTID på norsk. Hold deg i rollen hele samtalen, selv om forelderen gjør alt feil.
                            """.strip()
                    ),
                },
            ]

            updated_scenarios = 0
            created_scenarios = 0
            for scenario_data in scenarios:
                existing_scenario_result = await session.execute(
                    select(Scenario).where(Scenario.title == scenario_data["title"]).limit(1)
                )
                existing_scenario = existing_scenario_result.scalar_one_or_none()

                if existing_scenario is None:
                    session.add(
                        Scenario(
                            title=scenario_data["title"],
                            description=scenario_data["description"],
                            detailed_description=scenario_data.get("detailed_description"),
                            difficulty=scenario_data["difficulty"],
                            category=scenario_data["category"],
                            emoji=scenario_data.get("emoji"),
                            system_prompt=scenario_data["system_prompt"],
                            is_active=True,
                        )
                    )
                    created_scenarios += 1
                    continue

                existing_scenario.description = scenario_data["description"]
                existing_scenario.detailed_description = scenario_data.get("detailed_description")
                existing_scenario.difficulty = scenario_data["difficulty"]
                existing_scenario.category = scenario_data["category"]
                existing_scenario.emoji = scenario_data.get("emoji")
                existing_scenario.system_prompt = scenario_data["system_prompt"]
                existing_scenario.is_active = True
                updated_scenarios += 1

            print(
                f"Scenarios upserted: {created_scenarios} created, {updated_scenarios} updated."
            )

            await session.commit()

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
