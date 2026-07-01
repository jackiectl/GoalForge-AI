from goalforge.evaluation.metrics import brier_score, ece, outcome_index, rps


def test_rps_bounds():
    assert rps([1, 0, 0], 0) == 0.0          # perfect forecast
    assert rps([0, 0, 1], 0) == 1.0          # worst forecast (home won, all mass on away)
    assert 0.0 < rps([1 / 3, 1 / 3, 1 / 3], 0) < 1.0


def test_outcome_index():
    assert outcome_index(2, 1) == 0
    assert outcome_index(1, 1) == 1
    assert outcome_index(0, 2) == 2


def test_brier():
    assert brier_score([1, 0, 0], 0) == 0.0
    assert brier_score([0, 1, 0], 0) == 2.0


def test_ece():
    assert ece([[1, 0, 0], [0, 1, 0]], [0, 1]) == 0.0        # confident & correct
    assert ece([[1, 0, 0], [1, 0, 0]], [2, 2]) == 1.0        # confident & wrong
