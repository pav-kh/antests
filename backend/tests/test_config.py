from app.core.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("SESSION_SECRET", "secret")
    monkeypatch.setenv("ACCESS_CODE", "LET-ME-IN")
    monkeypatch.setenv("DAILY_SESSION_LIMIT", "7")
    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert s.access_code == "LET-ME-IN"
    assert s.daily_session_limit == 7


def test_daily_limit_has_default(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("SESSION_SECRET", "secret")
    monkeypatch.setenv("ACCESS_CODE", "X")
    monkeypatch.delenv("DAILY_SESSION_LIMIT", raising=False)
    s = Settings()
    assert s.daily_session_limit == 10


def test_cookie_secure_defaults_false_for_local_dev(monkeypatch):
    # Default must be False so the session cookie still works over local HTTP.
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("SESSION_SECRET", "secret")
    monkeypatch.setenv("ACCESS_CODE", "X")
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    s = Settings()
    assert s.cookie_secure is False


def test_cookie_secure_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("SESSION_SECRET", "secret")
    monkeypatch.setenv("ACCESS_CODE", "X")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    s = Settings()
    assert s.cookie_secure is True


def test_database_url_normalized_to_asyncpg(monkeypatch):
    # Railway/Heroku-style URLs use postgres:// or postgresql://; our async stack
    # needs the +asyncpg driver. The setting must normalize them.
    monkeypatch.setenv("SESSION_SECRET", "secret")
    monkeypatch.setenv("ACCESS_CODE", "X")

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
    assert Settings().database_url == "postgresql+asyncpg://u:p@h:5432/d"

    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/d")
    assert Settings().database_url == "postgresql+asyncpg://u:p@h:5432/d"

    # already-correct URL is left untouched
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    assert Settings().database_url == "postgresql+asyncpg://u:p@h:5432/d"


def test_settings_has_openai_and_generation(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("SESSION_SECRET", "secret")
    monkeypatch.setenv("ACCESS_CODE", "X")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_GEN_MODEL", "strong-model")
    monkeypatch.setenv("OPENAI_VALIDATE_MODEL", "cheap-model")
    monkeypatch.setenv("GENERATION_BATCH_SIZE", "10")
    monkeypatch.setenv("ADAPTIVE_QUESTION_COUNT", "20")
    monkeypatch.setenv("WEAK_TOPIC_THRESHOLD", "0.6")
    from app.core.config import Settings
    s = Settings()
    assert s.openai_api_key == "sk-test"
    assert s.openai_gen_model == "strong-model"
    assert s.openai_validate_model == "cheap-model"
    assert s.generation_batch_size == 10
    assert s.adaptive_question_count == 20
    assert s.weak_topic_threshold == 0.6
