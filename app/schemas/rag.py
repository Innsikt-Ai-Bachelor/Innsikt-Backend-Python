from pydantic import BaseModel
from typing import Any, Dict, List

class IngestItem(BaseModel):
    content: str
    metadata: Dict[str, Any] = {}

class IngestRequest(BaseModel):
    items: List[IngestItem]

class AskRequest(BaseModel):
    question: str
    k: int = 5
