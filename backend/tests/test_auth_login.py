import pytest


async def _register(client, login="heidi"):
    return await client.post(
        "/auth/register",
        json={"login": login, "password": "pw12345", "access_code": "TEST-CODE"},
    )


@pytest.mark.asyncio
async def test_login_success_and_me(client):
    await _register(client, "ivan")
    # logout first to clear the registration cookie
    await client.post("/auth/logout")
    resp = await client.post("/auth/login", json={"login": "ivan", "password": "pw12345"})
    assert resp.status_code == 200
    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["login"] == "ivan"


@pytest.mark.asyncio
async def test_session_cookie_not_secure_by_default(client):
    # Local HTTP dev: cookie must NOT carry the Secure attribute.
    resp = await _register(client, "nadia")
    set_cookie = resp.headers["set-cookie"]
    assert "session=" in set_cookie
    assert "secure" not in set_cookie.lower()


@pytest.mark.asyncio
async def test_session_cookie_secure_when_configured(client, monkeypatch):
    # Production-over-HTTPS: COOKIE_SECURE=true makes the cookie Secure.
    monkeypatch.setenv("COOKIE_SECURE", "true")
    resp = await _register(client, "oscar")
    set_cookie = resp.headers["set-cookie"]
    assert "secure" in set_cookie.lower()


@pytest.mark.asyncio
async def test_logout_cookie_clear_respects_secure_flag(client, monkeypatch):
    # The clearing cookie must match the Secure attribute or browsers ignore it.
    monkeypatch.setenv("COOKIE_SECURE", "true")
    resp = await client.post("/auth/logout")
    set_cookie = resp.headers["set-cookie"]
    assert "secure" in set_cookie.lower()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await _register(client, "judy")
    await client.post("/auth/logout")
    resp = await client.post("/auth/login", json={"login": "judy", "password": "WRONG"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    await client.post("/auth/logout")
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_non_uuid_session_payload_returns_401(client):
    # Forge a cookie that is correctly SIGNED but whose payload is not a UUID.
    from app.core.security import sign_session
    from app.core.config import get_settings
    token = sign_session("not-a-uuid", get_settings().session_secret)
    await client.post("/auth/logout")
    client.cookies.set("session", token)
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_session_and_me_returns_401(client):
    await _register(client, "mallory")
    # Authenticated right after register
    me_ok = await client.get("/auth/me")
    assert me_ok.status_code == 200
    await client.post("/auth/logout")
    me_after = await client.get("/auth/me")
    assert me_after.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_missing_user_still_runs_password_verify(db_session, monkeypatch):
    # Timing mitigation: when the login does not exist we must still perform an
    # argon2 verification (against a dummy hash) so the missing-user branch does
    # comparable work to the wrong-password branch and does not leak existence.
    from app.auth import service
    from app.auth.schemas import LoginRequest

    calls = []
    real_verify = service.verify_password

    def spy_verify(plain, hashed):
        calls.append(hashed)
        return real_verify(plain, hashed)

    monkeypatch.setattr(service, "verify_password", spy_verify)

    with pytest.raises(service.InvalidCredentials):
        await service.authenticate_user(
            db_session, LoginRequest(login="ghost", password="whatever")
        )

    # verify_password was invoked exactly once even though the user is absent.
    assert len(calls) == 1
    # ...and it verified against a real argon2 hash, not the empty string.
    assert calls[0].startswith("$argon2")
