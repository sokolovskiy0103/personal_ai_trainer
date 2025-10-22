"""User profile data model."""

from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """User profile with fitness goals and preferences."""

    user_id: str = Field(..., description="User email from OAuth")
    goals: List[str] = Field(
        default_factory=list,
        description="Fitness goals: схуднення, набір маси, витривалість, сила",
    )
    schedule: Dict[str, str] = Field(
        default_factory=dict,
        description="Available training days and times, e.g., {'Понеділок': '18:00-19:30'}",
    )
    health_conditions: List[str] = Field(
        default_factory=list, description="Health issues, injuries, limitations"
    )
    fitness_level: str = Field(
        default="beginner", description="Fitness level: beginner, intermediate, advanced"
    )
    equipment_available: List[str] = Field(
        default_factory=list,
        description="Available equipment: власна вага, гантелі, штанга, тренажери, etc.",
    )
    preferences: Dict[str, Any] = Field(
        default_factory=dict,
        description="Exercise preferences, dislikes, additional info",
    )
    additional_notes: str = Field(
        default="",
        description="Довільні примітки від AI тренера про користувача. Будь-яка важлива інформація, яка не підпадає під інші категорії.",
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def update(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now()

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user@example.com",
                "goals": ["схуднення", "витривалість"],
                "schedule": {"Понеділок": "18:00-19:00", "Середа": "18:00-19:00"},
                "health_conditions": ["біль в коліні"],
                "fitness_level": "beginner",
                "equipment_available": ["гантелі", "власна вага"],
                "preferences": {"dislikes": ["біг"]},
            }
        }
