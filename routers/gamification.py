from datetime import datetime
from typing import Any, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user_id
from database import get_session
from models.gamification import UserBadge, UserQuest
from models.history import ChatSessionDB, FeedbackRecord
from services.gamification_service import BADGE_CATALOG, QUEST_CATALOG, get_week_start

router = APIRouter(prefix="/gamification", tags=["gamification"])


class BadgeResponse(BaseModel):
    id: str
    earned_at: datetime


class QuestProgress(BaseModel):
    id: str
    name: str
    description: str
    target: int
    current_count: int
    completed: bool
    xp_reward: int


class MasteryItem(BaseModel):
    skill: str
    avg_score: float  # normalised 0.0–1.0
    session_count: int


# ---------------------------------------------------------------------------
# GET /gamification/badges
# ---------------------------------------------------------------------------
@router.get("/badges", response_model=List[BadgeResponse])
async def get_badges(
    db: AsyncSession = Depends(get_session),
    current_user_id: int = Depends(get_current_user_id),
):
    """Return all badges earned by the current user."""
    result = await db.execute(
        select(UserBadge)
        .where(UserBadge.user_id == current_user_id)
        .order_by(UserBadge.earned_at)
    )
    badges = result.scalars().all()
    return [BadgeResponse(id=b.badge_id, earned_at=b.earned_at) for b in badges]


# ---------------------------------------------------------------------------
# GET /gamification/quests
# ---------------------------------------------------------------------------
@router.get("/quests", response_model=List[QuestProgress])
async def get_quests(
    db: AsyncSession = Depends(get_session),
    current_user_id: int = Depends(get_current_user_id),
):
    """Return current-week quest progress.  Quests reset every Monday UTC."""
    week_start = get_week_start()
    result = await db.execute(
        select(UserQuest).where(
            UserQuest.user_id == current_user_id,
            UserQuest.week_start == week_start,
        )
    )
    quest_records: dict[str, UserQuest] = {
        q.quest_id: q for q in result.scalars().all()
    }

    progress: list[dict[str, Any]] = []
    for quest_def in QUEST_CATALOG:
        qid = quest_def["id"]
        record = quest_records.get(qid)
        progress.append(
            QuestProgress(
                id=qid,
                name=quest_def["name"],
                description=quest_def["description"],
                target=quest_def["target"],
                current_count=record.current_count if record else 0,
                completed=record.completed if record else False,
                xp_reward=quest_def["xp_reward"],
            )
        )
    return progress


# ---------------------------------------------------------------------------
# GET /gamification/mastery
# ---------------------------------------------------------------------------
@router.get("/mastery", response_model=List[MasteryItem])
async def get_mastery(
    db: AsyncSession = Depends(get_session),
    current_user_id: int = Depends(get_current_user_id),
):
    """
    Return per-skill aggregates derived from all stored feedback for this user.
    Each item represents one evaluation criterion aggregated across sessions.
    avg_score is the mean normalised score (0.0–1.0).
    """
    result = await db.execute(
        select(FeedbackRecord)
        .join(ChatSessionDB, FeedbackRecord.session_id == ChatSessionDB.id)
        .where(ChatSessionDB.user_id == current_user_id)
    )
    records = result.scalars().all()

    skill_data: dict[str, dict[str, Any]] = {}
    for record in records:
        for criterion in record.criteria or []:
            name = criterion.get("name", "Ukjent")
            score = criterion.get("score", 0)
            max_score = criterion.get("max_score", 10)
            if max_score and max_score > 0:
                if name not in skill_data:
                    skill_data[name] = {"total_normalized": 0.0, "count": 0}
                skill_data[name]["total_normalized"] += score / max_score
                skill_data[name]["count"] += 1

    return [
        MasteryItem(
            skill=name,
            avg_score=round(data["total_normalized"] / data["count"], 3),
            session_count=data["count"],
        )
        for name, data in sorted(skill_data.items(), key=lambda kv: -kv[1]["count"])
    ]
