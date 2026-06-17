from app.generation.open_seed import SEED_OPEN_QUESTIONS
from app.generation.schemas import OpenQuestion


def test_seed_pool_nonempty_and_valid():
    assert len(SEED_OPEN_QUESTIONS) >= 2
    for q in SEED_OPEN_QUESTIONS:
        assert isinstance(q, OpenQuestion)  # passes OpenQuestion._check (non-empty fields)
        # Visible stem carries the labelled blocks the real test shows
        assert "Задание:" in q.stem
        assert "Фокос ответа:" in q.stem or "Фокус ответа:" in q.stem
        assert "Критерии оценки:" in q.stem
        assert "до 2500 знаков" in q.stem
        # Hidden rubric is separate from the visible stem and non-trivial
        assert q.rubric and q.rubric not in q.stem
        assert q.explanation


def test_seed_pool_covers_the_two_known_cases():
    titles = " ".join(q.stem for q in SEED_OPEN_QUESTIONS)
    assert "От бизнес-проблемы к требованиям" in titles
    assert "Изменение, приемка и готовность результата" in titles \
        or "Изменение, приёмка и готовность результата" in titles
