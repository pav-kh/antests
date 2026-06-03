import asyncio

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
async def test_register_concurrent_duplicate_raises_login_taken_not_500(db_session):
    # Two identical registrations racing from independent connections: both pass
    # the pre-check, one wins the insert, the loser must surface LoginTaken
    # (mapped to 409) instead of an unhandled IntegrityError (500).
    from tests.conftest import _Session

    async def register_once():
        async with _Session() as s:
            req = RegisterRequest(
                login="quinn", password="pw12345", access_code="TEST-CODE"
            )
            try:
                await service.register_user(s, req, expected_code="TEST-CODE")
                return "ok"
            except service.LoginTaken:
                return "login_taken"

    results = await asyncio.gather(*(register_once() for _ in range(2)))

    # Exactly one succeeds, exactly one is cleanly rejected as LoginTaken.
    assert sorted(results) == ["login_taken", "ok"]
    rows = (await db_session.execute(select(User))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_register_endpoint_concurrent_duplicate_returns_409(client):
    # End-to-end: a racing duplicate registration returns 409, never 500.
    from tests.conftest import _Session
    from app.db.base import get_session
    from app.main import create_app
    from httpx import ASGITransport, AsyncClient

    async def register_via_fresh_client():
        async with _Session() as s:
            app = create_app()

            async def _override():
                yield s

            app.dependency_overrides[get_session] = _override
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post(
                    "/auth/register",
                    json={
                        "login": "rachel",
                        "password": "pw12345",
                        "access_code": "TEST-CODE",
                    },
                )
            return resp.status_code

    codes = await asyncio.gather(*(register_via_fresh_client() for _ in range(2)))

    assert sorted(codes) == [201, 409]


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
