from app.generation import topics


def test_eighteen_topics_total():
    assert len(topics.TOPICS) == 18


def test_proportions_sum_to_one_per_level():
    # base/specialist proportions are designed to sum to 1.0
    for level in ("base", "specialist"):
        total = sum(t.proportions[level] for t in topics.TOPICS)
        assert abs(total - 1.0) < 1e-6, f"{level} sums to {total}"


def test_ba_proportions_present_and_positive():
    # Every topic must carry a ba weight; the column total must be positive.
    # (ba weights are not consumed yet — a later task wires the planner to read
    # proportions["ba"]; this guards the data shape until then. They need NOT
    # sum to 1.0 — the planner normalizes per-level when it does consume them.)
    assert all("ba" in t.proportions for t in topics.TOPICS)
    assert all(t.proportions["ba"] >= 0 for t in topics.TOPICS)
    assert sum(t.proportions["ba"] for t in topics.TOPICS) > 0


NEW_BA_TOPIC_IDS = {
    "stakeholders", "strategy", "process_analysis", "elicitation",
    "solution_value", "agile_ba", "ba_planning", "soft_skills",
}


def test_new_ba_topics_present_and_ba_only():
    by_id = {t.id: t for t in topics.TOPICS}
    for tid in NEW_BA_TOPIC_IDS:
        assert tid in by_id, f"missing new topic {tid}"
        t = by_id[tid]
        assert t.proportions["ba"] > 0
        # New BA topics must NOT appear in base/specialist plans
        assert t.proportions["base"] == 0.0
        assert t.proportions["specialist"] == 0.0
        assert len(t.subtopics) >= 3


def test_stakeholders_owns_raci_analysis_angle():
    s = topics.get_topic("stakeholders")
    joined = " ".join(s.subtopics)
    assert "RACI как инструмент анализа стейкхолдеров" in joined


def test_methodology_raci_is_project_role_angle():
    m = topics.get_topic("methodology")
    joined = " ".join(m.subtopics)
    # Assert the FULL reworded phrase, incl. the "по задачам проекта" angle that
    # distinguishes it from the stakeholders topic's RACI-as-analysis framing.
    assert "RACI как распределение ролей по задачам проекта" in joined


def test_every_topic_has_id_title_and_subtopics():
    for t in topics.TOPICS:
        assert t.id
        assert t.title
        assert isinstance(t.subtopics, list) and len(t.subtopics) >= 1


def test_get_topic_by_id():
    t = topics.get_topic("requirements")
    assert t.title


def test_get_unknown_topic_raises():
    import pytest
    with pytest.raises(KeyError):
        topics.get_topic("nope")
