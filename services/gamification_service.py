from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db import User
from models.gamification import UserBadge, UserQuest
from models.history import ChatSessionDB, FeedbackRecord

# ---------------------------------------------------------------------------
# Badge catalogue — keep in sync with the frontend badge definitions.
# ---------------------------------------------------------------------------
BADGE_CATALOG: list[dict[str, str]] = [
    {
        "id": "first_session",
        "name": "Første steg",
        "description": "Fullfør din første økt",
        "icon": "🎯",
    },
    {
        "id": "session_5",
        "name": "Ivrig lærling",
        "description": "Fullfør 5 økter",
        "icon": "⭐",
    },
    {
        "id": "session_25",
        "name": "Erfaren",
        "description": "Fullfør 25 økter",
        "icon": "🏆",
    },
    {
        "id": "high_scorer",
        "name": "Høy score",
        "description": "Oppnå 80 poeng eller mer i en økt",
        "icon": "🌟",
    },
    {
        "id": "perfectionist",
        "name": "Perfeksjonist",
        "description": "Oppnå 100 poeng i en økt",
        "icon": "💯",
    },
    {
        "id": "explorer",
        "name": "Utforsker",
        "description": "Fullfør økter i minst 3 ulike scenarioer",
        "icon": "🧭",
    },
    {
        "id": "weekly_warrior",
        "name": "Ukens kriger",
        "description": "Fullfør 3 eller flere økter i én uke",
        "icon": "💪",
    },
]

# ---------------------------------------------------------------------------
# Quest catalogue — weekly repeatable quests.
# ---------------------------------------------------------------------------
QUEST_CATALOG: list[dict[str, Any]] = [
    {
        "id": "weekly_sessions",
        "name": "Ukentlig trening",
        "description": "Fullfør 3 økter denne uken",
        "target": 3,
        "xp_reward": 50,
    },
    {
        "id": "weekly_high_score",
        "name": "Ukentlig bragd",
        "description": "Oppnå minst 70 poeng i en økt denne uken",
        "target": 1,
        "xp_reward": 30,
    },
]

# ---------------------------------------------------------------------------
# XP / level helpers
# ---------------------------------------------------------------------------
_XP_BASE = 10        # XP awarded for finishing any session
_XP_PER_SCORE = 1    # additional XP per total_score point (0-100)


def compute_level(xp: int) -> int:
    """Level = 1 + xp // 200, capped at 99."""
    return min(99, 1 + max(0, xp) // 200)


def get_week_start() -> datetime:
    """Return Monday 00:00:00 UTC of the current ISO week."""
    today = datetime.now(timezone.utc)
    monday = today - timedelta(days=today.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Main trigger — called once per unique completed session.
# ---------------------------------------------------------------------------
async def award_xp_and_check_badges(
    db: AsyncSession,
    user_id: int,
    total_score: int,
) -> list[str]:
    """
    Award XP for the finished session, evaluate all badge triggers, and update
    weekly quest progress (including quest-completion XP bonuses).

    Returns a list of badge IDs that were *newly* earned in this call.

    The caller is responsible for idempotency: this should only be invoked
    when the FeedbackRecord for the session was *created* (not updated).
    """
    # --- 1. Load user ---
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return []

    # --- 2. Award base XP ---
    xp_earned = _XP_BASE + total_score * _XP_PER_SCORE
    user.xp = (user.xp or 0) + xp_earned

    # --- 3. Gather stats required by badge / quest triggers ---
    # Total sessions with feedback for this user (includes the one just committed)
    session_count: int = (
        await db.execute(
            select(func.count(ChatSessionDB.id))
            .join(FeedbackRecord, ChatSessionDB.id == FeedbackRecord.session_id)
            .where(ChatSessionDB.user_id == user_id)
        )
    ).scalar_one() or 0

    # Unique non-null scenario IDs across completed sessions
    unique_scenarios: int = (
        await db.execute(
            select(func.count(distinct(ChatSessionDB.scenario_id)))
            .join(FeedbackRecord, ChatSessionDB.id == FeedbackRecord.session_id)
            .where(ChatSessionDB.user_id == user_id)
            .where(ChatSessionDB.scenario_id.isnot(None))
        )
    ).scalar_one() or 0

    # Completed sessions in the current calendar week
    week_start = get_week_start()
    weekly_count: int = (
        await db.execute(
            select(func.count(ChatSessionDB.id))
            .join(FeedbackRecord, ChatSessionDB.id == FeedbackRecord.session_id)
            .where(ChatSessionDB.user_id == user_id)
            .where(ChatSessionDB.created_at >= week_start)
        )
    ).scalar_one() or 0

    # --- 4. Which badges does the user already have? ---
    existing_badges: set[str] = set(
        (
            await db.execute(
                select(UserBadge.badge_id).where(UserBadge.user_id == user_id)
            )
        ).scalars().all()
    )

    # --- 5. Evaluate badge triggers ---
    _TRIGGERS: dict[str, tuple[str, int]] = {
        "first_session":  ("session_count",    1),
        "session_5":      ("session_count",    5),
        "session_25":     ("session_count",   25),
        "high_scorer":    ("score_gte",        80),
        "perfectionist":  ("score_gte",       100),
        "explorer":       ("unique_scenarios",  3),
        "weekly_warrior": ("weekly_sessions",   3),
    }

    new_badges: list[str] = []
    for badge_id, (trigger_type, threshold) in _TRIGGERS.items():
        if badge_id in existing_badges:
            continue
        earned = (
            (trigger_type == "session_count"    and session_count    >= threshold)
            or (trigger_type == "score_gte"       and total_score      >= threshold)
            or (trigger_type == "unique_scenarios" and unique_scenarios >= threshold)
            or (trigger_type == "weekly_sessions"  and weekly_count    >= threshold)
        )
        if earned:
            db.add(UserBadge(user_id=user_id, badge_id=badge_id))
            new_badges.append(badge_id)

    # --- 6. Update weekly quest progress ---
    for quest_def in QUEST_CATALOG:
        quest_id = quest_def["id"]
        quest_result = await db.execute(
            select(UserQuest).where(
                UserQuest.user_id == user_id,
                UserQuest.quest_id == quest_id,
                UserQuest.week_start == week_start,
            )
        )
        quest = quest_result.scalar_one_or_none()

        if quest is None:
            quest = UserQuest(
                user_id=user_id,
                quest_id=quest_id,
                week_start=week_start,
                current_count=0,
                completed=False,
            )
            db.add(quest)

        if quest.completed:
            continue

        if quest_id == "weekly_sessions":
            quest.current_count = weekly_count
            if quest.current_count >= quest_def["target"]:
                quest.completed = True
                user.xp += quest_def["xp_reward"]

        elif quest_id == "weekly_high_score":
            if total_score >= 70:
                quest.current_count = 1
                quest.completed = True
                user.xp += quest_def["xp_reward"]

    # --- 7. Recompute level (after all XP bonuses) ---
    user.level = compute_level(user.xp)

    await db.commit()
    return new_badges
