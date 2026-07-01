import numpy as np

from goalforge.data.schema import Lineup, Player
from goalforge.simulation.montecarlo import simulate_match


def _lineup(team: str, strong: int = 0) -> Lineup:
    players = [
        Player(f"{team}_{i}", "FWD" if i < 3 else "MID",
               scoring_rate=(0.6 if i == strong else 0.1), assist_rate=0.1)
        for i in range(11)
    ]
    return Lineup(team, players)


def test_probs_valid_and_deterministic():
    h, a = _lineup("H"), _lineup("A")
    p1 = simulate_match(h, a, 1.6, 1.1, n_sims=20_000, rng=np.random.default_rng(0))
    p2 = simulate_match(h, a, 1.6, 1.1, n_sims=20_000, rng=np.random.default_rng(0))
    assert abs((p1.prob_home + p1.prob_draw + p1.prob_away) - 1.0) < 1e-9
    assert p1.prob_home == p2.prob_home                      # deterministic given seed
    assert p1.home_scorers[0][0] == "H_0"                    # strongest player tops scorers
    assert all(0.0 <= pr <= 1.0 for _, pr in p1.home_scorers)
    assert len(p1.home_scorers) == 11


def test_more_goals_more_scoring():
    h, a = _lineup("H"), _lineup("A")
    low = simulate_match(h, a, 0.5, 0.5, n_sims=20_000, rng=np.random.default_rng(1))
    high = simulate_match(h, a, 3.0, 0.5, n_sims=20_000, rng=np.random.default_rng(1))
    assert dict(high.home_scorers)["H_0"] > dict(low.home_scorers)["H_0"]


def test_stronger_lambda_more_wins():
    h, a = _lineup("H"), _lineup("A")
    pred = simulate_match(h, a, 2.5, 0.7, n_sims=20_000, rng=np.random.default_rng(2))
    assert pred.prob_home > pred.prob_away
