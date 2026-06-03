from app.generation.topics import TOPICS

LEVEL_TOTALS = {"base": 80, "specialist": 120}


def _largest_remainder(weights: dict[str, float], total: int) -> list[tuple[str, int]]:
    """Apportion `total` across keys by weight, guaranteeing the sum equals total."""
    raw = {k: w * total for k, w in weights.items()}
    floored = {k: int(v) for k, v in raw.items()}
    assigned = sum(floored.values())
    remainder = total - assigned
    frac_order = sorted(weights, key=lambda k: raw[k] - floored[k], reverse=True)
    for k in frac_order[:remainder]:
        floored[k] += 1
    return [(k, c) for k, c in floored.items() if c > 0]


def plan_exam(level: str) -> list[tuple[str, int]]:
    total = LEVEL_TOTALS[level]
    weights = {t.id: t.proportions[level] for t in TOPICS}
    plan = _largest_remainder(weights, total)
    present = {tid for tid, _ in plan}
    missing = [t.id for t in TOPICS if t.id not in present]
    plan_d = dict(plan)
    for tid in missing:
        donor = max(plan_d, key=plan_d.get)
        plan_d[donor] -= 1
        plan_d[tid] = 1
    return [(tid, c) for tid, c in plan_d.items() if c > 0]


def plan_adaptive(
    competency: dict[str, float], total: int, threshold: float
) -> list[tuple[str, int]]:
    if not competency:
        weights = {t.id: 1 / len(TOPICS) for t in TOPICS}
        return _largest_remainder(weights, total)

    weak = {tid: acc for tid, acc in competency.items() if acc < threshold}
    if not weak:
        ranked = sorted(competency.items(), key=lambda kv: kv[1])[:3]
        weak = dict(ranked)

    inv = {tid: (1.0 - acc) + 0.01 for tid, acc in weak.items()}
    s = sum(inv.values())
    weights = {tid: v / s for tid, v in inv.items()}
    return _largest_remainder(weights, total)
