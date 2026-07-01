from goalforge.data.synthetic import generate_dataset
from goalforge.evaluation.baselines import EloBaseline, base_rates


def test_base_rates_sum_to_one():
    d = generate_dataset(n_teams=8, seed=1)
    br = base_rates(d.matches)
    assert abs(sum(br) - 1.0) < 1e-9
    assert all(0.0 <= x <= 1.0 for x in br)


def test_elo_probs_valid_and_ranking():
    d = generate_dataset(n_teams=10, seed=2)
    elo = EloBaseline().fit(d.matches)
    p = elo.predict_proba(d.teams[0], d.teams[1])
    assert abs(sum(p.values()) - 1.0) < 1e-9
    strong = max(elo.r, key=elo.r.get)
    weak = min(elo.r, key=elo.r.get)
    ps = elo.predict_proba(strong, weak, neutral=True)
    assert ps["home_win"] > ps["away_win"]
