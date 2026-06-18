import json

import pytest

from app.generation.openai_client import OpenAIClient
from app.generation.planner import LEVEL_MULTI_TARGET


class _CaptureCompletions:
    def __init__(self, payload):
        self.payload = payload
        self.last_user_prompt = None

    async def create(self, **kw):
        for m in kw["messages"]:
            if m["role"] == "user":
                self.last_user_prompt = m["content"]

        class _M:
            def __init__(s, c): s.content = c
        class _C:
            def __init__(s, c):
                s.message = _M(c)
                s.finish_reason = "stop"
        class _Comp:
            def __init__(s, c): s.choices = [_C(c)]
        return _Comp(json.dumps(self.payload))


class _CaptureChat:
    def __init__(self, comp): self.completions = comp


class _CaptureClient:
    def __init__(self, comp): self.chat = _CaptureChat(comp)


_VALID_BATCH = {"questions": [{
    "topic_id": "requirements", "type": "multi", "stem": "Q?",
    "artifact_kind": "none", "artifact_content": None,
    "options": [{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
    "correct_keys": ["a", "b"], "explanation": "e",
}]}


def test_ba_has_multi_target():
    assert LEVEL_MULTI_TARGET.get("ba") == 0.7
    assert "base" not in LEVEL_MULTI_TARGET
    assert "specialist" not in LEVEL_MULTI_TARGET


@pytest.mark.asyncio
async def test_generate_batch_adds_multi_instruction_when_ratio_set():
    comp = _CaptureCompletions(_VALID_BATCH)
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_CaptureClient(comp))
    await client.generate_batch("ba", "exam", [("requirements", 1)], multi_ratio=0.7)
    assert "несколько верных" in comp.last_user_prompt
    assert "70%" in comp.last_user_prompt


@pytest.mark.asyncio
async def test_generate_batch_no_multi_instruction_when_ratio_none():
    comp = _CaptureCompletions(_VALID_BATCH)
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_CaptureClient(comp))
    await client.generate_batch("base", "exam", [("requirements", 1)])
    assert "несколько верных" not in (comp.last_user_prompt or "")
