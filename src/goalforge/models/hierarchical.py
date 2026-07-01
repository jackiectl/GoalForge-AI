"""Hierarchical (partial-pooling) Dixon-Coles scoreline model.

Extends :class:`DixonColesModel` with a Gaussian shrinkage prior on team attack/defence
strengths (a ridge penalty = prior precision), whose strength is selected by inner
walk-forward cross-validation. Shrinkage pulls thinly-observed teams toward the league mean
— the key robustness fix for sparse settings like the World Cup (3-7 games/team). Pure
NumPy/SciPy (CPU). For the full Bayesian posterior (uncertainty, GPU via NumPyro) see
:mod:`goalforge.models.bayesian`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..evaluation.metrics import outcome_index, rps
from .scoreline import DixonColesModel


class HierarchicalDixonColes(DixonColesModel):
    """Dixon-Coles whose shrinkage strength ``l2`` (Gaussian prior precision on att/def) is
    chosen by cross-validated RPS via :meth:`fit_cv`."""

    DEFAULT_GRID = (1e-3, 3e-3, 1e-2, 3e-2, 1e-1, 3e-1, 1.0)

    def fit_cv(self, matches: pd.DataFrame, l2_grid=None, cv_splits: int = 3,
               min_train_frac: float = 0.5, half_life_days: float | None = None):
        """Select the pooling strength by inner walk-forward CV, then refit on all matches."""
        grid = tuple(l2_grid) if l2_grid is not None else self.DEFAULT_GRID
        scores = {l2: self._cv_rps(matches, l2, cv_splits, min_train_frac, half_life_days)
                  for l2 in grid}
        self.l2 = min(scores, key=scores.get)
        self.cv_scores_ = scores
        self.cv_l2_ = self.l2
        return self.fit(matches, half_life_days=half_life_days)

    def _cv_rps(self, matches, l2, splits, min_train_frac, half_life_days) -> float:
        df = matches.sort_values("date").reset_index(drop=True)
        n = len(df)
        edges = np.linspace(int(n * min_train_frac), n, splits + 1, dtype=int)
        scores: list[float] = []
        for s, e in zip(edges[:-1], edges[1:]):
            train, test = df.iloc[:s], df.iloc[s:e]
            if len(test) == 0:
                continue
            m = DixonColesModel(max_goals=self.max_goals, l2=l2)
            m.fit(train, half_life_days=half_life_days, ref_date=test.date.iloc[0])
            for _, row in test.iterrows():
                if row.home_team not in m.attack_ or row.away_team not in m.attack_:
                    continue
                p = m.predict_proba(row.home_team, row.away_team)
                scores.append(rps([p["home_win"], p["draw"], p["away_win"]],
                                  outcome_index(row.home_goals, row.away_goals)))
        return float(np.mean(scores)) if scores else float("inf")
