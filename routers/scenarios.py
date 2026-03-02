from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_session
from models.scenario import Scenario


class ScenarioCreate(BaseModel):
	title: str
	description: str | None = None
	difficulty: str | None = None
	category: str | None = None
	system_prompt: str
	is_active: bool = True


class ScenarioUpdate(BaseModel):
	title: str | None = None
	description: str | None = None
	difficulty: str | None = None
	category: str | None = None
	system_prompt: str | None = None
	is_active: bool | None = None


class ScenarioPublic(BaseModel):
	id: int
	title: str
	description: str | None = None
	difficulty: str | None = None
	category: str | None = None
	system_prompt: str
	is_active: bool
	created_at: datetime
	updated_at: datetime | None = None


router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _to_public(scenario: Scenario) -> ScenarioPublic:
	return ScenarioPublic(
		id=scenario.id,
		title=scenario.title,
		description=scenario.description,
		difficulty=scenario.difficulty,
		category=scenario.category,
		system_prompt=scenario.system_prompt,
		is_active=scenario.is_active,
		created_at=scenario.created_at,
		updated_at=scenario.updated_at,
	)


@router.get("/", response_model=list[ScenarioPublic])
async def get_scenarios(
	session: AsyncSession = Depends(get_session),
	current_user: str = Depends(get_current_user),
):
	_ = current_user
	result = await session.execute(select(Scenario).order_by(Scenario.id.asc()))
	scenarios = result.scalars().all()
	return [_to_public(scenario) for scenario in scenarios]


@router.post("/", response_model=ScenarioPublic, status_code=status.HTTP_201_CREATED)
async def create_scenario(
	scenario_in: ScenarioCreate,
	session: AsyncSession = Depends(get_session),
	current_user: str = Depends(get_current_user),
):
	_ = current_user
	scenario = Scenario(
		title=scenario_in.title,
		description=scenario_in.description,
		difficulty=scenario_in.difficulty,
		category=scenario_in.category,
		system_prompt=scenario_in.system_prompt,
		is_active=scenario_in.is_active,
	)
	session.add(scenario)
	await session.commit()
	await session.refresh(scenario)
	return _to_public(scenario)


@router.put("/{scenario_id}", response_model=ScenarioPublic)
async def update_scenario(
	scenario_id: int,
	scenario_in: ScenarioUpdate,
	session: AsyncSession = Depends(get_session),
	current_user: str = Depends(get_current_user),
):
	_ = current_user
	result = await session.execute(select(Scenario).where(Scenario.id == scenario_id))
	scenario = result.scalar_one_or_none()
	if not scenario:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")

	if scenario_in.title is not None:
		scenario.title = scenario_in.title
	if scenario_in.description is not None:
		scenario.description = scenario_in.description
	if scenario_in.difficulty is not None:
		scenario.difficulty = scenario_in.difficulty
	if scenario_in.category is not None:
		scenario.category = scenario_in.category
	if scenario_in.system_prompt is not None:
		scenario.system_prompt = scenario_in.system_prompt
	if scenario_in.is_active is not None:
		scenario.is_active = scenario_in.is_active

	await session.commit()
	await session.refresh(scenario)
	return _to_public(scenario)
