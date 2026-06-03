from app.generation.planner import plan_exam, plan_adaptive


def test_exam_plan_totals_match_level():
    base = plan_exam("base")
    spec = plan_exam("specialist")
    assert sum(c for _, c in base) == 80
    assert sum(c for _, c in spec) == 120


def test_exam_plan_covers_all_topics():
    plan = dict(plan_exam("specialist"))
    assert len(plan) == 10
    assert all(c >= 1 for c in plan.values())


def test_adaptive_plan_picks_weakest_topics():
    competency = {
        "requirements": 0.9,
        "data": 0.2,
        "integration": 0.3,
        "modeling": 0.95,
    }
    plan = plan_adaptive(competency, total=10, threshold=0.6)
    chosen = {tid for tid, _ in plan}
    assert chosen == {"data", "integration"}
    assert sum(c for _, c in plan) == 10


def test_adaptive_falls_back_when_no_weak_topics():
    competency = {"requirements": 0.9, "data": 0.85, "modeling": 0.95}
    plan = plan_adaptive(competency, total=6, threshold=0.6)
    assert sum(c for _, c in plan) == 6
    assert len(plan) >= 1


def test_adaptive_with_empty_competency_uses_even_distribution():
    plan = plan_adaptive({}, total=10, threshold=0.6)
    assert sum(c for _, c in plan) == 10
    assert len(plan) == 10


def test_largest_remainder_sums_to_total_for_non_normalized_weights():
    from app.generation.planner import _largest_remainder
    # Weights summing to > 1.0 must still apportion exactly `total`.
    plan = dict(_largest_remainder({"a": 0.5, "b": 0.5, "c": 0.5}, 10))
    assert sum(plan.values()) == 10
    # Weights summing to < 1.0 must still apportion exactly `total`.
    plan2 = dict(_largest_remainder({"a": 0.1, "b": 0.1}, 10))
    assert sum(plan2.values()) == 10


def test_largest_remainder_handles_total_smaller_than_keys():
    from app.generation.planner import _largest_remainder
    # total < number of keys: still sums exactly, some keys get 0 (filtered out).
    plan = dict(_largest_remainder({"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0}, 2))
    assert sum(plan.values()) == 2


def test_largest_remainder_zero_weights_distributes_evenly():
    from app.generation.planner import _largest_remainder
    plan = dict(_largest_remainder({"a": 0.0, "b": 0.0}, 4))
    assert sum(plan.values()) == 4
