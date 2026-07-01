"""GoalForge inference agent: a saveable bundle of the fitted models.

A ``GoalForgeAgent`` holds the fitted team scoreline model and player ratings and knows how
to predict a match. Train once, ``save()`` a checkpoint to ``models/``, then ``load()`` and
call ``predict()`` for fast inference (no refit). Update by refitting on newer data.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..data.schema import Lineup
from ..models.player import PlayerRatings
from ..models.scoreline import DixonColesModel
from ..simulation.montecarlo import MatchPrediction, simulate_match


@dataclass
class GoalForgeAgent:
    scoreline: DixonColesModel
    ratings: PlayerRatings
    meta: dict = field(default_factory=dict)
    squads: dict = field(default_factory=dict)   # team -> [player names by minutes] for the UI

    def build_lineup(self, team: str, player_names, **kwargs) -> Lineup:
        return self.ratings.build_lineup(team, player_names, **kwargs)

    def predict(self, home: Lineup, away: Lineup, *, neutral: bool = False,
                n_sims: int = 50_000, rng: np.random.Generator | None = None,
                **sim_kwargs) -> MatchPrediction:
        lam_h, lam_a = self.scoreline.expected_goals(home.team, away.team, neutral=neutral)
        return simulate_match(home, away, lam_h, lam_a, n_sims=n_sims, rng=rng, **sim_kwargs)

    def save(self, path: str | Path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        return str(path)

    @staticmethod
    def load(path: str | Path) -> "GoalForgeAgent":
        with open(path, "rb") as f:
            return pickle.load(f)
