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


def test_system_prompt_forbids_programming_code_and_stem_duplication():
    p = build_generation_system_prompt().lower()
    # no programming-language code (analyst test, not a coding test)
    assert "python" in p or "программир" in p
    # artifact must not be duplicated into the stem
    assert "artifact_content" in p
    assert "stem" in p


def test_strip_artifact_from_stem_removes_fenced_blocks():
    from app.generation.openai_client import _strip_artifact_from_stem
    # complete fenced mermaid block is removed
    s = "В какой нотации показать процесс? ```mermaid\nflowchart TD\nA-->B\n```"
    assert _strip_artifact_from_stem(s) == "В какой нотации показать процесс?"
    # clean stem is untouched
    assert _strip_artifact_from_stem("Обычный вопрос.") == "Обычный вопрос."
    # truncated/dangling fence is also removed
    assert _strip_artifact_from_stem("Вопрос ```mermaid\nA-->") == "Вопрос"


@pytest.mark.asyncio
async def test_generate_batch_scrubs_leaked_artifact_from_stem():
    # The model leaks the mermaid block into the stem AND fills artifact_content.
    leaked = {
        "topic_id": "modeling", "type": "single",
        "stem": "Что показано на диаграмме? ```mermaid\nflowchart TD\nA-->B\n```",
        "artifact_kind": "mermaid", "artifact_content": "flowchart TD\nA-->B",
        "options": [{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        "correct_keys": ["a"], "explanation": "because",
    }
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_FakeOpenAI({"questions": [leaked]}))
    batch = await client.generate_batch("base", "exam", [("modeling", 1)])
    q = batch.questions[0]
    assert "```" not in q.stem
    assert "flowchart" not in q.stem.lower()
    assert q.stem == "Что показано на диаграмме?"
    # the artifact is preserved in its own field
    assert q.artifact_content == "flowchart TD\nA-->B"


@pytest.mark.asyncio
async def test_generate_batch_raises_on_empty_content():
    import pytest
    from app.generation.openai_client import OpenAIClient, OpenAIResponseError

    class _NoneMsg:
        content = None
        finish_reason = "content_filter"
    class _Choice:
        message = _NoneMsg()
        finish_reason = "content_filter"
    class _Completion:
        choices = [_Choice()]
    class _Completions:
        async def create(self, **kw): return _Completion()
    class _Chat:
        completions = _Completions()
    class _Client:
        chat = _Chat()

    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v", _client=_Client())
    with pytest.raises(OpenAIResponseError):
        await client.generate_batch("base", "exam", [("data", 1)])
