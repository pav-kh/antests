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
