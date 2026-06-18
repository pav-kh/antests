from app.generation import topics


def test_ten_topics_for_each_level():
    assert len(topics.TOPICS) == 10


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
