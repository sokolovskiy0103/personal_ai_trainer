"""Personal AI Trainer - Streamlit App."""

import logging
import os

import streamlit as st

if hasattr(st, "secrets") and "LANGSMITH_API_KEY" in st.secrets:
    os.environ["LANGSMITH_TRACING"] = st.secrets.get("LANGSMITH_TRACING", "true")
    os.environ["LANGSMITH_ENDPOINT"] = st.secrets.get(
        "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"
    )
    os.environ["LANGSMITH_API_KEY"] = st.secrets["LANGSMITH_API_KEY"]
    os.environ["LANGSMITH_PROJECT"] = st.secrets.get("LANGSMITH_PROJECT", "personal_ai_trainer")
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = st.secrets["LANGSMITH_API_KEY"]
    os.environ["LANGCHAIN_PROJECT"] = st.secrets.get("LANGSMITH_PROJECT", "personal_ai_trainer")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
from src.memory.gdrive_memory import GoogleDriveStorage  # noqa: E402
from src.models.user_profile import UserProfile  # noqa: E402
from src.models.workout_plan import WorkoutPlan  # noqa: E402
from src.utils.anthropic_langchain_client import AnthropicLangChainClient  # noqa: E402
from src.utils.google_auth import (  # noqa: E402
    credentials_from_dict,
    credentials_to_dict,
    exchange_code_for_token,
    get_authorization_url,
    get_user_info,
    refresh_credentials,
    revoke_credentials,
)
from src.utils.prompts import SYSTEM_PROMPT  # noqa: E402
from src.utils.secure_storage import get_secure_storage  # noqa: E402
from src.utils.tool_handlers import build_user_context, set_storage_context  # noqa: E402

# Page config
st.set_page_config(
    page_title="Personal AI Trainer",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def initialize_session_state() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = None
    if "credentials" not in st.session_state:
        st.session_state.credentials = None
    if "cookie_save_pending" not in st.session_state:
        st.session_state.cookie_save_pending = False
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
    try:
        if st.secrets.get("redirect_uri"):
            return st.secrets["redirect_uri"]
    except Exception:
        pass
    return "http://localhost:8501"


def get_client_config() -> dict:
    return {
        "web": {
            "client_id": st.secrets["google_oauth"]["client_id"],
            "client_secret": st.secrets["google_oauth"]["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def check_user_access(email: str) -> bool:
    allowed_emails = []
    try:
        if "allowed_emails" in st.secrets:
            allowed_emails = st.secrets["allowed_emails"]
        elif hasattr(st.secrets, "allowed_emails"):
            allowed_emails = st.secrets.allowed_emails

        if isinstance(allowed_emails, str):
            allowed_emails = [allowed_emails]
        elif not isinstance(allowed_emails, (list, tuple)):
            allowed_emails = list(allowed_emails) if allowed_emails else []
    except Exception as e:
        logger.warning(f"Error reading allowed_emails: {e}")
        allowed_emails = []

    if not allowed_emails:
        logger.warning("No allowed_emails configured - denying access")
        return False

    is_allowed = email in allowed_emails
    logger.info(f"Access check for {email}: {'ALLOWED' if is_allowed else 'DENIED'}")
    return is_allowed


def restore_session_from_cookie() -> bool:
    if st.session_state.authenticated:
        return True

    storage = get_secure_storage()
    if not storage.is_ready():
        return False

    saved_credentials = storage.load_credentials()
    if not saved_credentials:
        return False

    try:
        creds = credentials_from_dict(saved_credentials)
        creds = refresh_credentials(creds)
        user_info = get_user_info(creds)
        user_email = user_info.get("email")

        if not check_user_access(user_email):
            logger.warning(f"Access denied: {user_email}")
            storage.clear_credentials()
            return False

        st.session_state.authenticated = True
        st.session_state.credentials = credentials_to_dict(creds)
        st.session_state.user_info = user_info
        logger.info(f"Session restored for {user_email}")
        return True
    except Exception as e:
        logger.warning(f"Failed to restore session: {e}")
        storage.clear_credentials()
        return False


def handle_oauth_callback() -> None:
    query_params = st.query_params
    if "code" not in query_params:
        return

    if st.session_state.authenticated:
        st.query_params.clear()
        return

    code = query_params["code"]
    try:
        client_config = get_client_config()
        redirect_uri = get_redirect_uri()
        credentials = exchange_code_for_token(code, client_config, redirect_uri)
        st.query_params.clear()

        user_info = get_user_info(credentials)
        user_email = user_info.get("email")

        if not check_user_access(user_email):
            logger.warning(f"Access denied: {user_email}")
            st.error(
                "🚫 Доступ заборонено. Цей додаток доступний тільки для авторизованих користувачів."
            )
            st.stop()

        st.session_state.credentials = credentials_to_dict(credentials)
        st.session_state.user_info = user_info
        st.session_state.authenticated = True
        st.session_state.cookie_save_pending = True
        st.rerun()
    except Exception as e:
        logger.error(f"OAuth error: {str(e)}", exc_info=True)
        st.query_params.clear()
        st.error(f"Помилка авторизації: {str(e)}")


def load_user_data() -> None:
    if not st.session_state.drive_storage or st.session_state.data_loaded:
        return

    storage: GoogleDriveStorage = st.session_state.drive_storage
    try:
        profile_data = storage.load_json("profile.json")
        if profile_data:
            st.session_state.user_profile = UserProfile(**profile_data)

        plan_data = storage.load_json("current_plan.json")
        if plan_data:
            st.session_state.current_plan = WorkoutPlan(**plan_data)

        st.session_state.data_loaded = True
    except Exception as e:
        logger.warning(f"Failed to load user data: {e}")
        st.warning(f"Не вдалося завантажити дані: {str(e)}")


def initialize_services() -> None:
    if not st.session_state.credentials:
        return

    creds = credentials_from_dict(st.session_state.credentials)
    creds = refresh_credentials(creds)
    st.session_state.credentials = credentials_to_dict(creds)

    if not st.session_state.drive_storage:
        st.session_state.drive_storage = GoogleDriveStorage(creds)
        load_user_data()

    if not st.session_state.gemini_client:
        anthropic_api_key = st.secrets.get("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            st.error("ANTHROPIC_API_KEY not found in secrets.toml")
            st.stop()

        st.session_state.gemini_client = AnthropicLangChainClient(
            api_key=anthropic_api_key,
            system_instruction=SYSTEM_PROMPT,
            model_name="claude-haiku-4-5-20251001",
            temperature=0.7,
        )

        user_context = build_user_context()
        if user_context:
            st.session_state.gemini_client.update_system_instruction(user_context)

    if st.session_state.drive_storage and st.session_state.user_info:
        set_storage_context(
            st.session_state.drive_storage,
            st.session_state.user_info.get("email"),
        )


def logout() -> None:
    storage = get_secure_storage()
    storage.clear_credentials()

    try:
        if st.session_state.credentials:
            creds = credentials_from_dict(st.session_state.credentials)
            revoke_credentials(creds)
    except Exception as e:
        logger.warning(f"Failed to revoke credentials: {e}")

    for key in list(st.session_state.keys()):
        del st.session_state[key]

    st.rerun()


def login_page() -> None:
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
            st.markdown(
                f'<meta http-equiv="refresh" content="0;url={auth_url}">', unsafe_allow_html=True
            )

    st.markdown("---")
    st.info(
        "ℹ️ Твої дані будуть зберігатися на твоєму Google Drive. Ніхто крім тебе не матиме до них доступу."
    )


def main_app() -> None:
    initialize_services()

    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🏋️ Personal AI Trainer")
    with col2:
        if st.button("Вийти", use_container_width=True):
            logout()
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
            st.session_state.chat_history.append(
                {"role": "user", "content": "Хочу почати тренування"}
            )
            st.rerun()

        if st.button("📊 Переглянути прогрес", use_container_width=True):
            st.session_state.chat_history.append({"role": "user", "content": "Покажи мій прогрес"})
            st.rerun()

        if st.button("✏️ Змінити план", use_container_width=True):
            st.session_state.chat_history.append(
                {"role": "user", "content": "Хочу змінити план тренувань"}
            )
            st.rerun()

        st.markdown("---")
        st.markdown("### ℹ️ Інформація")
        st.info("Дані зберігаються на твоєму Google Drive у папці 'PersonalAITrainer'")

    st.markdown("### 💬 Чат з тренером")

    chat_container = st.container()
    with chat_container:
        for message in st.session_state.chat_history:
            role = message["role"]
            content = message["content"]
            if role == "user":
                st.chat_message("user").write(content)
            else:
                st.chat_message("assistant").write(content)

    pending_message = None
    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
        pending_message = st.session_state.chat_history[-1]["content"]

    user_input = st.chat_input("Напиши повідомлення...")

    if user_input or pending_message:
        message_to_process = pending_message if pending_message else user_input

        if not pending_message:
            st.session_state.chat_history.append({"role": "user", "content": user_input})
            st.chat_message("user").write(user_input)

        gemini_client = st.session_state.gemini_client
        if not gemini_client.chat_history:
            gemini_client.start_chat(history=st.session_state.chat_history[:-1])

        try:
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = ""

                for chunk in gemini_client.send_message_stream(message_to_process):
                    full_response += chunk
                    message_placeholder.markdown(full_response + "▌")

                message_placeholder.markdown(full_response)

            st.session_state.chat_history.append({"role": "assistant", "content": full_response})
        except Exception as e:
            st.error(f"Помилка: {str(e)}")


def main() -> None:
    initialize_session_state()
    handle_oauth_callback()

    if st.session_state.authenticated:
        storage = get_secure_storage()
        if st.session_state.cookie_save_pending and storage.is_ready():
            if storage.save_credentials(st.session_state.credentials):
                st.session_state.cookie_save_pending = False
        main_app()
        return

    storage = get_secure_storage()
    if not storage.is_ready():
        st.info("Завантаження...")
        import time

        time.sleep(0.5)
        st.rerun()
        return

    if restore_session_from_cookie():
        st.rerun()
        return

    login_page()


if __name__ == "__main__":
    main()
