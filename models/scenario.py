from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from database import Base

class Scenario(Base):
    __tablename__ = "scenarios"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    difficulty = Column(String(20), nullable=True)

    # brukes for filtering i appen (f.eks "konflikt", "skole", "skjermtid")
    category = Column(String(60), nullable=True)

    # “prompt template” eller “system context” som AI-agenten skal bruke
    system_prompt = Column(Text, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
