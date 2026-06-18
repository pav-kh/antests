import asyncio
import itertools

import pytest

from app.generation.schemas import (
    GeneratedBatch,
    GeneratedQuestion,
    OpenQuestion,
    ValidationVerdict,
)

_stem_counter = itertools.count()


def _q(topic_id="data"):
    # Distinct stem per call so the generator's per-topic dedup guard (which
    # skips exact-duplicate stems) doesn't collapse the batch.
    return GeneratedQuestion(
        topic_id=topic_id, type="single", stem=f"Q{next(_stem_counter)}?",
        artifact_kind="none", artifact_content=None,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        correct_keys=["a"], explanation="because",
    )


class FakeClient:
    async def generate_batch(
        self, level, mode, plan_slice, avoid_stems=None, want_artifact=False,
        multi_ratio=None, mermaid_only=False,
    ):
        n = sum(c for _, c in plan_slice)
        return GeneratedBatch(questions=[_q(plan_slice[0][0]) for _ in range(n)])

    async def validate_question(self, q):
        return ValidationVerdict(valid=True, reason="ok")

    async def generate_open_questions(self, level, count=3):
        return [
            OpenQuestion(stem=f"Открытый {i}", rubric=f"критерии {i}",
                         explanation=f"разбор {i}")
            for i in range(count)
        ]

    async def generate_open_on_topic(self, topic_title, hint):
        return OpenQuestion(stem=f"Тема: {topic_title}", rubric="rt", explanation="et")


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    from app.generation import router as gen_router
    monkeypatch.setattr(gen_router, "build_openai_client", lambda: FakeClient())


async def _register(client, login="kate"):
    return await client.post(
        "/auth/register",
        json={"login": login, "password": "pw12345", "access_code": "TEST-CODE"},
    )


async def _make_ready_session(client):
    resp = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
    sid = resp.json()["id"]
    for _ in range(50):
        st = await client.get(f"/sessions/{sid}/status")
        if st.json()["status"] == "ready":
            break
        await asyncio.sleep(0.05)
    qs = (await client.get(f"/sessions/{sid}/questions")).json()
    return sid, qs


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
    # total_questions is the CLOSED pool; 3 open questions are appended on top as
    # a bonus section (base: 1 seed + 2 themed), so generated_count covers
    # closed + 3 open.
    assert body["generated_count"] == body["total_questions"] + 3

    qs = await client.get(f"/sessions/{sid}/questions")
    items = qs.json()
    closed = [it for it in items if it["type"] in ("single", "multi")]
    openq = [it for it in items if it["type"] == "open"]
    assert len(closed) == body["total_questions"]
    assert len(openq) == 3
    assert "correct_keys" not in items[0]
    assert "explanation" not in items[0]
    assert {"id", "seq", "topic_id", "type", "stem", "options"} <= set(items[0].keys())


@pytest.mark.asyncio
async def test_start_timer_is_idempotent(client):
    await _register(client, "timer_u")
    sid, _ = await _make_ready_session(client)

    # A freshly-ready session has no timer until the user enters the exam.
    pre = await client.get(f"/sessions/{sid}/status")
    assert pre.json()["timer_started_at"] is None

    r1 = await client.post(f"/sessions/{sid}/start")
    assert r1.status_code == 200
    t1 = r1.json()["timer_started_at"]
    assert t1 is not None

    r2 = await client.post(f"/sessions/{sid}/start")
    assert r2.status_code == 200
    assert r2.json()["timer_started_at"] == t1  # unchanged on re-entry


@pytest.mark.asyncio
async def test_start_timer_requires_ownership(client):
    await _register(client, "owner_u")
    sid, _ = await _make_ready_session(client)
    await client.post("/auth/logout")
    await _register(client, "intruder_u")
    r = await client.post(f"/sessions/{sid}/start")
    assert r.status_code == 404


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
async def test_failed_generation_refunds_exactly_one_slot(client, db_session, monkeypatch):
    # Prove the refund fires exactly once (not zero, not twice). decrement_usage
    # floors at 0, so a base of 0 would mask an over-refund; seed a non-zero base.
    import datetime as dt

    from sqlalchemy import select

    from app.auth import service as auth_service
    from app.db.base import engine
    from app.db.models import User
    from app.generation import router as gen_router

    # Background task uses the app's pooled engine; dispose so its SessionLocal()
    # binds to this test's event loop (see sibling failed-generation tests).
    await engine.dispose()

    def _boom():
        raise RuntimeError("bad key")

    monkeypatch.setattr(gen_router, "build_openai_client", _boom)

    await _register(client, "wade")
    user = (
        await db_session.execute(select(User).where(User.login == "wade"))
    ).scalar_one()
    today = dt.datetime.now(dt.timezone.utc).date()
    # Seed the counter to a known non-zero base so an over-refund can't be
    # masked by the floor-at-zero in decrement_usage.
    await auth_service.increment_usage(db_session, user.id, today)  # base = 1
    base = await auth_service.get_usage_count(db_session, user.id, today)

    resp = await client.post("/sessions", json={"level": "base", "mode": "adaptive"})
    assert resp.status_code == 201
    sid = resp.json()["id"]
    for _ in range(50):
        st = await client.get(f"/sessions/{sid}/status")
        if st.json()["status"] == "failed":
            break
        await asyncio.sleep(0.05)
    assert st.json()["status"] == "failed"

    # create_session incremented to base+1, then the failure refunded exactly
    # one -> back to base. Poll to avoid a race between the status flip and the
    # refund commit (they happen in the same background task, but ordering of
    # the commit relative to the observed status flip is not guaranteed).
    final = None
    for _ in range(50):
        final = await auth_service.get_usage_count(db_session, user.id, today)
        if final == base:
            break
        await asyncio.sleep(0.05)
    assert final == base, f"expected exactly one refund (final {final} == base {base})"


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


@pytest.mark.asyncio
async def test_create_ba_session_uses_40_and_90min(client):
    await _register(client, "ba_user")
    resp = await client.post("/sessions", json={"level": "ba", "mode": "exam"})
    assert resp.status_code == 201
    sid = resp.json()["id"]

    for _ in range(50):
        st = await client.get(f"/sessions/{sid}/status")
        if st.json()["status"] == "ready":
            break
        await asyncio.sleep(0.05)

    body = (await client.get(f"/sessions/{sid}/status")).json()
    assert body["level"] == "ba"
    assert body["time_limit_sec"] == 90 * 60
    assert body["total_questions"] == 40

    qs = (await client.get(f"/sessions/{sid}/questions")).json()
    closed = [q for q in qs if q["type"] in ("single", "multi")]
    openq = [q for q in qs if q["type"] == "open"]
    assert len(closed) == 40
    assert len(openq) == 2
