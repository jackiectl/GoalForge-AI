"""Run the pipeline on real StatsBomb World Cup 2022 data (requires statsbombpy).

    python scripts/run_worldcup.py [HOME_TEAM] [AWAY_TEAM]

Loads WC2022 open data, fits the scoreline + player models, and predicts a match at a
neutral venue. International tournament data is sparse (3-7 games/team), so treat this as a
pipeline demonstration on real data, not a tuned forecast — see docs/workflow.md on Bayesian
shrinkage for the proper fix. Data: StatsBomb open data (attribution: StatsBomb).
"""
import sys
import warnings

import numpy as np

from goalforge.data.statsbomb import WORLD_CUP_2022, load_competition
from goalforge.models.player import PlayerRatings
from goalforge.models.scoreline import DixonColesModel
from goalforge.prediction.predict_match import predict_match

warnings.filterwarnings("ignore")


def main(home: str = "Argentina", away: str = "France") -> None:
    print("Loading StatsBomb World Cup 2022 open data (attribution: StatsBomb)...")
    d = load_competition(*WORLD_CUP_2022, verbose=False)
    print(f"  {len(d.matches)} matches | {len(d.teams)} teams | {len(d.goals)} goals")

    dc = DixonColesModel().fit(d.matches)                    # single tournament -> no time decay
    ratings = PlayerRatings(prior_strength=3.0).fit(d.appearances, d.goals)

    def make(team: str):
        names = ratings.most_used_xi(d.appearances, team)
        pen = max(names, key=lambda nm: ratings.rate(nm, "scoring"))
        return ratings.build_lineup(team, names, pen_taker=pen)

    pred = predict_match(make(home), make(away), dc, neutral=True,
                         n_sims=50_000, rng=np.random.default_rng(0))
    print(pred.summary())


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[0] if len(args) > 0 else "Argentina", args[1] if len(args) > 1 else "France")
