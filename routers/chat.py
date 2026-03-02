from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from models.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    CriterionScore,
    FinishRequest,
    FinishResponse,
    SessionListItem,
    Source,
)
from models.session_db import ChatSession
from services.chat_session_store import (
    add_message,
    create_session,
    get_messages,
    session_exists,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/session", response_model=CreateSessionResponse)
async def create_chat_session(
    req: CreateSessionRequest,
    db: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    session_id = create_session()
    db.add(ChatSession(
        session_id=session_id,
        username=current_user,
        scenario_id=req.scenario_id,
        title=req.title,
    ))
    await db.commit()
    return CreateSessionResponse(session_id=session_id)


@router.post("/message", response_model=ChatMessageResponse)
async def chat_message(
    req: ChatMessageRequest,
    db: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    _ = current_user
    if not session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Unknown session_id. Call /chat/session first.")

    add_message(req.session_id, "user", req.message)

    # Dummy reply for now. We'll replace this with a proper chatbot pipeline when frontend is wired.
    assistant = f"Jeg hørte deg: {req.message}"
    add_message(req.session_id, "assistant", assistant)

    result = await db.execute(select(ChatSession).where(ChatSession.session_id == req.session_id))
    chat_session = result.scalar_one_or_none()
    if chat_session:
        chat_session.turn_count += 1
        chat_session.last_message_preview = assistant[:255]
        await db.commit()

    return ChatMessageResponse(
        session_id=req.session_id,
        assistant_message=assistant,
        used_rag=False,
        sources=[],
    )


@router.post("/finish", response_model=FinishResponse)
async def finish_chat(
    req: FinishRequest,
    db: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    _ = current_user
    if not session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Unknown session_id.")

    transcript = get_messages(req.session_id)
    if not transcript:
        raise HTTPException(status_code=400, detail="Session has no messages.")

    result = await db.execute(select(ChatSession).where(ChatSession.session_id == req.session_id))
    chat_session = result.scalar_one_or_none()
    if chat_session:
        chat_session.saved_at = datetime.now(timezone.utc)
        await db.commit()

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


@router.get("/sessions", response_model=list[SessionListItem])
async def get_chat_sessions(
    db: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.username == current_user)
        .where(ChatSession.saved_at.is_not(None))
        .order_by(ChatSession.saved_at.desc())
    )
    sessions = result.scalars().all()
    return [
        SessionListItem(
            session_id=s.session_id,
            scenario_id=s.scenario_id,
            title=s.title,
            saved_at=s.saved_at,
            turn_count=s.turn_count,
            last_message_preview=s.last_message_preview,
        )
        for s in sessions
    ]
