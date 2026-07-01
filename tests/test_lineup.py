from goalforge.data.synthetic import generate_dataset
from goalforge.prediction.lineup import likely_xi


def test_likely_xi_recent():
    d = generate_dataset(n_teams=8, seed=0)
    team = d.teams[0]
    xi = likely_xi(d.appearances, d.matches, team, n=11, recent_matches=5)
    assert len(xi) == 11
    assert len(set(xi)) == 11
    played = set(d.appearances[d.appearances.team == team].player)
    assert set(xi) <= played
