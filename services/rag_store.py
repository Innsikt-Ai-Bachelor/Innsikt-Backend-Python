from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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


async def search_similar(session, query_embedding, k: int = 5):
    stmt = (
        select(RagChunk)
        .order_by(RagChunk.embedding.cosine_distance(query_embedding))
        .limit(k)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())
