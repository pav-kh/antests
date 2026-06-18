import json

import pytest

from app.generation.generator import (
    ARTIFACT_TOPICS,
    LEVEL_ARTIFACT_MERMAID_ONLY,
    LEVEL_ARTIFACT_TOPICS,
)
from app.generation.openai_client import OpenAIClient


class _Cap:
    def __init__(self, payload):
        self.payload = payload
        self.last = None

    async def create(self, **kw):
        for m in kw["messages"]:
            if m["role"] == "user":
                self.last = m["content"]

        class _M:
            def __init__(s, c):
                s.content = c

        class _C:
            def __init__(s, c):
                s.message = _M(c)
                s.finish_reason = "stop"

        class _Comp:
            def __init__(s, c):
                s.choices = [_C(c)]

        return _Comp(json.dumps(self.payload))


class _Chat:
    def __init__(self, c):
        self.completions = c


class _Client:
    def __init__(self, c):
        self.chat = _Chat(c)


_BATCH = {"questions": [{
    "topic_id": "modeling", "type": "single", "stem": "Q?",
    "artifact_kind": "mermaid", "artifact_content": "flowchart TD\n A-->B",
    "options": [{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
    "correct_keys": ["a"], "explanation": "e",
}]}


def test_ba_artifact_topics_are_modeling_and_process_analysis():
    assert LEVEL_ARTIFACT_TOPICS["ba"] == {"modeling", "process_analysis"}
    # base/specialist have artifacts turned off entirely (empty set) — code/data
    # artifacts lost their pedagogical value there.
    assert LEVEL_ARTIFACT_TOPICS["base"] == set()
    assert LEVEL_ARTIFACT_TOPICS["specialist"] == set()
    assert "ba" in LEVEL_ARTIFACT_MERMAID_ONLY
    # ba drops the SA-only data/integration artifact topics from ARTIFACT_TOPICS
    assert "data" in ARTIFACT_TOPICS
    assert "data" not in LEVEL_ARTIFACT_TOPICS["ba"]
    assert "integration" not in LEVEL_ARTIFACT_TOPICS["ba"]


@pytest.mark.asyncio
async def test_generate_batch_mermaid_only_prompt():
    cap = _Cap(_BATCH)
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v", _client=_Client(cap))
    await client.generate_batch("ba", "exam", [("modeling", 1)], want_artifact=True, mermaid_only=True)
    assert "Mermaid" in cap.last
    assert "artifact_kind='mermaid'" in cap.last
    # no SQL/JSON/XML offered in the mermaid-only prompt
    assert "SQL-запрос" not in cap.last
    assert "JSON, XML" not in cap.last


@pytest.mark.asyncio
async def test_generate_batch_full_artifact_prompt_unchanged_for_base():
    cap = _Cap(_BATCH)
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v", _client=_Client(cap))
    await client.generate_batch("base", "exam", [("data", 1)], want_artifact=True)  # mermaid_only defaults False
    # the original multi-format wording is present
    assert "SQL-запрос" in cap.last
    assert "JSON" in cap.last


@pytest.mark.asyncio
async def test_generate_batch_no_artifact_block_when_not_wanted():
    cap = _Cap(_BATCH)
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v", _client=_Client(cap))
    await client.generate_batch("ba", "exam", [("requirements", 1)])  # want_artifact defaults False
    assert "артефакт" not in (cap.last or "")
