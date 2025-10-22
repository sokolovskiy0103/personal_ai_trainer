"""Workout plan data models."""

from datetime import datetime
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


class Exercise(BaseModel):
    """Single exercise with parameters."""

    name: str = Field(..., description="Exercise name in Ukrainian")
    sets: int = Field(..., ge=1, description="Number of sets")
    reps: Union[int, str] = Field(
        ..., description="Number of reps per set, e.g., 10 or '10-12' or 'до відмови'"
    )
    weight: Optional[float] = Field(None, description="Weight in kg (if applicable)")
    rest_seconds: int = Field(60, ge=0, description="Rest time between sets in seconds")
    instructions: str = Field(
        default="", description="Exercise instructions and technique tips"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Віджимання",
                "sets": 3,
                "reps": "10-12",
                "weight": None,
                "rest_seconds": 90,
                "instructions": "Тримай спину прямо, опускайся до кута 90 градусів",
            }
        }


class WorkoutDay(BaseModel):
    """Single workout day with exercises."""

    day_name: str = Field(..., description="Day name, e.g., 'Понеділок' or 'Верх тіла'")
    exercises: List[Exercise] = Field(default_factory=list)
    notes: str = Field(default="", description="Additional notes for the day")
    estimated_duration_minutes: int = Field(
        45, ge=0, description="Estimated workout duration"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "day_name": "Понеділок - Верх тіла",
                "exercises": [
                    {
                        "name": "Віджимання",
                        "sets": 3,
                        "reps": "10-12",
                        "rest_seconds": 90,
                    }
                ],
                "notes": "Розминка 5-10 хвилин перед початком",
                "estimated_duration_minutes": 45,
            }
        }


class WorkoutPlan(BaseModel):
    """Complete workout plan for a user."""

    plan_id: str = Field(..., description="Unique plan ID (UUID)")
    user_id: str = Field(..., description="User email")
    weeks: int = Field(..., ge=1, le=52, description="Plan duration in weeks")
    days_per_week: int = Field(..., ge=1, le=7, description="Training days per week")
    plan: Dict[str, List[WorkoutDay]] = Field(
        default_factory=dict,
        description="Workout plan organized by weeks, e.g., {'week_1': [day1, day2, ...]}",
    )
    created_at: datetime = Field(default_factory=datetime.now)
    status: str = Field(
        default="active", description="Plan status: active, completed, paused"
    )
    notes: str = Field(default="", description="General plan notes and goals")

    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "user@example.com",
                "weeks": 8,
                "days_per_week": 3,
                "plan": {
                    "week_1": [
                        {
                            "day_name": "Понеділок - Верх тіла",
                            "exercises": [],
                            "notes": "",
                        }
                    ]
                },
                "status": "active",
                "notes": "План для схуднення та покращення витривалості",
            }
        }
