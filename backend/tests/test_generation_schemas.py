import pytest
from pydantic import ValidationError
from app.generation.schemas import GeneratedQuestion, ValidationVerdict


def test_single_question_requires_exactly_one_correct():
    q = GeneratedQuestion(
        topic_id="data", type="single", stem="Q?",
        artifact_kind="none", artifact_content=None,
        options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
        correct_keys=["a"], explanation="because",
    )
    assert q.correct_keys == ["a"]


def test_single_with_multiple_correct_is_invalid():
    with pytest.raises(ValidationError):
        GeneratedQuestion(
            topic_id="data", type="single", stem="Q?",
            artifact_kind="none", artifact_content=None,
            options=[{"key": "a", "text": "x"}, {"key": "b", "text": "y"}],
            correct_keys=["a", "b"], explanation="because",
        )


def test_correct_keys_must_exist_in_options():
    with pytest.raises(ValidationError):
        GeneratedQuestion(
            topic_id="data", type="single", stem="Q?",
            artifact_kind="none", artifact_content=None,
            options=[{"key": "a", "text": "x"}],
            correct_keys=["z"], explanation="because",
        )


def test_validation_verdict():
    v = ValidationVerdict(valid=True, reason="ok")
    assert v.valid is True
