import pytest


async def _register(client, login="uo"):
    return await client.post(
        "/auth/register",
        json={"login": login, "password": "pw12345", "access_code": "TEST-CODE"},
    )


@pytest.mark.asyncio
async def test_overview_empty_for_new_user(client):
    await _register(client, "newbie")
    resp = await client.get("/me/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions"] == []
    assert body["competency"] == []


@pytest.mark.asyncio
async def test_overview_requires_auth(client):
    await client.post("/auth/logout")
    resp = await client.get("/me/overview")
    assert resp.status_code == 401
