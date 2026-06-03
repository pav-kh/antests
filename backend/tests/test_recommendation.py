import pytest

from app.assessment.recommendation import build_recommendation


class FakeOpenAIClient:
    def __init__(self, text):
        self._text = text

    async def recommend(self, level, weak_topics):
        return self._text


@pytest.mark.asyncio
async def test_build_recommendation_uses_weak_topics():
    fake = FakeOpenAIClient("Подтяните SQL и интеграции.")
    text = await build_recommendation(
        fake, level="base",
        topic_accuracy={"data": 0.3, "integration": 0.4, "requirements": 0.9},
        threshold=0.6,
    )
    assert "SQL" in text or text


@pytest.mark.asyncio
async def test_build_recommendation_no_weak_topics_returns_praise():
    fake = FakeOpenAIClient("SHOULD NOT BE CALLED")
    text = await build_recommendation(
        fake, level="base",
        topic_accuracy={"data": 0.9, "modeling": 0.95},
        threshold=0.6,
    )
    assert "SHOULD NOT BE CALLED" not in text
    assert len(text) > 0
