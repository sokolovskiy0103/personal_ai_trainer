"""Helper functions for AI to interact with storage."""

import uuid
from datetime import datetime
from typing import Any, Dict

from src.models.user_profile import UserProfile
from src.models.workout_log import CompletedExercise, WorkoutLog
from src.models.workout_plan import Exercise, WorkoutDay, WorkoutPlan


def create_user_profile_from_dict(user_id: str, profile_data: Dict[str, Any]) -> UserProfile:
    preferences = profile_data.get("preferences", {})
    if not isinstance(preferences, dict):
        if isinstance(preferences, list):
            preferences = {"items": preferences}
        elif isinstance(preferences, str):
            preferences = {"note": preferences}
        else:
            preferences = {}

    return UserProfile(
        user_id=user_id,
        goals=profile_data.get("goals", []),
        schedule=profile_data.get("schedule", {}),
        health_conditions=profile_data.get("health_conditions", []),
        fitness_level=profile_data.get("fitness_level", "beginner"),
        equipment_available=profile_data.get("equipment_available", []),
        preferences=preferences,
        additional_notes=profile_data.get("additional_notes", ""),
    )


def create_workout_plan_from_dict(user_id: str, plan_data: Dict[str, Any]) -> WorkoutPlan:
    parsed_plan = {}
    for week_key, days in plan_data.get("plan", {}).items():
        if not isinstance(days, list):
            continue

        parsed_days = []
        for day_data in days:
            if not isinstance(day_data, dict):
                if isinstance(day_data, str):
                    day_data = {"day_name": day_data, "exercises": []}
                else:
                    continue

            exercises = []
            exercises_data = day_data.get("exercises", [])
            if isinstance(exercises_data, list):
                for ex in exercises_data:
                    if isinstance(ex, dict):
                        try:
                            exercises.append(Exercise(**ex))
                        except Exception:
                            continue

            workout_day = WorkoutDay(
                day_name=day_data.get("day_name", "Unnamed Day"),
                exercises=exercises,
                notes=day_data.get("notes", ""),
                estimated_duration_minutes=day_data.get("estimated_duration_minutes", 45),
            )
            parsed_days.append(workout_day)

        if parsed_days:
            parsed_plan[week_key] = parsed_days

    return WorkoutPlan(
        plan_id=str(uuid.uuid4()),
        user_id=user_id,
        weeks=plan_data.get("weeks", 4),
        days_per_week=plan_data.get("days_per_week", 3),
        plan=parsed_plan,
        status="active",
        notes=plan_data.get("notes", ""),
    )


def create_workout_log_from_dict(user_id: str, log_data: Dict[str, Any]) -> WorkoutLog:
    planned_exercises = []
    for ex_data in log_data.get("planned_exercises", []):
        if isinstance(ex_data, dict):
            planned_exercises.append(Exercise(**ex_data))

    completed_exercises = []
    for comp_ex in log_data.get("completed_exercises", []):
        if isinstance(comp_ex, dict):
            weight_per_set = comp_ex.get("weight_per_set", [])
            cleaned_weights = []
            weight_notes = []

            for i, weight in enumerate(weight_per_set):
                if isinstance(weight, str):
                    cleaned_weights.append(0.0)
                    weight_notes.append(f"Підхід {i + 1}: {weight}")
                elif isinstance(weight, (int, float)):
                    cleaned_weights.append(float(weight))
                else:
                    cleaned_weights.append(0.0)

            exercise_notes = comp_ex.get("notes", "")
            if weight_notes:
                weight_note_text = "; ".join(weight_notes)
                if exercise_notes:
                    exercise_notes = f"{exercise_notes} ({weight_note_text})"
                else:
                    exercise_notes = weight_note_text

            cleaned_comp_ex = {
                "exercise_name": comp_ex.get("exercise_name", "Unknown"),
                "sets_completed": comp_ex.get("sets_completed", 0),
                "reps_per_set": comp_ex.get("reps_per_set", []),
                "weight_per_set": cleaned_weights,
                "notes": exercise_notes,
            }

            try:
                completed_exercises.append(CompletedExercise(**cleaned_comp_ex))
            except Exception:
                continue

    workout_date = log_data.get("date")
    if isinstance(workout_date, str):
        workout_date = datetime.fromisoformat(workout_date)
    elif workout_date is None:
        workout_date = datetime.now()

    return WorkoutLog(
        log_id=str(uuid.uuid4()),
        user_id=user_id,
        date=workout_date,
        planned_exercises=planned_exercises,
        completed_exercises=completed_exercises,
        feedback=log_data.get("feedback", ""),
        duration_minutes=log_data.get("duration_minutes", 0),
        skipped=log_data.get("skipped", False),
        skip_reason=log_data.get("skip_reason"),
    )
