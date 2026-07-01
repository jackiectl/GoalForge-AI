from goalforge.data.synthetic import generate_dataset
from goalforge.models.scoreline import DixonColesModel


def test_fit_matrix_and_probs():
    data = generate_dataset(n_teams=10, n_rounds=2, seed=1)
    dc = DixonColesModel().fit(data.matches)
    h, a = data.teams[0], data.teams[1]

    M = dc.score_matrix(h, a)
    assert abs(M.sum() - 1.0) < 1e-6
    assert (M >= 0).all()

    p = dc.predict_proba(h, a)
    assert abs(sum(p.values()) - 1.0) < 1e-6
    assert all(0.0 <= v <= 1.0 for v in p.values())


def test_home_advantage_positive():
    data = generate_dataset(n_teams=10, seed=2)
    dc = DixonColesModel().fit(data.matches)
    assert dc.home_adv_ > 0  # synthetic data has a real home advantage


def test_time_decay_runs():
    data = generate_dataset(n_teams=8, seed=5)
    dc = DixonColesModel().fit(data.matches, half_life_days=120)
    lam_h, lam_a = dc.expected_goals(data.teams[0], data.teams[1])
    assert lam_h > 0 and lam_a > 0
