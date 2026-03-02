from datetime import datetime

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional


Role = Literal["user", "assistant", "system"]


class CreateSessionResponse(BaseModel):
    session_id: str


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Source(BaseModel):
    source: str
    doc_id: Optional[str] = None
    chunk_id: Optional[int] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    session_id: str
    assistant_message: str
    used_rag: bool = False
    sources: List[Source] = Field(default_factory=list)


class FinishRequest(BaseModel):
    session_id: str


class CriterionScore(BaseModel):
    name: str
    score: int
    max_score: int
    reason: str


class FinishResponse(BaseModel):
    session_id: str
    total_score: int
    criteria: List[CriterionScore]
    feedback: List[str]
    sources: List[Source] = Field(default_factory=list)


class StoredMessage(BaseModel):
    role: Role
    content: str


class CreateSessionRequest(BaseModel):
    scenario_id: int
    title: str


class SessionListItem(BaseModel):
    session_id: str
    scenario_id: int | None
    title: str | None
    saved_at: datetime
    turn_count: int
    last_message_preview: str | None
