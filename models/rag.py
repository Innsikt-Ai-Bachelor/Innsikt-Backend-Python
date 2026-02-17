from sqlalchemy import Text, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from database import Base

EMBED_DIM = 1536  

class RagChunk(Base):
    __tablename__ = "rag_chunks"
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(200), index=True)
    chunk_text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
