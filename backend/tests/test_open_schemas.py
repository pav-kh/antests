import pytest
from pydantic import ValidationError
from app.generation.schemas import GeneratedQuestion, OpenQuestion


def test_open_question_schema_minimal():
    oq = OpenQuestion(stem="Опишите проблему и решения.", rubric="должен задать вопросы и предложить решения", explanation="хороший ответ...")
    assert oq.stem
    assert oq.rubric
    assert oq.explanation


def test_open_question_requires_rubric():
    with pytest.raises(ValidationError):
        OpenQuestion(stem="Q", rubric="", explanation="x")


def test_generated_question_still_rejects_open_type():
    with pytest.raises(ValidationError):
        GeneratedQuestion(
            topic_id="data", type="open", stem="Q",
            artifact_kind="none", artifact_content=None,
            options=[], correct_keys=[], explanation="x",
        )
