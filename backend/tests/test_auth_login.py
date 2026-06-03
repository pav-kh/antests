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
