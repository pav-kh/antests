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

    async def recommend(self, level, weak_topics):
        return "Совет по подготовке."


@pytest.fixture(autouse=True)
def _patch_clients(monkeypatch):
    from app.generation import router as gen_router
    from app.assessment import router as asm_router
    monkeypatch.setattr(gen_router, "build_openai_client", lambda: FakeClient())
    monkeypatch.setattr(asm_router, "build_openai_client", lambda: FakeClient())


async def _register(client, login="quinn"):
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
async def test_full_flow_submit_finish_results(client):
    await _register(client, "quinn")
    sid, qs = await _make_ready_session(client)
    for q in qs:
        r = await client.post(
            f"/sessions/{sid}/answers",
            json={"question_id": q["id"], "selected_keys": ["a"]},
        )
        assert r.status_code == 200
    fin = await client.post(f"/sessions/{sid}/finish")
    assert fin.status_code == 200

    res = await client.get(f"/sessions/{sid}/results")
    assert res.status_code == 200
    body = res.json()
    assert body["passed"] is True
    assert body["score_percent"] == 100.0
    assert body["recommendation"]
    assert "correct_keys" in body["questions"][0]
    assert "explanation" in body["questions"][0]
    assert len(body["topic_breakdown"]) >= 1


@pytest.mark.asyncio
async def test_results_requires_ownership(client):
    await _register(client, "rita")
    sid, qs = await _make_ready_session(client)
    await client.post("/auth/logout")
    await _register(client, "sam")
    res = await client.get(f"/sessions/{sid}/results")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_finish_requires_auth(client):
    await _register(client, "tom")
    sid, qs = await _make_ready_session(client)
    await client.post("/auth/logout")
    fin = await client.post(f"/sessions/{sid}/finish")
    assert fin.status_code == 401
