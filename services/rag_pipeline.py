from __future__ import annotations

from typing import Any, Dict, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from services.openai_client import chat_complete, embed_query, embed_texts
from services.rag_store import insert_chunks, search_similar


def split_text(text: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> List[str]:
    """Simple character-based splitter (good enough for v1).

    You can swap this with a tokenizer-based splitter later.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be < chunk_size")

    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - chunk_overlap
        if start < 0:
            start = 0
        if end == n:
            break
    return chunks


async def ingest_documents(
    session: AsyncSession,
    items: List[Tuple[str, str, Dict[str, Any]]],
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> int:
    """Ingest (doc_id, content, meta) items into pgvector store."""
    total_chunks = 0
    for doc_id, content, meta in items:
        chunks = split_text(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not chunks:
            continue
        embeddings = await embed_texts(chunks)
        await insert_chunks(session=session, doc_id=doc_id, chunks=chunks, embeddings=embeddings, meta=meta)
        total_chunks += len(chunks)
    return total_chunks


def _format_context(rows) -> str:
    parts = []
    for r in rows:
        src = r.meta.get("source", r.doc_id)
        parts.append(f"[doc_id={r.doc_id} source={src} chunk_id={r.id}]\n{r.chunk_text}")
    return "\n\n---\n\n".join(parts)


async def answer_question(
    session: AsyncSession,
    question: str,
    k: int = 5,
    doc_id: str | None = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    q_emb = await embed_query(question)
    rows = await search_similar(session=session, query_embedding=q_emb, k=k, doc_id=doc_id)
    context = _format_context(rows)

    system = (
        "Du er en hjelpsom assistent. Bruk kun konteksten for å svare. "
        "Hvis svaret ikke finnes i konteksten, si tydelig at du ikke kan finne det i dokumentene."
    )

    user = f"Kontekst:\n{context}\n\nSpørsmål: {question}"
    answer = await chat_complete(system=system, user=user)

    sources = [
        {
            "id": r.id,
            "doc_id": r.doc_id,
            "meta": r.meta or {},
        }
        for r in rows
    ]
    return answer, sources
