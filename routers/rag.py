from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from models.rag_api import IngestResponse, AskRequest, AskResponse, AskSource
from services.rag_pipeline import ingest_documents, answer_question


router = APIRouter(prefix="/rag", tags=["rag"])


def _extract_upload_text(file: UploadFile, raw: bytes) -> str:
    filename = (file.filename or "").lower()
    is_pdf = file.content_type == "application/pdf" or filename.endswith(".pdf")

    if is_pdf:
        reader = PdfReader(BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if not text:
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename or 'unknown'}' does not contain extractable text",
            )
        return text

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File '{file.filename or 'unknown'}' is not supported. "
                "Use UTF-8 text files or PDFs."
            ),
        )


@router.post("/ingest", response_model=IngestResponse)
async def rag_ingest(
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    _ = current_user
    items = []
    for file in files:
        raw = await file.read()
        if not raw:
            continue
        content = _extract_upload_text(file=file, raw=raw)

        doc_id = file.filename or "uploaded_document"
        meta = {
            "filename": file.filename,
            "content_type": file.content_type,
            "source": file.filename,
        }
        items.append((doc_id, content, meta))

    if not items:
        raise HTTPException(status_code=400, detail="No non-empty files were provided")

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
