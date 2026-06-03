import json
import pytest
from app.generation.openai_client import OpenAIClient, build_generation_system_prompt
from app.generation.schemas import GeneratedQuestion


class _FakeMessage:
    def __init__(self, content): self.content = content


class _FakeChoice:
    def __init__(self, content): self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content): self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, payload): self._payload = payload
    async def create(self, **kwargs):
        return _FakeCompletion(json.dumps(self._payload))


class _FakeChat:
    def __init__(self, payload): self.completions = _FakeCompletions(payload)


class _FakeOpenAI:
    def __init__(self, payload): self.chat = _FakeChat(payload)


def _valid_question_payload():
    return {
        "topic_id": "data", "type": "single", "stem": "Q?",
        "artifact_kind": "none", "artifact_content": None,
        "options": [{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        "correct_keys": ["a"], "explanation": "because",
    }


@pytest.mark.asyncio
async def test_generate_batch_parses_questions():
    payload = {"questions": [_valid_question_payload(), _valid_question_payload()]}
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_FakeOpenAI(payload))
    batch = await client.generate_batch("specialist", "exam", [("data", 2)])
    assert len(batch.questions) == 2
    assert isinstance(batch.questions[0], GeneratedQuestion)


@pytest.mark.asyncio
async def test_validate_question_returns_verdict():
    payload = {"valid": True, "reason": "looks correct"}
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_FakeOpenAI(payload))
    q = GeneratedQuestion(**_valid_question_payload())
    verdict = await client.validate_question(q)
    assert verdict.valid is True


def test_system_prompt_mentions_quality_rules():
    p = build_generation_system_prompt()
    assert "однознач" in p.lower() or "ровно один" in p.lower()
    assert "mermaid" in p.lower()
