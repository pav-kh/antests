import json
import pytest
from app.generation.openai_client import OpenAIClient
from app.generation.schemas import OpenQuestion


class _Msg:
    def __init__(self, c): self.content = c
class _Choice:
    def __init__(self, c): self.message = _Msg(c); self.finish_reason = "stop"
class _Completion:
    def __init__(self, c): self.choices = [_Choice(c)]
class _Completions:
    def __init__(self, c): self._c = c
    async def create(self, **kw): return _Completion(self._c)
class _Chat:
    def __init__(self, c): self.completions = _Completions(c)
class _Client:
    def __init__(self, c): self.chat = _Chat(c)


@pytest.mark.asyncio
async def test_generate_open_questions_parses_two():
    payload = {"questions": [
        {"stem": "Опишите проблему повторных обращений и решения.",
         "rubric": "вопросы клиенту + решения", "explanation": "хороший ответ раскрывает..."},
        {"stem": "Как выявить причину задержки заявки?",
         "rubric": "диагностические вопросы", "explanation": "..."},
    ]}
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_Client(json.dumps(payload)))
    qs = await client.generate_open_questions("base", count=2)
    assert len(qs) == 2
    assert isinstance(qs[0], OpenQuestion)
    assert qs[0].rubric


@pytest.mark.asyncio
async def test_judge_open_returns_feedback():
    client = OpenAIClient(api_key="x", gen_model="g", validate_model="v",
                          _client=_Client("Хорошо, но упустили эскалацию."))
    fb = await client.judge_open(
        stem="Опишите решения.", rubric="вопросы + решения", answer="Спросить статус.")
    assert "эскалацию" in fb
