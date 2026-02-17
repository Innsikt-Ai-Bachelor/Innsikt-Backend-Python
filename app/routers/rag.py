from fastapi import APIRouter
from app.schemas.rag import IngestRequest, AskRequest
from app.services.rag.store import ingest_texts
from app.services.rag.pipeline import answer

router = APIRouter(prefix="/rag", tags=["rag"])

@router.post("/ingest")
def rag_ingest(req: IngestRequest):
    chunks_added = ingest_texts([i.model_dump() for i in req.items])
    return {"ok": True, "chunks_added": chunks_added}

@router.post("/ask")
def rag_ask(req: AskRequest):
    return answer(req.question, k=req.k)
