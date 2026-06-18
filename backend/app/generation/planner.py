from app.generation.topics import TOPICS

LEVEL_TOTALS = {"base": 50, "specialist": 50, "ba": 40}

# Target share of multi-answer (multiple correct) questions, per level. Soft
# quota: passed into the generation prompt as guidance, not enforced by
# discarding. Levels absent here keep the default (no multi steering).
LEVEL_MULTI_TARGET = {"ba": 0.7}


def _largest_remainder(weights: dict[str, float], total: int) -> list[tuple[str, int]]:
    """Apportion `total` across keys by weight, guaranteeing the sum equals total.

    Weights are normalized defensively so the sum invariant holds even if the
    caller passes weights that do not sum to 1.0.
    """
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        # Degenerate input: distribute evenly.
        norm = {k: 1 / len(weights) for k in weights} if weights else {}
    else:
        norm = {k: w / weight_sum for k, w in weights.items()}
    raw = {k: w * total for k, w in norm.items()}
    floored = {k: int(v) for k, v in raw.items()}
    assigned = sum(floored.values())
    remainder = total - assigned
    frac_order = sorted(norm, key=lambda k: raw[k] - floored[k], reverse=True)
    for k in frac_order[:remainder]:
        floored[k] += 1
    return [(k, c) for k, c in floored.items() if c > 0]


def plan_exam(level: str) -> list[tuple[str, int]]:
    total = LEVEL_TOTALS[level]
    weights = {t.id: t.proportions[level] for t in TOPICS}
    plan = _largest_remainder(weights, total)
    present = {tid for tid, _ in plan}
    # Backfill only topics that have a non-zero weight for THIS level — a topic
    # weighted 0 for the level (e.g. a ba-only topic under "specialist") must
    # never be force-injected into that level's plan.
    missing = [
        t.id for t in TOPICS
        if t.id not in present and t.proportions[level] > 0
    ]
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
