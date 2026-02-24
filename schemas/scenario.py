from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ScenarioOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2 (bruk orm_mode=True hvis v1)
