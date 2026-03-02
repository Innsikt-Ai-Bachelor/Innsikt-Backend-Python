from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


class Scenario(BaseModel):
    id: int
    title: str
    description: str
    durationMin: str
    difficulty: str
    emoji: str


_SCENARIOS: list[Scenario] = [
    Scenario(
        id=1,
        title="Bedtime Resistance",
        description="Your child refuses to go to bed and keeps asking for more time.",
        durationMin="5–10 min",
        difficulty="Moderate",
        emoji="🌙",
    ),
    Scenario(
        id=2,
        title="Homework Frustration",
        description="Your child is upset and refuses to do homework.",
        durationMin="10–15 min",
        difficulty="Challenging",
        emoji="📚",
    ),
    Scenario(
        id=3,
        title="Sharing Conflict",
        description="Your child won't share toys with a sibling.",
        durationMin="5–8 min",
        difficulty="Easy",
        emoji="🧸",
    ),
    Scenario(
        id=4,
        title="Morning Rush",
        description="Your child is moving slowly and you're running late.",
        durationMin="8–12 min",
        difficulty="Moderate",
        emoji="⏰",
    ),
]


@router.get("/", response_model=list[Scenario])
async def get_scenarios():
    return _SCENARIOS
