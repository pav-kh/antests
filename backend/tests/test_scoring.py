from app.assessment.scoring import is_answer_correct, score


def test_single_correct():
    assert is_answer_correct(["a"], ["a"]) is True


def test_single_wrong():
    assert is_answer_correct(["b"], ["a"]) is False


def test_multi_exact_match_correct():
    assert is_answer_correct(["a", "c"], ["c", "a"]) is True


def test_multi_partial_is_wrong():
    assert is_answer_correct(["a"], ["a", "c"]) is False


def test_multi_extra_is_wrong():
    assert is_answer_correct(["a", "b", "c"], ["a", "c"]) is False


def test_empty_selection_is_wrong():
    assert is_answer_correct([], ["a"]) is False


def test_score_percent_and_pass():
    result = score(correct_count=7, total=10, threshold_percent=70)
    assert result.percent == 70.0
    assert result.passed is True


def test_score_below_threshold_fails():
    result = score(correct_count=7, total=10, threshold_percent=75)
    assert result.percent == 70.0
    assert result.passed is False


def test_score_zero_total_is_safe():
    result = score(correct_count=0, total=0, threshold_percent=70)
    assert result.percent == 0.0
    assert result.passed is False
