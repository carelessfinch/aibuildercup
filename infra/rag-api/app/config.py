"""All settings come from environment variables, so Cloud Run can change them without a rebuild."""

import os
from dataclasses import dataclass, field


def _list(name: str, default: str = "") -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    # Gemini model used by every agent. Change it here (or in Cloud Run's env vars) when a newer Flash ships.
    gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

    # Where the private litrag index lives: a gs:// prefix (copied to local disk at startup) or a local folder.
    index_uri: str = os.environ.get("LITRAG_INDEX_URI", "")
    local_index_dir: str = os.environ.get("LITRAG_LOCAL_INDEX_DIR", "/tmp/litrag-index")

    # Comma-separated browser origins allowed to call the API (the frontend). "*" allows any.
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "*"))

    # Demo login secrets and the research-api-only service key (normally injected from Secret Manager).
    auth_secret: str = os.environ.get("AUTH_SECRET", "")
    service_key: str = os.environ.get("SERVICE_KEY", "")
    demo_users: str = os.environ.get("DEMO_USERS", "")

    # Login attempts are deliberately separate from chat/search budgets.
    login_per_minute_per_ip: int = int(os.environ.get("LOGIN_PER_MINUTE_PER_IP", "5"))

    # Spending brakes for the open demo link (decision I2).
    chat_per_minute_per_ip: int = int(os.environ.get("CHAT_PER_MINUTE_PER_IP", "10"))
    chat_per_day_total: int = int(os.environ.get("CHAT_PER_DAY_TOTAL", "2000"))
    search_per_minute_per_ip: int = int(os.environ.get("SEARCH_PER_MINUTE_PER_IP", "60"))
    max_message_chars: int = int(os.environ.get("MAX_MESSAGE_CHARS", "4000"))

    @classmethod
    def from_env(cls) -> "Settings":
        """Read environment values when the application is created, not when this module imports."""
        return cls(
            gemini_model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
            index_uri=os.environ.get("LITRAG_INDEX_URI", ""),
            local_index_dir=os.environ.get("LITRAG_LOCAL_INDEX_DIR", "/tmp/litrag-index"),
            cors_origins=_list("CORS_ORIGINS", "*"),
            auth_secret=os.environ.get("AUTH_SECRET", ""),
            service_key=os.environ.get("SERVICE_KEY", ""),
            demo_users=os.environ.get("DEMO_USERS", ""),
            login_per_minute_per_ip=int(os.environ.get("LOGIN_PER_MINUTE_PER_IP", "5")),
            chat_per_minute_per_ip=int(os.environ.get("CHAT_PER_MINUTE_PER_IP", "10")),
            chat_per_day_total=int(os.environ.get("CHAT_PER_DAY_TOTAL", "2000")),
            search_per_minute_per_ip=int(os.environ.get("SEARCH_PER_MINUTE_PER_IP", "60")),
            max_message_chars=int(os.environ.get("MAX_MESSAGE_CHARS", "4000")),
        )


settings = Settings.from_env()
