"""Personal AI Trainer - Streamlit App."""

import logging
import streamlit as st
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from src.memory.gdrive_memory import GoogleDriveStorage
from src.models.user_profile import UserProfile
from src.models.workout_plan import WorkoutPlan
from src.utils.gemini_langchain_client import GeminiLangChainClient
from src.utils.tool_handlers import set_storage_context
from src.utils.prompts import SYSTEM_PROMPT
from src.utils.google_auth import (
    get_authorization_url,
    exchange_code_for_token,
    credentials_to_dict,
    credentials_from_dict,
    refresh_credentials,
    get_user_info,
    revoke_credentials,
)
from src.utils.secure_storage import get_secure_storage

# Page config
st.set_page_config(
    page_title="Personal AI Trainer",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def initialize_session_state() -> None:
    """Initialize all session state variables."""
    # Authentication state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = None
    if "credentials" not in st.session_state:
        st.session_state.credentials = None
    if "cookie_save_pending" not in st.session_state:
        st.session_state.cookie_save_pending = False

    # Application state
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "gemini_client" not in st.session_state:
        st.session_state.gemini_client = None
    if "drive_storage" not in st.session_state:
        st.session_state.drive_storage = None
    if "user_profile" not in st.session_state:
        st.session_state.user_profile = None
    if "current_plan" not in st.session_state:
        st.session_state.current_plan = None
    if "data_loaded" not in st.session_state:
        st.session_state.data_loaded = False


def get_redirect_uri() -> str:
    """Get OAuth redirect URI based on environment."""
    # For Streamlit Community Cloud
    try:
        if st.secrets.get("redirect_uri"):
            return st.secrets["redirect_uri"]
    except Exception:
        pass

    # Default for local development
    return "http://localhost:8501"


def get_client_config() -> dict:
    """Get Google OAuth client configuration from secrets."""
    return {
        "web": {
            "client_id": st.secrets["google_oauth"]["client_id"],
            "client_secret": st.secrets["google_oauth"]["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def restore_session_from_cookie() -> bool:
    """
    Try to restore authentication from cookie.

    Returns:
        True if session was restored, False otherwise
    """
    if st.session_state.authenticated:
        return True

    storage = get_secure_storage()

    # Wait for cookie manager to be ready
    if not storage.is_ready():
        return False

    # Try to load credentials
    saved_credentials = storage.load_credentials()
    if not saved_credentials:
        return False

    try:
        # Validate and refresh credentials
        creds = credentials_from_dict(saved_credentials)
        creds = refresh_credentials(creds)

        # Get user info
        user_info = get_user_info(creds)

        # Restore session
        st.session_state.authenticated = True
        st.session_state.credentials = credentials_to_dict(creds)
        st.session_state.user_info = user_info

        logger.info(f"Restored session from cookie for {user_info.get('email')}")
        return True

    except Exception as e:
        logger.warning(f"Failed to restore session from cookie: {e}")
        # Clear invalid cookie
        storage.clear_credentials()
        return False


def handle_oauth_callback() -> None:
    """Handle OAuth callback with authorization code."""
    # Check for OAuth code in query params
    query_params = st.query_params
    if "code" not in query_params:
        return

    # Skip if already authenticated
    if st.session_state.authenticated:
        st.query_params.clear()
        return

    code = query_params["code"]
    logger.info(f"OAuth callback received with code: {code[:20]}...")

    try:
        client_config = get_client_config()
        redirect_uri = get_redirect_uri()

        # Exchange code for credentials
        credentials = exchange_code_for_token(code, client_config, redirect_uri)
        logger.info("Successfully exchanged code for credentials")

        # Clear query params immediately
        st.query_params.clear()

        # Get user info
        user_info = get_user_info(credentials)
        logger.info(f"Got user info for: {user_info.get('email')}")

        # Store credentials and user info in session state
        st.session_state.credentials = credentials_to_dict(credentials)
        st.session_state.user_info = user_info
        st.session_state.authenticated = True

        # Mark that we need to save to cookie
        st.session_state.cookie_save_pending = True

        # Rerun to show authenticated app
        st.rerun()

    except Exception as e:
        logger.error(f"OAuth error: {str(e)}", exc_info=True)
        st.query_params.clear()
        st.error(f"Помилка авторизації: {str(e)}")


def load_user_data() -> None:
    """Load user data from Google Drive."""
    if not st.session_state.drive_storage or st.session_state.data_loaded:
        return

    storage: GoogleDriveStorage = st.session_state.drive_storage

    try:
        # Load user profile
        profile_data = storage.load_json("profile.json")
        if profile_data:
            st.session_state.user_profile = UserProfile(**profile_data)

        # Load current workout plan
        plan_data = storage.load_json("current_plan.json")
        if plan_data:
            st.session_state.current_plan = WorkoutPlan(**plan_data)

        # Load chat history
        chat_data = storage.load_json("chat_history.json")
        if chat_data:
            st.session_state.chat_history = chat_data.get("messages", [])

        st.session_state.data_loaded = True
        logger.info("User data loaded successfully")

    except Exception as e:
        logger.warning(f"Failed to load user data: {e}")
        st.warning(f"Не вдалося завантажити дані: {str(e)}")


def save_chat_history() -> None:
    """Save chat history to Google Drive."""
    if not st.session_state.drive_storage:
        return

    storage: GoogleDriveStorage = st.session_state.drive_storage

    try:
        storage.save_json("chat_history.json", {
            "messages": st.session_state.chat_history,
            "last_updated": datetime.now().isoformat()
        })
    except Exception as e:
        # Fail silently for chat history to not interrupt user flow
        logger.warning(f"Failed to save chat history: {e}")


def initialize_services() -> None:
    """Initialize Google Drive storage and Gemini client."""
    if not st.session_state.credentials:
        return

    # Refresh credentials if needed
    creds = credentials_from_dict(st.session_state.credentials)
    creds = refresh_credentials(creds)
    st.session_state.credentials = credentials_to_dict(creds)

    # Initialize storage
    if not st.session_state.drive_storage:
        st.session_state.drive_storage = GoogleDriveStorage(creds)
        load_user_data()

    # Initialize Gemini client
    if not st.session_state.gemini_client:
        gemini_api_key = st.secrets["GEMINI_API_KEY"]
        st.session_state.gemini_client = GeminiLangChainClient(
            api_key=gemini_api_key,
            system_instruction=SYSTEM_PROMPT,
        )

    # Set storage context for tools
    if st.session_state.drive_storage and st.session_state.user_info:
        set_storage_context(
            st.session_state.drive_storage,
            st.session_state.user_info.get("email"),
        )


def logout() -> None:
    """Clear authentication and session state."""
    # Clear cookie
    storage = get_secure_storage()
    storage.clear_credentials()

    # Revoke credentials if possible
    try:
        if st.session_state.credentials:
            creds = credentials_from_dict(st.session_state.credentials)
            revoke_credentials(creds)
    except Exception as e:
        logger.warning(f"Failed to revoke credentials: {e}")

    # Clear all session state
    for key in list(st.session_state.keys()):
        del st.session_state[key]

    logger.info("User logged out")
    st.rerun()


def login_page() -> None:
    """Display login page."""
    st.title("🏋️ Personal AI Trainer")
    st.markdown("### Твій персональний AI тренер")

    st.markdown("""
    Вітаю! Я допоможу тобі:
    - Створити персональний план тренувань
    - Відстежувати прогрес
    - Коригувати програму на основі твоїх результатів
    - Мотивувати та підтримувати на шляху до мети

    Для початку увійди через Google аккаунт.
    """)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        if st.button("🔐 Увійти через Google", type="primary", use_container_width=True):
            client_config = get_client_config()
            redirect_uri = get_redirect_uri()
            auth_url = get_authorization_url(client_config, redirect_uri)

            # Redirect to Google OAuth
            st.markdown(
                f'<meta http-equiv="refresh" content="0;url={auth_url}">',
                unsafe_allow_html=True
            )

    st.markdown("---")
    st.info("ℹ️ Твої дані будуть зберігатися на твоєму Google Drive. Ніхто крім тебе не матиме до них доступу.")


def main_app() -> None:
    """Main application UI."""
    # Initialize services
    initialize_services()

    # Header
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🏋️ Personal AI Trainer")
    with col2:
        if st.button("Вийти", use_container_width=True):
            logout()

    # Sidebar
    with st.sidebar:
        user_info = st.session_state.user_info
        if user_info:
            st.image(user_info.get("picture", ""), width=80)
            st.write(f"**{user_info.get('name')}**")
            st.write(user_info.get("email"))

        st.markdown("---")

        # Show user profile info if exists
        if st.session_state.user_profile:
            profile: UserProfile = st.session_state.user_profile
            with st.expander("👤 Мій профіль"):
                st.write(f"**Рівень:** {profile.fitness_level}")
                st.write(f"**Цілі:** {', '.join(profile.goals)}")
                if profile.equipment_available:
                    st.write(f"**Обладнання:** {', '.join(profile.equipment_available)}")

        # Show current plan if exists
        if st.session_state.current_plan:
            plan: WorkoutPlan = st.session_state.current_plan
            with st.expander("📋 Поточний план"):
                st.write(f"**Тривалість:** {plan.weeks} тижнів")
                st.write(f"**Тренувань на тиждень:** {plan.days_per_week}")
                st.write(f"**Статус:** {plan.status}")

        st.markdown("---")

        st.markdown("### 📋 Швидкі дії")
        if st.button("💪 Почати тренування", use_container_width=True):
            st.session_state.chat_history.append({
                "role": "user",
                "content": "Хочу почати тренування"
            })
            save_chat_history()
            st.rerun()

        if st.button("📊 Переглянути прогрес", use_container_width=True):
            st.session_state.chat_history.append({
                "role": "user",
                "content": "Покажи мій прогрес"
            })
            save_chat_history()
            st.rerun()

        if st.button("✏️ Змінити план", use_container_width=True):
            st.session_state.chat_history.append({
                "role": "user",
                "content": "Хочу змінити план тренувань"
            })
            save_chat_history()
            st.rerun()

        st.markdown("---")
        st.markdown("### ℹ️ Інформація")
        st.info("Дані зберігаються на твоєму Google Drive у папці 'PersonalAITrainer'")

    # Chat interface
    st.markdown("### 💬 Чат з тренером")

    # Display chat history
    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_history:
            role = message["role"]
            content = message["content"]

            if role == "user":
                st.chat_message("user").write(content)
            else:
                st.chat_message("assistant").write(content)

    # Check if there's a pending user message without AI response
    pending_message = None
    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
        pending_message = st.session_state.chat_history[-1]["content"]

    # Chat input
    user_input = st.chat_input("Напиши повідомлення...")

    # Process user input (either from chat input or pending from quick action)
    if user_input or pending_message:
        # Use pending message if exists, otherwise use new input
        message_to_process = pending_message if pending_message else user_input

        # Add user message to history (only if it's new input, not pending)
        if not pending_message:
            st.session_state.chat_history.append({
                "role": "user",
                "content": user_input
            })

        # Get AI response
        gemini_client = st.session_state.gemini_client

        # Initialize chat if needed
        if not gemini_client.chat_session:
            gemini_client.start_chat(history=st.session_state.chat_history[:-1])

        try:
            with st.spinner("Тренер думає..."):
                response = gemini_client.send_message(message_to_process)

            # Add AI response to history
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": response
            })

            # Save chat history to Drive
            save_chat_history()

            st.rerun()

        except Exception as e:
            st.error(f"Помилка: {str(e)}")


def main() -> None:
    """Main app entry point."""
    # Initialize session state
    initialize_session_state()

    # Handle OAuth callback first (highest priority)
    handle_oauth_callback()

    # If already authenticated from callback or session, show app
    if st.session_state.authenticated:
        # Try to save credentials to cookie if pending
        storage = get_secure_storage()
        if st.session_state.cookie_save_pending and storage.is_ready():
            if storage.save_credentials(st.session_state.credentials):
                st.session_state.cookie_save_pending = False
                logger.info("Saved credentials to cookie")

        main_app()
        return

    # Try to restore from cookie
    storage = get_secure_storage()
    if not storage.is_ready():
        # Wait for cookie manager to initialize
        st.info("Завантаження...")
        import time
        time.sleep(0.5)
        st.rerun()
        return

    # Try to restore session
    if restore_session_from_cookie():
        logger.info("Session restored, rerunning to show app")
        st.rerun()
        return

    # Not authenticated - show login page
    login_page()


if __name__ == "__main__":
    main()
