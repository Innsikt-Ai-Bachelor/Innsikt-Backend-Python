from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from models.rag_api import IngestRequest, IngestResponse, AskRequest, AskResponse, AskSource
from services.rag_pipeline import ingest_documents, answer_question


router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/ingest", response_model=IngestResponse)
async def rag_ingest(
    req: IngestRequest,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    _ = current_user
    items = [(i.doc_id, i.content, i.meta) for i in req.items]
    chunks_added = await ingest_documents(session=session, items=items)
    return IngestResponse(ok=True, chunks_added=chunks_added)


@router.post("/ask", response_model=AskResponse)
async def rag_ask(
    req: AskRequest,
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    _ = current_user
    try:
        answer, sources = await answer_question(session=session, question=req.question, k=req.k, doc_id=req.doc_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AskResponse(
        answer=answer,
        sources=[AskSource(id=s["id"], doc_id=s["doc_id"], meta=s["meta"]) for s in sources],
    )
