from app.generation import topics


def test_ten_topics_for_each_level():
    assert len(topics.TOPICS) == 10


def test_proportions_sum_to_one_per_level():
    # base/specialist proportions are designed to sum to 1.0
    for level in ("base", "specialist"):
        total = sum(t.proportions[level] for t in topics.TOPICS)
        assert abs(total - 1.0) < 1e-6, f"{level} sums to {total}"


def test_ba_proportions_present_and_positive():
    # ba weights need not sum to 1.0 — the planner normalizes them. Every topic
    # must carry a ba weight (>=0), and the total must be positive.
    ba_total = sum(t.proportions["ba"] for t in topics.TOPICS)
    assert ba_total > 0
    assert all("ba" in t.proportions for t in topics.TOPICS)


def test_methodology_raci_is_project_role_angle():
    m = topics.get_topic("methodology")
    joined = " ".join(m.subtopics)
    assert "RACI как распределение ролей" in joined


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
