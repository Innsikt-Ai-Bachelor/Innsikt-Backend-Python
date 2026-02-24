from pydantic import BaseModel
from datetime import datetime

class ScenarioSessionCreate(BaseModel):
    scenario_id: int

class ScenarioSessionOut(BaseModel):
    id: int
    scenario_id: int
    started_at: datetime

    class Config:
        from_attributes = True
