from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pgvector.sqlalchemy import cosine_distance

from models.rag import RagChunk


async def insert_chunks(
    session: AsyncSession,
    doc_id: str,
    chunks: list[str],
    embeddings: list[list[float]],
    meta: dict | None = None,
) -> None:
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings must have same length")

    rows = [
        RagChunk(
            doc_id=doc_id,
            chunk_text=chunk,
            embedding=embedding,
            meta=meta or {},
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]

    session.add_all(rows)
    await session.commit()


async def search_similar(
    session: AsyncSession,
    query_embedding: list[float],
    k: int = 5,
    doc_id: str | None = None,
):
    stmt = select(RagChunk)

    if doc_id:
        stmt = stmt.where(RagChunk.doc_id == doc_id)

    stmt = (
        stmt.order_by(cosine_distance(RagChunk.embedding, query_embedding))
        .limit(k)
    )

    result = await session.execute(stmt)
    return result.scalars().all()
