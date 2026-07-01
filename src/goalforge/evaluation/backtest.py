"""Walk-forward backtest of the Dixon-Coles model on match outcomes.

Expanding window: for each chronological block, refit on all prior matches and score the
next block's 1X2 forecasts with RPS, comparing against a base-rate baseline. This is the
honest way to judge predictive performance (no look-ahead).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..models.scoreline import DixonColesModel
from .metrics import outcome_index, rps


def _base_rates(train: pd.DataFrame) -> list[float]:
    oi = [outcome_index(h, a) for h, a in zip(train.home_goals, train.away_goals)]
    c = np.bincount(oi, minlength=3).astype(float)
    return list(c / c.sum())


def walk_forward_backtest(matches: pd.DataFrame, n_splits: int = 4,
                          min_train_frac: float = 0.4,
                          half_life_days: float | None = 180) -> dict:
    """Return mean RPS of the model vs a base-rate baseline over expanding-window splits."""
    df = matches.sort_values("date").reset_index(drop=True)
    n = len(df)
    edges = np.linspace(int(n * min_train_frac), n, n_splits + 1, dtype=int)

    model_scores, base_scores = [], []
    for s, e in zip(edges[:-1], edges[1:]):
        train, test = df.iloc[:s], df.iloc[s:e]
        if len(test) == 0:
            continue
        dc = DixonColesModel().fit(train, half_life_days=half_life_days,
                                   ref_date=test.date.iloc[0])
        base = _base_rates(train)
        for _, m in test.iterrows():
            if m.home_team not in dc.attack_ or m.away_team not in dc.attack_:
                continue  # unseen team, skip
            oi = outcome_index(m.home_goals, m.away_goals)
            p = dc.predict_proba(m.home_team, m.away_team)
            model_scores.append(rps([p["home_win"], p["draw"], p["away_win"]], oi))
            base_scores.append(rps(base, oi))

    return {
        "n": len(model_scores),
        "model_rps": float(np.mean(model_scores)) if model_scores else float("nan"),
        "baseline_rps": float(np.mean(base_scores)) if base_scores else float("nan"),
    }
