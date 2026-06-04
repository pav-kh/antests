from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str = ""
    session_secret: str
    access_code: str
    daily_session_limit: int = 10
    # Send the session cookie only over HTTPS. Defaults False so local HTTP
    # dev keeps working; set COOKIE_SECURE=true in production behind TLS.
    cookie_secure: bool = False
    # Browser origin of the frontend, for CORS. Must be an explicit origin (not
    # a wildcard) because requests are credentialed. Set FRONTEND_ORIGIN in prod.
    frontend_origin: str = "http://localhost:3000"
    openai_api_key: str = ""
    openai_gen_model: str = "gpt-4o"
    openai_validate_model: str = "gpt-4o-mini"
    # Small batches stream the first questions to the user within seconds and
    # keep the progress counter rising smoothly; large batches make generation
    # look frozen while a whole batch is produced. 3 balances responsiveness
    # against per-call prompt overhead.
    generation_batch_size: int = 3
    adaptive_question_count: int = 20
    weak_topic_threshold: float = 0.6


def get_settings() -> Settings:
    return Settings()
