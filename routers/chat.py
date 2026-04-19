from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import os
from datetime import datetime
from sqlalchemy import func, select
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
from services.gamification_service import award_xp_and_check_badges


class CreateSessionRequest(BaseModel):
    scenario_id: Optional[int] = None
    title: Optional[str] = None


class SessionSummary(BaseModel):
    session_id: str
    scenario_id: Optional[int]
    title: Optional[str]
    created_at: datetime
    # Always an integer; 0 means the session has not been evaluated yet.
    total_score: int = 0
    has_feedback: bool = False


class FeedbackDetail(BaseModel):
    """Lightweight feedback-only view — no message history."""
    session_id: str
    total_score: int
    criteria: List[CriterionScore]
    positive_feedback: List[str] = Field(default_factory=list)
    negative_feedback: List[str] = Field(default_factory=list)
    sources: List[Source] = Field(default_factory=list)


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
    current_user_id: int = Depends(get_current_user_id),
):
    _ = current_user
    scenario_id: Optional[int] = None

    if session_exists(req.session_id):
        transcript = get_messages(req.session_id)
        scenario_id, _title = get_session_meta(req.session_id)
    else:
        # Session not in memory (e.g. after a restart) — fall back to DB
        db_sess_result = await db.execute(
            select(ChatSessionDB).where(ChatSessionDB.id == req.session_id)
        )
        db_sess = db_sess_result.scalar_one_or_none()
        if not db_sess:
            raise HTTPException(status_code=404, detail="Session not found.")
        scenario_id = db_sess.scenario_id

        msgs_result = await db.execute(
            select(ChatMessageDB)
            .where(ChatMessageDB.session_id == req.session_id)
            .order_by(ChatMessageDB.id)
        )
        db_messages = msgs_result.scalars().all()
        transcript = [StoredMessage(role=m.role, content=m.content) for m in db_messages]

    if not transcript:
        raise HTTPException(status_code=400, detail="Session has no messages.")

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

    # Upsert feedback — avoid integrity error if /finish is called more than once
    fb_result = await db.execute(
        select(FeedbackRecord).where(FeedbackRecord.session_id == req.session_id)
    )
    existing_fb = fb_result.scalar_one_or_none()
    is_new_feedback = existing_fb is None
    if existing_fb:
        existing_fb.total_score = feedback.total_score
        existing_fb.criteria = [c.model_dump() for c in feedback.criteria]
        existing_fb.positive_feedback = feedback.positive_feedback
        existing_fb.negative_feedback = feedback.negative_feedback
        existing_fb.sources = [s.model_dump() for s in feedback.sources]
    else:
        db.add(FeedbackRecord(
            session_id=req.session_id,
            total_score=feedback.total_score,
            criteria=[c.model_dump() for c in feedback.criteria],
            positive_feedback=feedback.positive_feedback,
            negative_feedback=feedback.negative_feedback,
            sources=[s.model_dump() for s in feedback.sources],
        ))
    await db.commit()

    # Award XP / badges exactly once per unique session completion.
    new_badges: list[str] = []
    if is_new_feedback:
        new_badges = await award_xp_and_check_badges(
            db=db,
            user_id=current_user_id,
            total_score=feedback.total_score,
        )

    return feedback.model_copy(update={"newly_earned_badges": new_badges})


@router.get("/sessions", response_model=List[SessionSummary])
async def list_sessions(
    db: AsyncSession = Depends(get_session),
    current_user_id: int = Depends(get_current_user_id),
):
    result = await db.execute(
        select(
            ChatSessionDB,
            func.coalesce(FeedbackRecord.total_score, 0).label("total_score"),
            (FeedbackRecord.session_id.isnot(None)).label("has_feedback"),
        )
        .outerjoin(FeedbackRecord, ChatSessionDB.id == FeedbackRecord.session_id)
        .where(ChatSessionDB.user_id == current_user_id)
        .order_by(ChatSessionDB.created_at.desc())
    )
    rows = result.all()
    return [
        SessionSummary(
            session_id=chat_session.id,
            scenario_id=chat_session.scenario_id,
            title=chat_session.title,
            created_at=chat_session.created_at,
            total_score=total_score,
            has_feedback=has_feedback,
        )
        for chat_session, total_score, has_feedback in rows
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


@router.get("/session/{session_id}/feedback", response_model=FeedbackDetail)
async def get_session_feedback(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    current_user_id: int = Depends(get_current_user_id),
):
    """Return only the feedback/criteria for a session — no message history."""
    # Verify ownership
    owner_result = await db.execute(
        select(ChatSessionDB.id).where(
            ChatSessionDB.id == session_id,
            ChatSessionDB.user_id == current_user_id,
        )
    )
    if owner_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    fb_result = await db.execute(
        select(FeedbackRecord).where(FeedbackRecord.session_id == session_id)
    )
    fb = fb_result.scalar_one_or_none()
    if fb is None:
        raise HTTPException(status_code=404, detail="No feedback found for this session.")

    return FeedbackDetail(
        session_id=session_id,
        total_score=fb.total_score,
        criteria=[CriterionScore(**c) for c in fb.criteria],
        positive_feedback=fb.positive_feedback,
        negative_feedback=fb.negative_feedback,
        sources=[Source(**s) for s in fb.sources],
    )
