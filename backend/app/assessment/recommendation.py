PASS_PRAISE = (
    "Отличный результат — слабых тем не выявлено. Поддерживайте уровень: "
    "периодически повторяйте материал и пробуйте полные экзамены-симуляции."
)


async def build_recommendation(
    openai_client,
    level: str,
    topic_accuracy: dict[str, float],
    threshold: float,
) -> str:
    """Pick topics below the threshold and ask the LLM for targeted advice.
    If there are none, return praise without an LLM call."""
    weak = sorted(
        ((tid, acc) for tid, acc in topic_accuracy.items() if acc < threshold),
        key=lambda kv: kv[1],
    )
    if not weak:
        return PASS_PRAISE
    if openai_client is None:
        # No LLM available (e.g. OPENAI_API_KEY missing). Finishing must still
        # succeed; we just can't produce targeted advice this time.
        return ""
    return await openai_client.recommend(level, weak)
