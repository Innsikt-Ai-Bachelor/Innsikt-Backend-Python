from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any


Role = Literal["user", "assistant", "system"]


class CreateSessionResponse(BaseModel):
    session_id: str


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str
    # Valgfritt: hvis frontend vil sende ekstra info senere
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Source(BaseModel):
    source: str
    chunk_id: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


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
