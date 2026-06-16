MIN_ANSWER_CHARS = 10

EMPTY_FEEDBACK = (
    "Вы не ответили на этот вопрос (или ответ слишком короткий). "
    "Для сильного ответа стоило раскрыть пункты из разбора ниже."
)


async def evaluate_open(judge_client, stem: str, rubric: str, answer: str) -> str:
    """Feedback for one open answer. Empty/too-short answers get a stub without
    an LLM call. A judge failure is non-fatal (returns '') so finishing the test
    never breaks."""
    if len((answer or "").strip()) < MIN_ANSWER_CHARS:
        return EMPTY_FEEDBACK
    try:
        return await judge_client.judge_open(stem, rubric, answer)
    except Exception:
        return ""
