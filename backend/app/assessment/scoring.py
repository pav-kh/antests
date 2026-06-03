from dataclasses import dataclass


def is_answer_correct(selected_keys: list[str], correct_keys: list[str]) -> bool:
    """Exact-match scoring for both single and multi choice: the selected set
    must equal the correct set exactly (no partial credit)."""
    return set(selected_keys) == set(correct_keys)


@dataclass(frozen=True)
class ScoreResult:
    percent: float
    passed: bool


def score(correct_count: int, total: int, threshold_percent: float) -> ScoreResult:
    percent = round(100.0 * correct_count / total, 2) if total > 0 else 0.0
    return ScoreResult(percent=percent, passed=percent >= threshold_percent)
