"""Handlers for tool function calls using LangChain."""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from langchain_core.tools import tool

from src.memory.gdrive_memory import GoogleDriveStorage
from src.models.user_profile import UserProfile
from src.models.workout_plan import WorkoutPlan
from src.models.workout_log import WorkoutLog
from src.utils.storage_helpers import (
    create_user_profile_from_dict,
    create_workout_plan_from_dict,
    create_workout_log_from_dict,
)

logger = logging.getLogger(__name__)

# Global storage and user email (will be set by app.py)
_storage: Optional[GoogleDriveStorage] = None
_user_email: str = ""


def set_storage_context(storage: GoogleDriveStorage, user_email: str) -> None:
    """Set storage and user context for tools."""
    global _storage, _user_email
    _storage = storage
    _user_email = user_email


@tool
def save_user_profile(
    goals: List[str],
    fitness_level: str,
    schedule: Optional[Dict[str, str]] = None,
    health_conditions: Optional[List[str]] = None,
    equipment_available: Optional[List[str]] = None,
    preferences: Optional[Dict[str, Any]] = None,
    additional_notes: Optional[str] = None,
) -> str:
    """Зберегти або оновити профіль користувача на Google Drive.

    Використовуй цю функцію після завершення опитування (onboarding) або коли користувач оновлює свої дані.

    Args:
        goals: Фітнес-цілі користувача (схуднення, набір маси, витривалість, сила)
        fitness_level: Рівень підготовки (beginner, intermediate, advanced)
        schedule: Доступні дні та час тренувань, наприклад {"Понеділок": "18:00-19:00"}
        health_conditions: Травми, хвороби, обмеження здоров'я
        equipment_available: Доступне обладнання (власна вага, гантелі, штанга, тощо)
        preferences: Вподобання щодо тренувань (має бути об'єкт!), наприклад {"training_type": "силові"}
        additional_notes: Довільні примітки про користувача для майбутніх взаємодій

    Returns:
        Повідомлення про успіх або помилку
    """
    if not _storage:
        return "ПОМИЛКА: Storage не ініціалізовано"

    try:
        logger.info(f"Saving user profile for {_user_email}")

        profile_data = {
            "goals": goals,
            "fitness_level": fitness_level,
            "schedule": schedule or {},
            "health_conditions": health_conditions or [],
            "equipment_available": equipment_available or [],
            "preferences": preferences or {},
            "additional_notes": additional_notes or "",
        }

        profile = create_user_profile_from_dict(_user_email, profile_data)
        profile_dict = profile.model_dump(mode="json")
        _storage.save_json("profile.json", profile_dict)

        logger.info("User profile saved successfully")
        return f"✅ Профіль успішно збережено! Цілі: {', '.join(goals)}, Рівень: {fitness_level}"

    except Exception as e:
        error_msg = f"❌ Помилка збереження профілю: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool
def save_workout_plan(
    weeks: int,
    days_per_week: int,
    plan: Dict[str, List[Dict[str, Any]]],
    notes: Optional[str] = None,
) -> str:
    """Зберегти новий план тренувань на Google Drive.

    Args:
        weeks: Кількість тижнів у плані
        days_per_week: Кількість тренувань на тиждень
        plan: Структура плану по тижнях. Кожен ключ - це week_1, week_2, тощо.
              Кожен тиждень - це МАСИВ об'єктів днів.
        notes: Загальні нотатки про план

    Returns:
        Повідомлення про успіх або помилку
    """
    if not _storage:
        return "ПОМИЛКА: Storage не ініціалізовано"

    try:
        logger.info(f"Saving workout plan for {_user_email}")

        plan_data = {
            "weeks": weeks,
            "days_per_week": days_per_week,
            "plan": plan,
            "notes": notes or "",
        }

        workout_plan = create_workout_plan_from_dict(_user_email, plan_data)
        plan_dict = workout_plan.model_dump(mode="json")

        _storage.save_json("current_plan.json", plan_dict)

        # Save to history
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        history_filename = f"plan_{timestamp}.json"
        _storage.save_json(history_filename, plan_dict, subfolder="plans_history")

        logger.info("Workout plan saved successfully")
        return f"✅ План тренувань на {weeks} тижнів успішно збережено на Google Drive!"

    except Exception as e:
        error_msg = f"❌ Помилка збереження плану: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool
def save_workout_log(
    completed_exercises: List[Dict[str, Any]],
    duration_minutes: int,
    feedback: Optional[str] = None,
) -> str:
    """Зберегти журнал виконаного тренування на Google Drive.

    Args:
        completed_exercises: Список виконаних вправ. Кожна вправа має мати:
                            - exercise_name: назва вправи
                            - sets_completed: кількість підходів
                            - reps_per_set: масив повторів [12, 10, 8]
                            - weight_per_set: масив ваг в кг [0, 0, 0] (для власної ваги використовуй 0)
                            - notes: нотатки про виконання
        duration_minutes: Тривалість тренування в хвилинах
        feedback: Загальний фідбек користувача після тренування

    Returns:
        Повідомлення про успіх або помилку
    """
    if not _storage:
        return "ПОМИЛКА: Storage не ініціалізовано"

    try:
        logger.info(f"Saving workout log for {_user_email}")

        log_data = {
            "completed_exercises": completed_exercises,
            "duration_minutes": duration_minutes,
            "feedback": feedback or "",
        }

        workout_log = create_workout_log_from_dict(_user_email, log_data)
        log_dict = workout_log.model_dump(mode="json")

        # Save to logs history
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"log_{timestamp}.json"
        _storage.save_json(log_filename, log_dict, subfolder="workout_logs")

        logger.info("Workout log saved successfully")
        return f"✅ Журнал тренування збережено! Виконано {len(completed_exercises)} вправ за {duration_minutes} хвилин"

    except Exception as e:
        error_msg = f"❌ Помилка збереження журналу: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool
def get_user_profile() -> str:
    """Завантажити профіль користувача з Google Drive.

    Returns:
        Профіль користувача або повідомлення про відсутність
    """
    if not _storage:
        return "ПОМИЛКА: Storage не ініціалізовано"

    try:
        logger.info(f"Loading user profile for {_user_email}")
        profile_data = _storage.load_json("profile.json")

        if not profile_data:
            return "Профіль користувача ще не створено. Почни з опитування."

        profile = UserProfile(**profile_data)
        logger.info("User profile loaded successfully")

        # Format profile for display
        output = f"""**Профіль користувача:**
- Рівень: {profile.fitness_level}
- Цілі: {', '.join(profile.goals)}
"""
        if profile.schedule:
            output += "- Розклад:\n"
            for day, time in profile.schedule.items():
                output += f"  - {day}: {time}\n"

        if profile.health_conditions:
            output += f"- Обмеження здоров'я: {', '.join(profile.health_conditions)}\n"

        if profile.equipment_available:
            output += f"- Доступне обладнання: {', '.join(profile.equipment_available)}\n"

        if profile.additional_notes:
            output += f"\n**Додаткові примітки:**\n{profile.additional_notes}\n"

        return output

    except Exception as e:
        error_msg = f"❌ Помилка завантаження профілю: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool
def get_current_plan() -> str:
    """Завантажити поточний активний план тренувань користувача з Google Drive.

    Returns:
        Активний план тренувань або повідомлення про відсутність
    """
    if not _storage:
        return "ПОМИЛКА: Storage не ініціалізовано"

    try:
        logger.info(f"Loading current plan for {_user_email}")
        plan_data = _storage.load_json("current_plan.json")

        if not plan_data:
            return "Активний план тренувань не знайдено. Створи новий план."

        plan = WorkoutPlan(**plan_data)
        logger.info(f"Current plan loaded: {plan.weeks} weeks, {plan.days_per_week} days/week")

        # Format plan summary
        output = f"""**Активний план тренувань:**
- Тижнів: {plan.weeks}
- Тренувань на тиждень: {plan.days_per_week}
- Статус: {plan.status}
"""
        if plan.notes:
            output += f"- Нотатки: {plan.notes}\n"

        # Count total workouts
        total_workouts = sum(len(days) for days in plan.plan.values())
        output += f"- Всього тренувань у плані: {total_workouts}\n"

        return output

    except Exception as e:
        error_msg = f"❌ Помилка завантаження плану: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool
def get_workout_logs(limit: int = 10) -> str:
    """Завантажити журнали тренувань користувача з Google Drive.

    Args:
        limit: Максимальна кількість логів для завантаження (за замовчуванням 10)

    Returns:
        Список журналів тренувань
    """
    if not _storage:
        return "ПОМИЛКА: Storage не ініціалізовано"

    try:
        logger.info(f"Loading workout logs for {_user_email}, limit={limit}")

        # List all log files
        files = _storage.list_files(subfolder="workout_logs")
        if not files:
            return "Журнали тренувань не знайдено. Почни перше тренування!"

        # Sort by creation time (newest first) and limit
        files.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
        files = files[:limit]

        # Load log data
        logs = []
        for file_info in files:
            try:
                log_data = _storage.load_json(file_info["name"], subfolder="workout_logs")
                if log_data:
                    logs.append(WorkoutLog(**log_data))
            except Exception as e:
                logger.warning(f"Failed to load log {file_info['name']}: {e}")
                continue

        logger.info(f"Loaded {len(logs)} workout logs")

        # Format logs summary
        output = f"**Останні {len(logs)} тренувань:**\n\n"
        for i, log in enumerate(logs, 1):
            date_str = log.date.strftime("%Y-%m-%d %H:%M")
            output += f"{i}. {date_str} - {len(log.completed_exercises)} вправ, {log.duration_minutes} хв\n"
            if log.feedback:
                output += f"   Фідбек: {log.feedback}\n"

        return output

    except Exception as e:
        error_msg = f"❌ Помилка завантаження журналів: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def get_all_tools() -> List:
    """Get all tool functions for LangChain."""
    return [
        save_user_profile,
        save_workout_plan,
        save_workout_log,
        get_user_profile,
        get_current_plan,
        get_workout_logs,
    ]

