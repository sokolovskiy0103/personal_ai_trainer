"""Handlers for tool function calls using LangChain."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from src.memory.gdrive_memory import GoogleDriveStorage
from src.utils.storage_helpers import (
    create_user_profile_from_dict,
    create_workout_log_from_dict,
    create_workout_plan_from_dict,
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
    """Save or update user profile to Google Drive.

    Use this function after completing onboarding or when user updates their data.

    Args:
        goals: User's fitness goals (weight loss, muscle gain, endurance, strength)
        fitness_level: Fitness level (beginner, intermediate, advanced)
        schedule: Available days and training times, e.g. {"Monday": "18:00-19:00"}
        health_conditions: Injuries, illnesses, health limitations
        equipment_available: Available equipment (bodyweight, dumbbells, barbell, etc.)
        preferences: Training preferences (must be object!), e.g. {"training_type": "strength"}
        additional_notes: Arbitrary notes about user for future interactions

    Returns:
        Success or error message
    """
    if not _storage:
        return "ERROR: Storage not initialized"

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
        return f"✅ Profile saved successfully! Goals: {', '.join(goals)}, Level: {fitness_level}"

    except Exception as e:
        error_msg = f"❌ Error saving profile: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool
def save_workout_plan(
    weeks: int,
    days_per_week: int,
    plan: Dict[str, List[Dict[str, Any]]],
    notes: Optional[str] = None,
) -> str:
    """Save new workout plan to Google Drive.

    Args:
        weeks: Number of weeks in the plan
        days_per_week: Number of workouts per week
        plan: Plan structure by weeks. Each key is week_1, week_2, etc.
              Each week is an ARRAY of day objects.
        notes: General notes about the plan

    Returns:
        Success or error message
    """
    if not _storage:
        return "ERROR: Storage not initialized"

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
        return f"✅ Workout plan for {weeks} weeks saved successfully to Google Drive!"

    except Exception as e:
        error_msg = f"❌ Error saving plan: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool
def save_workout_log(
    completed_exercises: List[Dict[str, Any]],
    duration_minutes: int,
    feedback: Optional[str] = None,
) -> str:
    """Save completed workout log to Google Sheets.

    Args:
        completed_exercises: List of completed exercises. Each exercise must have:
                            - exercise_name: exercise name
                            - sets_completed: number of sets
                            - reps_per_set: array of reps [12, 10, 8]
                            - weight_per_set: array of weights in kg [0, 0, 0] (use 0 for bodyweight)
                            - notes: execution notes
        duration_minutes: Workout duration in minutes
        feedback: Overall user feedback after workout

    Returns:
        Success or error message
    """
    if not _storage:
        return "ERROR: Storage not initialized"

    try:
        logger.info(f"Saving workout log to Google Sheets for {_user_email}")

        # Get current date
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Append each exercise to sheet
        for exercise in completed_exercises:
            _storage.append_workout_to_sheet(
                date=date_str,
                exercise_name=exercise.get("exercise_name", ""),
                sets=exercise.get("sets_completed", 0),
                reps=exercise.get("reps_per_set", []),
                weights=exercise.get("weight_per_set", []),
                duration_minutes=duration_minutes,
                notes=exercise.get("notes", ""),
                feedback=feedback or "",
            )

        # Also save JSON backup
        log_data = {
            "completed_exercises": completed_exercises,
            "duration_minutes": duration_minutes,
            "feedback": feedback or "",
        }
        workout_log = create_workout_log_from_dict(_user_email, log_data)
        log_dict = workout_log.model_dump(mode="json")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"log_{timestamp}.json"
        _storage.save_json(log_filename, log_dict, subfolder="workout_logs")

        logger.info("Workout log saved successfully to Google Sheets")
        sheet_url = _storage.get_workout_log_sheet_url()
        return f"✅ Workout log saved! Completed {len(completed_exercises)} exercises in {duration_minutes} minutes.\n\n📊 View spreadsheet: {sheet_url}"

    except Exception as e:
        error_msg = f"❌ Error saving workout log: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool
def update_memory(
    old_text: Optional[str] = None,
    new_text: str = "",
    mode: str = "replace",
) -> str:
    """Update trainer memory (free-form text document).

    Use this tool to record any important information about the user:
    - Personal preferences and settings
    - Progress observations
    - Specific exercise preferences
    - Any other notes that will help you serve the user better

    Modes:
    - "replace": Replace old_text with new_text (like str.replace)
    - "append": Add new_text to the end of document
    - "overwrite": Completely rewrite entire document with new_text

    Args:
        old_text: Text to replace (required only for mode="replace")
        new_text: New text to insert/replace
        mode: Edit mode ("replace", "append", "overwrite")

    Returns:
        Success or error message
    """
    if not _storage:
        return "ERROR: Storage not initialized"

    try:
        logger.info(f"Updating trainer memory for {_user_email}, mode={mode}")

        # Load current memory
        current_memory = _storage.load_memory()

        if mode == "replace":
            if not old_text:
                return "❌ Error: 'replace' mode requires old_text parameter"
            if old_text not in current_memory:
                return f"❌ Error: text '{old_text[:50]}...' not found in memory"
            updated_memory = current_memory.replace(old_text, new_text)

        elif mode == "append":
            if current_memory:
                updated_memory = current_memory + "\n\n" + new_text
            else:
                updated_memory = new_text

        elif mode == "overwrite":
            updated_memory = new_text

        else:
            return f"❌ Error: unknown mode '{mode}'. Use: replace, append, overwrite"

        # Save updated memory
        _storage.save_memory(updated_memory)
        logger.info("Trainer memory updated successfully")

        return f"✅ Trainer memory updated (mode: {mode})!"

    except Exception as e:
        error_msg = f"❌ Error updating memory: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool
def get_workout_logs(limit: int = 10) -> str:
    """Load user's workout logs from Google Sheets.

    Args:
        limit: Maximum number of logs to display (default 10)

    Returns:
        Latest workout log entries and link to spreadsheet
    """
    if not _storage:
        return "ERROR: Storage not initialized"

    try:
        logger.info(f"Loading workout logs from Google Sheets for {_user_email}, limit={limit}")

        # Get sheet URL
        sheet_url = _storage.get_workout_log_sheet_url()

        # Read logs from sheet
        logs = _storage.read_workout_logs_from_sheet(limit=limit)

        if not logs:
            return f"No workout logs yet. Start your first workout!\n\n📊 Spreadsheet link: {sheet_url}"

        logger.info(f"Loaded {len(logs)} workout logs from sheet")

        # Format logs summary
        output = f"**Last {len(logs)} workouts:**\n\n"

        # Group by date
        current_date = None
        for log in logs:
            log_date = log.get("date", "")

            # Show date header if it's a new date
            if log_date != current_date:
                output += f"\n📅 **{log_date}**\n"
                current_date = log_date

            # Show exercise details
            exercise_name = log.get("exercise_name", "")
            sets = log.get("sets", "")
            reps = log.get("reps", "")
            weights = log.get("weights", "")
            notes = log.get("notes", "")

            output += f"  • {exercise_name}: {sets} sets ({reps})"
            if weights and weights != "0, 0, 0":
                output += f", weight: {weights} kg"
            if notes:
                output += f"\n    💬 {notes}"
            output += "\n"

        output += f"\n📊 **Full workout log:** {sheet_url}"

        return output

    except Exception as e:
        error_msg = f"❌ Error loading workout logs: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


def build_user_context() -> str:
    """Build comprehensive user context for system prompt.

    Collects and formats:
    - User profile (goals, fitness level, schedule, health conditions, equipment)
    - Current workout plan (if exists)
    - Last 3 workout sessions summary
    - Trainer memory (free-form notes)
    - Onboarding instructions if profile/plan missing

    Returns:
        Formatted context string for system prompt
    """
    if not _storage:
        return ""

    context_parts = []
    has_profile = False
    has_plan = False

    # 1. User Profile
    try:
        profile_data = _storage.load_json("profile.json")
        if profile_data:
            has_profile = True
            context_parts.append("=== USER PROFILE ===")
            context_parts.append(f"Email: {_user_email}")
            context_parts.append(f"Fitness level: {profile_data.get('fitness_level', 'N/A')}")
            context_parts.append(f"Goals: {', '.join(profile_data.get('goals', []))}")

            schedule = profile_data.get('schedule', {})
            if schedule:
                context_parts.append("Training schedule:")
                for day, time in schedule.items():
                    context_parts.append(f"  - {day}: {time}")

            health = profile_data.get('health_conditions', [])
            if health:
                context_parts.append(f"⚠️ Health limitations: {', '.join(health)}")

            equipment = profile_data.get('equipment_available', [])
            if equipment:
                context_parts.append(f"Available equipment: {', '.join(equipment)}")

            notes = profile_data.get('additional_notes', '')
            if notes:
                context_parts.append(f"Additional notes: {notes}")

            context_parts.append("")
    except Exception as e:
        logger.warning(f"Failed to load profile for context: {e}")

    # 2. Current Workout Plan
    try:
        plan_data = _storage.load_json("current_plan.json")
        if plan_data:
            has_plan = True
            context_parts.append("=== CURRENT WORKOUT PLAN ===")
            context_parts.append(f"Duration: {plan_data.get('weeks', 'N/A')} weeks")
            context_parts.append(f"Workouts per week: {plan_data.get('days_per_week', 'N/A')}")
            context_parts.append(f"Status: {plan_data.get('status', 'N/A')}")

            notes = plan_data.get('notes', '')
            if notes:
                context_parts.append(f"Plan notes: {notes}")

            # Count total workouts
            plan = plan_data.get('plan', {})
            total_workouts = sum(len(days) for days in plan.values())
            context_parts.append(f"Total workouts in plan: {total_workouts}")
            context_parts.append("")
    except Exception as e:
        logger.warning(f"Failed to load plan for context: {e}")

    # 3. Last 3 Workout Sessions
    try:
        logs = _storage.read_workout_logs_from_sheet(limit=50)  # Get more to group by date
        if logs:
            context_parts.append("=== LAST 3 WORKOUTS ===")

            # Group by date and take last 3 unique dates
            workouts_by_date = {}
            for log in logs:
                date = log.get('date', '')
                if date not in workouts_by_date:
                    workouts_by_date[date] = []
                workouts_by_date[date].append(log)

            # Take last 3 workout sessions
            recent_workouts = list(workouts_by_date.items())[:3]

            for date, exercises in recent_workouts:
                context_parts.append(f"\n📅 {date}:")
                for ex in exercises:
                    ex_name = ex.get('exercise_name', '')
                    sets = ex.get('sets', '')
                    reps = ex.get('reps', '')
                    weights = ex.get('weights', '')
                    notes = ex.get('notes', '')

                    line = f"  • {ex_name}: {sets} sets ({reps})"
                    if weights and weights != "0, 0, 0":
                        line += f", weight: {weights} kg"
                    context_parts.append(line)

                    if notes:
                        context_parts.append(f"    💬 {notes}")

                # Add feedback if present (same for all exercises in session)
                if exercises and exercises[0].get('feedback'):
                    context_parts.append(f"  Feedback: {exercises[0]['feedback']}")

            context_parts.append("")
    except Exception as e:
        logger.warning(f"Failed to load workout logs for context: {e}")

    # 4. Trainer Memory
    try:
        memory = _storage.load_memory()
        if memory:
            context_parts.append("=== TRAINER MEMORY ===")
            context_parts.append(memory)
            context_parts.append("")
    except Exception as e:
        logger.warning(f"Failed to load memory for context: {e}")

    # 5. Onboarding Instructions (if profile or plan missing)
    if not has_profile or not has_plan:
        context_parts.append("=== ⚠️ IMPORTANT ONBOARDING INSTRUCTIONS ===")

        if not has_profile:
            context_parts.append("""
📋 USER PROFILE NOT CREATED

Your first task is to conduct an onboarding interview to create a profile:

1. Greet and introduce yourself as a personal trainer
2. Ask questions ONE AT A TIME (not a list), in a friendly tone
3. Collect the following information:
   - Fitness goals (lose weight/build muscle/endurance/strength)
   - Current fitness level (beginner/intermediate/advanced)
   - Schedule (which days and times available for training)
   - Health status (injuries, illnesses, limitations) - VERY IMPORTANT!
   - Available equipment (bodyweight only/dumbbells/barbell/full gym)
   - Preferences (likes/dislikes)

4. After collecting ALL information:
   - Summarize what you learned
   - Give user opportunity to correct
   - Call tool save_user_profile() with all data

IMPORTANT: Don't proceed to creating plan until you save and confirm the profile!
""")

        if not has_plan:
            if has_profile:
                context_parts.append("""
📋 WORKOUT PLAN NOT CREATED

User profile exists, now need to create a plan:

1. Say that you will now create a personalized plan based on profile
2. Consider ALL health limitations and injuries!
3. Ask how many weeks user wants plan for (recommend 4-8 weeks for beginners)
4. Create plan with gradual progression:
   - First 1-2 weeks: adaptation, moderate loads
   - Following weeks: gradual intensity increase
   - Always include warm-up (5-10 min) and cool-down (5-10 min)
5. Show plan to user in readable format
6. Ask if everything is acceptable
7. After confirmation - call save_workout_plan()

IMPORTANT: Plan must be SAFE and match fitness level!
""")

        context_parts.append("")

    return "\n".join(context_parts)


def get_all_tools() -> List:
    """Get all tool functions for LangChain."""
    return [
        save_user_profile,
        save_workout_plan,
        save_workout_log,
        update_memory,
        get_workout_logs,
    ]

