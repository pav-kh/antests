import pytest
from app.auth import service
from app.auth.schemas import RegisterRequest
from app.db.models import User
from sqlalchemy import select


@pytest.mark.asyncio
async def test_register_creates_user_with_correct_code(db_session):
    req = RegisterRequest(login="alice", password="pw12345", access_code="TEST-CODE")
    user = await service.register_user(db_session, req, expected_code="TEST-CODE")
    assert user.login == "alice"
    rows = (await db_session.execute(select(User))).scalars().all()
    assert len(rows) == 1
    assert rows[0].password_hash != "pw12345"


@pytest.mark.asyncio
async def test_register_rejects_wrong_access_code(db_session):
    req = RegisterRequest(login="bob", password="pw12345", access_code="WRONG")
    with pytest.raises(service.InvalidAccessCode):
        await service.register_user(db_session, req, expected_code="TEST-CODE")


@pytest.mark.asyncio
async def test_register_rejects_duplicate_login(db_session):
    req = RegisterRequest(login="carol", password="pw12345", access_code="TEST-CODE")
    await service.register_user(db_session, req, expected_code="TEST-CODE")
    with pytest.raises(service.LoginTaken):
        await service.register_user(db_session, req, expected_code="TEST-CODE")


@pytest.mark.asyncio
async def test_register_endpoint_success(client):
    resp = await client.post(
        "/auth/register",
        json={"login": "erin", "password": "pw12345", "access_code": "TEST-CODE"},
    )
    assert resp.status_code == 201
    assert resp.json()["login"] == "erin"
    assert "session" in resp.cookies


@pytest.mark.asyncio
async def test_register_endpoint_wrong_code(client):
    resp = await client.post(
        "/auth/register",
        json={"login": "frank", "password": "pw12345", "access_code": "NOPE"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_endpoint_duplicate(client):
    body = {"login": "grace", "password": "pw12345", "access_code": "TEST-CODE"}
    await client.post("/auth/register", json=body)
    resp = await client.post("/auth/register", json=body)
    assert resp.status_code == 409
