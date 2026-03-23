from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models.scenario import Scenario
from models.history import ChatSessionDB, ChatMessageDB, FeedbackRecord
from services.chat_session_store import get_session_meta

from auth import get_current_user, get_current_user_id
from models.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    CreateSessionResponse,
    CriterionScore,
    FinishRequest,
    FinishResponse,
    Source,
    StoredMessage,
)
from services.chat_session_store import (
    add_message,
    create_session,
    get_messages,
    session_exists,
)
from services.openai_client import chat_complete_messages
from services.feedback_pipeline import evaluate_conversation


class CreateSessionRequest(BaseModel):
    scenario_id: Optional[int] = None
    title: Optional[str] = None


class SessionSummary(BaseModel):
    session_id: str
    scenario_id: Optional[int]
    title: Optional[str]
    created_at: datetime
    total_score: Optional[int] = None


class SessionDetail(BaseModel):
    session_id: str
    scenario_id: Optional[int]
    title: Optional[str]
    created_at: datetime
    messages: List[StoredMessage]
    feedback: Optional[FinishResponse] = None


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/session", response_model=CreateSessionResponse)
async def create_chat_session(
    req: Optional[CreateSessionRequest] = None,
    db: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
    current_user_id: int = Depends(get_current_user_id),
):
    scenario_id = req.scenario_id if req else None
    title = req.title if req else None
    session_id = create_session(scenario_id=scenario_id, title=title)

    db_session = ChatSessionDB(
        id=session_id,
        user_id=current_user_id,
        scenario_id=scenario_id,
        title=title,
    )
    db.add(db_session)
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

    # 1) lagre user message i session
    add_message(req.session_id, "user", req.message)

    # 2) bygg meldingshistorikk til OpenAI
    base_system_prompt = os.getenv("CHAT_SYSTEM_PROMPT", "Du er en hjelpsom assistent.")
    transcript = get_messages(req.session_id)

    messages = [{"role": "system", "content": base_system_prompt}]

    # 2.1) hent scenario og legg inn scenario-system_prompt
    scenario_id, _title = get_session_meta(req.session_id)
    if scenario_id is not None:
        result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
        scenario = result.scalar_one_or_none()
        if scenario and scenario.system_prompt:
            messages.append({"role": "system", "content": scenario.system_prompt})
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

    # 4) lagre assistant reply i minnet
    add_message(req.session_id, "assistant", assistant)

    # 5) lagre begge meldinger i databasen
    db.add(ChatMessageDB(session_id=req.session_id, role="user", content=req.message))
    db.add(ChatMessageDB(session_id=req.session_id, role="assistant", content=assistant))
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

    scenario_id, _title = get_session_meta(req.session_id)
    scenario = None
    if scenario_id is not None:
        result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
        scenario = result.scalar_one_or_none()

    try:
        feedback = await evaluate_conversation(
            session=db,
            session_id=req.session_id,
            messages=transcript,
            scenario=scenario,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evalueringsfeil: {str(e)}")

    # Lagre feedback i databasen
    db.add(FeedbackRecord(
        session_id=req.session_id,
        total_score=feedback.total_score,
        criteria=[c.model_dump() for c in feedback.criteria],
        positive_feedback=feedback.positive_feedback,
        negative_feedback=feedback.negative_feedback,
        sources=[s.model_dump() for s in feedback.sources],
    ))
    await db.commit()

    return feedback


@router.get("/sessions", response_model=List[SessionSummary])
async def list_sessions(
    db: AsyncSession = Depends(get_session),
    current_user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(ChatSessionDB, FeedbackRecord.total_score)
        .outerjoin(FeedbackRecord, ChatSessionDB.id == FeedbackRecord.session_id)
        .where(ChatSessionDB.user_id == current_user_id)
        .order_by(ChatSessionDB.created_at.desc())
    )
    rows = result.all()
    return [
        SessionSummary(
            session_id=row.ChatSessionDB.id,
            scenario_id=row.ChatSessionDB.scenario_id,
            title=row.ChatSessionDB.title,
            created_at=row.ChatSessionDB.created_at,
            total_score=row.total_score,
        )
        for row in rows
    ]


@router.get("/session/{session_id}", response_model=SessionDetail)
async def get_session_detail(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    current_user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(ChatSessionDB).where(
            ChatSessionDB.id == session_id,
            ChatSessionDB.user_id == current_user_id,
        )
    )
    chat_session = result.scalar_one_or_none()
    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found.")

    msgs_result = await db.execute(
        select(ChatMessageDB)
        .where(ChatMessageDB.session_id == session_id)
        .order_by(ChatMessageDB.id)
    )
    db_messages = msgs_result.scalars().all()
    messages = [StoredMessage(role=m.role, content=m.content) for m in db_messages]

    fb_result = await db.execute(
        select(FeedbackRecord).where(FeedbackRecord.session_id == session_id)
    )
    fb = fb_result.scalar_one_or_none()

    feedback = None
    if fb:
        feedback = FinishResponse(
            session_id=session_id,
            total_score=fb.total_score,
            criteria=[CriterionScore(**c) for c in fb.criteria],
            positive_feedback=fb.positive_feedback,
            negative_feedback=fb.negative_feedback,
            sources=[Source(**s) for s in fb.sources],
        )

    return SessionDetail(
        session_id=chat_session.id,
        scenario_id=chat_session.scenario_id,
        title=chat_session.title,
        created_at=chat_session.created_at,
        messages=messages,
        feedback=feedback,
    )
