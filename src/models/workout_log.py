"""Workout log data models."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .workout_plan import Exercise


class CompletedExercise(BaseModel):
    """Completed exercise with actual performance data."""

    exercise_name: str = Field(..., description="Exercise name")
    sets_completed: int = Field(..., ge=0, description="Number of sets completed")
    reps_per_set: List[int] = Field(
        default_factory=list, description="Actual reps per set, e.g., [10, 8, 6]"
    )
    weight_per_set: List[float] = Field(
        default_factory=list, description="Weight used per set in kg"
    )
    notes: str = Field(
        default="",
        description="Notes about performance: 'важко', 'легко', 'біль в коліні', etc.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "exercise_name": "Віджимання",
                "sets_completed": 3,
                "reps_per_set": [12, 10, 8],
                "weight_per_set": [0, 0, 0],
                "notes": "Останній підхід був важким",
            }
        }


class WorkoutLog(BaseModel):
    """Log of a completed workout session."""

    log_id: str = Field(..., description="Unique log ID (UUID)")
    user_id: str = Field(..., description="User email")
    date: datetime = Field(default_factory=datetime.now, description="Workout date")
    planned_exercises: List[Exercise] = Field(
        default_factory=list, description="Exercises that were planned"
    )
    completed_exercises: List[CompletedExercise] = Field(
        default_factory=list, description="Exercises that were completed"
    )
    feedback: str = Field(
        default="",
        description="User feedback after workout: самопочуття, складність, енергія",
    )
    duration_minutes: int = Field(0, ge=0, description="Actual workout duration")
    skipped: bool = Field(default=False, description="Was the workout skipped?")
    skip_reason: Optional[str] = Field(None, description="Reason for skipping (if applicable)")

    class Config:
        json_schema_extra = {
            "example": {
                "log_id": "123e4567-e89b-12d3-a456-426614174001",
                "user_id": "user@example.com",
                "date": "2025-01-15T18:00:00",
                "planned_exercises": [],
                "completed_exercises": [
                    {
                        "exercise_name": "Віджимання",
                        "sets_completed": 3,
                        "reps_per_set": [12, 10, 8],
                        "weight_per_set": [0, 0, 0],
                        "notes": "Добре відчував м'язи",
                    }
                ],
                "feedback": "Відчував себе добре, але останні підходи були важкими",
                "duration_minutes": 45,
                "skipped": False,
            }
        }
