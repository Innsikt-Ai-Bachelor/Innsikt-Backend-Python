from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import verify_token
from database import get_session
from models.scenario import Scenario
from models.scenario_session import ScenarioSession
from schemas.scenario import ScenarioOut
from schemas.scenario_session import ScenarioSessionCreate, ScenarioSessionOut

router = APIRouter(prefix="/scenarios", tags=["Scenarios"])


@router.post("/start", response_model=ScenarioSessionOut)
async def start_scenario_session(
    payload: ScenarioSessionCreate,
    session: AsyncSession = Depends(get_session),
    token_payload: dict = Depends(verify_token),  # gives you uid + sub
):
    user_id = token_payload.get("uid")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing uid in token")

    res = await session.execute(select(Scenario).where(Scenario.id == payload.scenario_id))
    scenario = res.scalar_one_or_none()

    if not scenario or not scenario.is_active:
        raise HTTPException(status_code=404, detail="Scenario not found")

    sc_session = ScenarioSession(user_id=user_id, scenario_id=scenario.id)
    session.add(sc_session)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Scenario session could not be created due to a conflict",
        )
    except Exception:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the scenario session",
        )
    await session.refresh(sc_session)
    return sc_session


@router.get("", response_model=List[ScenarioOut])
async def list_scenarios(
    session: AsyncSession = Depends(get_session),
    category: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
):
    stmt = select(Scenario)
    if active_only:
        stmt = stmt.where(Scenario.is_active == True)  # noqa: E712
    if category:
        stmt = stmt.where(Scenario.category == category)

    stmt = stmt.order_by(Scenario.id.asc())
    res = await session.execute(stmt)
    return res.scalars().all()


@router.get("/{scenario_id}", response_model=ScenarioOut)
async def get_scenario(scenario_id: int, session: AsyncSession = Depends(get_session)):
    res = await session.execute(select(Scenario).where(Scenario.id == scenario_id))
    scenario = res.scalar_one_or_none()

    if not scenario or not scenario.is_active:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario