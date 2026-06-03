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
