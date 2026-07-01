import numpy as np

from goalforge.data.synthetic import generate_dataset
from goalforge.models.player import PlayerRatings
from goalforge.models.scoreline import DixonColesModel
from goalforge.prediction.agent import GoalForgeAgent


def test_agent_roundtrip_and_predict(tmp_path):
    d = generate_dataset(n_teams=8, seed=0)
    dc = DixonColesModel(l2=0.1).fit(d.matches)
    ratings = PlayerRatings().fit(d.appearances, d.goals)
    agent = GoalForgeAgent(dc, ratings, {"k": 1})

    path = tmp_path / "agent.pkl"
    agent.save(path)
    loaded = GoalForgeAgent.load(path)
    assert loaded.meta == {"k": 1}

    home_names = ratings.most_used_xi(d.appearances, d.teams[0])
    home = loaded.build_lineup(d.teams[0], home_names)
    away = loaded.build_lineup(d.teams[1], ratings.most_used_xi(d.appearances, d.teams[1]))
    pred = loaded.predict(home, away, n_sims=3000, rng=np.random.default_rng(0))
    assert 0.0 <= pred.prob_home <= 1.0
    assert len(pred.home_scorers) == len(home_names)
