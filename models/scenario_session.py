from sqlalchemy import Column, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship
from database import Base

class ScenarioSession(Base):
    __tablename__ = "scenario_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # valgfritt:
    # ended_at = Column(DateTime(timezone=True), nullable=True)

    scenario = relationship("Scenario")
