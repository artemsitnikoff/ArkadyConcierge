from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram
    bot_token: SecretStr

    # OpenRouter (voice transcription)
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = "google/gemini-2.5-pro"
    openrouter_timeout: float = 300.0

    # Reject voice messages longer than this to cap base64 payload size,
    # transcription cost, and event-loop blocking during b64 encode.
    max_voice_duration_sec: int = 600

    # Claude CLI (subscription auth via OAuth)
    claude_cli_path: str = "claude"
    claude_model: str = "claude-opus-4-7"
    claude_oauth_client_id: str = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    claude_code_oauth_token: str = ""
    claude_refresh_token: str = ""

    # Access control — comma-separated Telegram IDs. Empty = allow everyone.
    allowed_users: str = ""

    # HTTP API key for /api/concierge/breakdown. Empty = endpoint is disabled
    # (returns 503). Set to a strong random string in production.
    api_key: SecretStr = SecretStr("")

    # Logging
    log_level: str = "INFO"
    # "plain" = human-readable, "json" = one JSON object per line (for
    # aggregators like Loki / Elastic / Datadog).
    log_format: str = "plain"

    @property
    def allowed_user_ids(self) -> set[int]:
        if not self.allowed_users.strip():
            return set()
        return {
            int(x) for x in self.allowed_users.split(",")
            if x.strip().lstrip("-").isdigit()
        }

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
