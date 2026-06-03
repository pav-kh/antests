from app.generation import topics


def test_ten_topics_for_each_level():
    assert len(topics.TOPICS) == 10


def test_proportions_sum_to_one_per_level():
    for level in ("base", "specialist"):
        total = sum(t.proportions[level] for t in topics.TOPICS)
        assert abs(total - 1.0) < 1e-6, f"{level} sums to {total}"


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
