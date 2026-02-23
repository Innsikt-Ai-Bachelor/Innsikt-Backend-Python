from fastapi import APIRouter, Depends, HTTPException

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


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/session", response_model=CreateSessionResponse)
async def create_chat_session(current_user: str = Depends(get_current_user)):
    # Session is tied to an authenticated user (at least in API usage).
    # For now we only return a session_id; a DB store later can store user_id as well.
    _ = current_user
    session_id = create_session()
    return CreateSessionResponse(session_id=session_id)


@router.post("/message", response_model=ChatMessageResponse)
async def chat_message(req: ChatMessageRequest, current_user: str = Depends(get_current_user)):
    _ = current_user
    if not session_exists(req.session_id):
        raise HTTPException(status_code=404, detail="Unknown session_id. Call /chat/session first.")

    add_message(req.session_id, "user", req.message)

    # Dummy reply for now. We'll replace this with a proper chatbot pipeline when frontend is wired.
    assistant = f"Jeg hørte deg: {req.message}"

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
