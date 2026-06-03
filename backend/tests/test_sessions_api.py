import asyncio
import pytest

from app.generation.schemas import GeneratedBatch, GeneratedQuestion, ValidationVerdict


def _q(topic_id="data"):
    return GeneratedQuestion(
        topic_id=topic_id, type="single", stem="Q?",
        artifact_kind="none", artifact_content=None,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        correct_keys=["a"], explanation="because",
    )


class FakeClient:
    async def generate_batch(self, level, mode, plan_slice):
        n = sum(c for _, c in plan_slice)
        return GeneratedBatch(questions=[_q(plan_slice[0][0]) for _ in range(n)])

    async def validate_question(self, q):
        return ValidationVerdict(valid=True, reason="ok")


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    from app.generation import router as gen_router
    monkeypatch.setattr(gen_router, "build_openai_client", lambda: FakeClient())


async def _register(client, login="kate"):
    return await client.post(
        "/auth/register",
        json={"login": login, "password": "pw12345", "access_code": "TEST-CODE"},
    )


@pytest.mark.asyncio
async def test_create_adaptive_session_generates_and_becomes_ready(client):
    await _register(client, "kate")
    resp = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
    assert resp.status_code == 201
    sid = resp.json()["id"]

    for _ in range(50):
        st = await client.get(f"/sessions/{sid}/status")
        body = st.json()
        if body["status"] == "ready":
            break
        await asyncio.sleep(0.05)
    assert body["status"] == "ready"
    assert body["generated_count"] == body["total_questions"]

    qs = await client.get(f"/sessions/{sid}/questions")
    items = qs.json()
    assert len(items) == body["total_questions"]
    assert "correct_keys" not in items[0]
    assert "explanation" not in items[0]
    assert {"id", "seq", "topic_id", "type", "stem", "options"} <= set(items[0].keys())


@pytest.mark.asyncio
async def test_create_session_requires_auth(client):
    await client.post("/auth/logout")
    resp = await client.post("/sessions", json={"level": "base", "mode": "exam"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_daily_limit_blocks_after_threshold(client):
    await _register(client, "leo")
    for _ in range(3):
        r = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
        assert r.status_code == 201
    blocked = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_failed_generation_refunds_daily_slot(client, monkeypatch):
    from app.db.base import engine
    from app.generation import router as gen_router

    # See note in the failed-status test: dispose the app's pooled engine so the
    # background task opens a SessionLocal() bound to this test's event loop.
    await engine.dispose()

    def _boom():
        raise RuntimeError("bad key")

    monkeypatch.setattr(gen_router, "build_openai_client", _boom)
    await _register(client, "vera")
    # start 5 sessions that all fail; each should refund, so we can keep going
    for _ in range(5):  # more than the limit of 3 — only works if refunds happen
        resp = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
        assert resp.status_code == 201
        sid = resp.json()["id"]
        for _ in range(50):
            st = await client.get(f"/sessions/{sid}/status")
            if st.json()["status"] == "failed":
                break
            await asyncio.sleep(0.05)
        assert st.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_session_marked_failed_when_client_construction_raises(client, monkeypatch):
    import asyncio

    from app.db.base import engine
    from app.generation import router as gen_router

    # The background task (and its _mark_session_failed fallback) uses the app's
    # own pooled engine, not the per-test NullPool engine. Across the test
    # suite each test runs in a fresh event loop, so dispose the pool here to
    # drop any connection bound to a previous loop before this test's
    # background task opens a fresh SessionLocal(). (Production keeps one loop;
    # this is purely test isolation.)
    await engine.dispose()

    def _boom():
        raise RuntimeError("bad OPENAI key")

    monkeypatch.setattr(gen_router, "build_openai_client", _boom)
    await _register(client, "peggy")
    resp = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
    assert resp.status_code == 201
    sid = resp.json()["id"]
    # Poll until the session resolves to failed (must NOT stay generating forever)
    for _ in range(50):
        st = await client.get(f"/sessions/{sid}/status")
        if st.json()["status"] == "failed":
            break
        await asyncio.sleep(0.05)
    assert st.json()["status"] == "failed"
