from goalforge.data.synthetic import generate_dataset
from goalforge.evaluation.backtest import walk_forward_backtest
from goalforge.prediction.predict_match import _demo


def test_end_to_end_demo():
    pred = _demo(n_sims=5_000, seed=0)
    assert 0.0 <= pred.prob_home <= 1.0
    assert len(pred.home_scorers) == 11 and len(pred.away_assisters) == 11
    assert "scorers" in pred.summary()


def test_backtest_beats_baseline():
    data = generate_dataset(n_teams=12, n_rounds=2, seed=3)
    res = walk_forward_backtest(data.matches, n_splits=3)
    assert res["n"] > 0
    # With real signal in the data, the fitted model should beat naive base rates.
    assert res["model_rps"] < res["baseline_rps"]
