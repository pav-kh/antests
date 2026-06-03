from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str = ""
    session_secret: str
    access_code: str
    daily_session_limit: int = 10


def get_settings() -> Settings:
    return Settings()
