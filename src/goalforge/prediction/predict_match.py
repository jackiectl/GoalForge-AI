"""End-to-end prediction agent: two lineups -> scoreline + scorers + assisters.

Ties the fitted team scoreline model and the Monte-Carlo engine together. Includes a CLI
demo (`python -m goalforge.prediction.predict_match --demo`) that builds a synthetic
dataset, fits the models, and predicts a sample match end-to-end.
"""
from __future__ import annotations

import argparse

import numpy as np

from ..data.schema import Lineup
from ..models.scoreline import DixonColesModel
from ..simulation.montecarlo import MatchPrediction, simulate_match


def predict_match(home: Lineup, away: Lineup, scoreline_model: DixonColesModel, *,
                  neutral: bool = False, n_sims: int = 50_000,
                  rng: np.random.Generator | None = None, **sim_kwargs) -> MatchPrediction:
    """Predict one match from two lineups and a fitted scoreline model."""
    lam_h, lam_a = scoreline_model.expected_goals(home.team, away.team, neutral=neutral)
    return simulate_match(home, away, lam_h, lam_a, n_sims=n_sims, rng=rng, **sim_kwargs)


def _demo(n_sims: int = 50_000, seed: int = 0) -> MatchPrediction:
    """Build synthetic data, fit models, and predict a sample match (used by tests/CLI)."""
    from ..data.synthetic import generate_dataset
    from ..models.player import PlayerRatings

    data = generate_dataset()
    dc = DixonColesModel().fit(data.matches, half_life_days=180)
    positions = {p.name: p.position for roster in data.rosters.values() for p in roster}
    ratings = PlayerRatings().fit(data.appearances, data.goals, positions=positions)

    def make(team: str) -> Lineup:
        names = ratings.most_used_xi(data.appearances, team)
        pen = max(names, key=lambda nm: ratings.rate(nm, "scoring"))
        return ratings.build_lineup(team, names, pen_taker=pen)

    rng = np.random.default_rng(seed)
    return predict_match(make(data.teams[0]), make(data.teams[1]), dc, n_sims=n_sims, rng=rng)


def main(argv=None):
    ap = argparse.ArgumentParser(description="GoalForge match prediction")
    ap.add_argument("--demo", action="store_true", help="run an end-to-end synthetic demo")
    ap.add_argument("--n-sims", type=int, default=50_000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    if args.demo:
        print(_demo(n_sims=args.n_sims, seed=args.seed).summary())
    else:  # lineup-file mode is a later phase; see docs/workflow.md
        ap.print_help()


if __name__ == "__main__":
    main()
