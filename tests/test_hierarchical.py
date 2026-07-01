from goalforge.data.synthetic import generate_dataset
from goalforge.models.hierarchical import HierarchicalDixonColes


def test_fit_cv_selects_shrinkage_and_predicts():
    d = generate_dataset(n_teams=10, seed=1)
    grid = (0.01, 0.3, 1.0)
    m = HierarchicalDixonColes().fit_cv(d.matches, l2_grid=grid, cv_splits=2)
    assert m.cv_l2_ in grid
    assert set(m.cv_scores_) == set(grid)
    p = m.predict_proba(d.teams[0], d.teams[1])
    assert abs(sum(p.values()) - 1.0) < 1e-6
