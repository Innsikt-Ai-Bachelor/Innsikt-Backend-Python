from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.scenario import Scenario
from services.chat_session_store import get_session_meta

from auth import get_current_user
from models.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    CreateSessionResponse,
    FinishRequest,
    FinishResponse,
    CriterionScore,
    Source,
)
from services.chat_session_store import (
    add_message,
    create_session,
    get_messages,
    session_exists,
)
from services.openai_client import chat_complete_messages
class CreateSessionRequest(BaseModel):
    scenario_id: Optional[int] = None
    title: Optional[str] = None


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/session", response_model=CreateSessionResponse)
async def create_chat_session(
    req: Optional[CreateSessionRequest] = None,
    current_user: str = Depends(get_current_user),
):
    _ = current_user
    scenario_id = req.scenario_id if req else None
    title = req.title if req else None
    session_id = create_session(scenario_id=scenario_id, title=title)
    return CreateSessionResponse(session_id=session_id)


@router.post("/message", response_model=ChatMessageResponse)
async def chat_message(
    req: ChatMessageRequest,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    _ = current_user
    if not session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Unknown session_id. Call /chat/session first.")

    # 1) lagre user message i session
    add_message(req.session_id, "user", req.message)

    # 2) bygg meldingshistorikk til OpenAI
    base_system_prompt = os.getenv("CHAT_SYSTEM_PROMPT", "Du er en hjelpsom assistent.")
    transcript = get_messages(req.session_id)

    messages = [{"role": "system", "content": base_system_prompt}]

    # 2.1) hent scenario og legg inn scenario-system_prompt
    scenario_id, _title = get_session_meta(req.session_id)
    if scenario_id is not None:
        result = await session.execute(select(Scenario).where(Scenario.id == scenario_id))
        scenario = result.scalar_one_or_none()
        if scenario and scenario.system_prompt:
            messages.append({"role": "system", "content": scenario.system_prompt})

            # (valgfritt, men ofte nyttig) ekstra kontekst til modellen:
            messages.append({
                "role": "system",
                "content": (
                    f"Scenario: {scenario.title}\n"
                    f"Beskrivelse: {scenario.description or ''}\n"
                    f"Vanskelighetsgrad: {scenario.difficulty or ''}\n"
                    f"Kategori: {scenario.category or ''}\n"
                ).strip(),
            })

    # 2.2) legg til historikk
    messages.extend([{"role": m.role, "content": m.content} for m in transcript])

    # 3) kall OpenAI
    try:
        assistant = await chat_complete_messages(messages=messages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI-feil: {str(e)}")

    # 4) lagre assistant reply
    add_message(req.session_id, "assistant", assistant)

    return ChatMessageResponse(
        session_id=req.session_id,
        assistant_message=assistant,
        used_rag=False,
        sources=[],
    )


@router.post("/finish", response_model=FinishResponse)
async def finish_chat(req: FinishRequest, current_user: str = Depends(get_current_user)):
    _ = current_user
    if not session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Unknown session_id.")

    transcript = get_messages(req.session_id)
    if not transcript:
        raise HTTPException(status_code=400, detail="Session has no messages.")

    # Dummy scoring for now. Will be replaced by Eval-RAG.
    criteria = [
        CriterionScore(name="Faglig korrekthet", score=3, max_score=5, reason="Dummy – ikke evaluert enda."),
        CriterionScore(name="Sikkerhet", score=3, max_score=5, reason="Dummy – ikke evaluert enda."),
        CriterionScore(name="Kommunikasjon", score=4, max_score=5, reason="Dummy – ikke evaluert enda."),
    ]
    total = round(sum(c.score / c.max_score for c in criteria) / len(criteria) * 100)
    feedback = [
        "Dummy feedback: Dette er en placeholder til Eval-RAG er koblet på.",
        "Når vi kobler på, kommer konkrete forbedringspunkter basert på kundedokumentene.",
    ]

    return FinishResponse(
        session_id=req.session_id,
        total_score=total,
        criteria=criteria,
        feedback=feedback,
        sources=[Source(source="dummy")],
    )