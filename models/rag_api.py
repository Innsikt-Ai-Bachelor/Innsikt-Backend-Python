from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class IngestItem(BaseModel):
    doc_id: str
    content: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    items: List[IngestItem]


class IngestResponse(BaseModel):
    ok: bool
    chunks_added: int


class AskRequest(BaseModel):
    question: str
    k: int = 5
    doc_id: Optional[str] = None


class AskSource(BaseModel):
    id: int
    doc_id: str
    meta: Dict[str, Any]


class AskResponse(BaseModel):
    answer: str
    sources: List[AskSource]
