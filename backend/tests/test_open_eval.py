import pytest
from app.assessment.open_eval import evaluate_open


class FakeJudge:
    async def judge_open(self, stem, rubric, answer):
        return f"feedback for: {answer}"


@pytest.mark.asyncio
async def test_empty_answer_skips_llm():
    fb = await evaluate_open(FakeJudge(), stem="Q", rubric="что раскрыть", answer="")
    assert "не ответ" in fb.lower() or "не дан" in fb.lower()


@pytest.mark.asyncio
async def test_too_short_answer_skips_llm():
    fb = await evaluate_open(FakeJudge(), stem="Q", rubric="r", answer="  нет  ")
    assert "feedback for" not in fb


@pytest.mark.asyncio
async def test_real_answer_uses_judge():
    answer = "Спросить статус заявки, сроки, причины задержки; предложить уведомления."
    fb = await evaluate_open(FakeJudge(), stem="Q", rubric="r", answer=answer)
    assert fb == f"feedback for: {answer}"


@pytest.mark.asyncio
async def test_judge_failure_is_non_fatal():
    class Boom:
        async def judge_open(self, *a, **k):
            raise RuntimeError("openai down")
    fb = await evaluate_open(Boom(), stem="Q", rubric="r",
                             answer="достаточно длинный ответ для оценки судьёй")
    assert fb == ""
