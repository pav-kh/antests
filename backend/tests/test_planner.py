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
