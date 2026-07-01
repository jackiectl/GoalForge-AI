"""Baseline forecasters for honest evaluation: base-rate and Elo.

A model is only "good" if it beats these. Base-rate is the floor; Elo is a strong, simple
rating baseline. (The bookmaker de-vigged odds — the practical ceiling — can be added later
where odds are available.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import outcome_index


def base_rates(train: pd.DataFrame) -> list[float]:
    """Home/draw/away frequencies from the training matches."""
    oi = [outcome_index(h, a) for h, a in zip(train.home_goals, train.away_goals)]
    c = np.bincount(oi, minlength=3).astype(float)
    return list(c / c.sum())


class EloBaseline:
    """Classic Elo with home advantage and an empirical draw rate, mapped to 1X2."""

    def __init__(self, k: float = 20.0, home_adv: float = 60.0, base: float = 1500.0):
        self.k, self.home_adv, self.base = k, home_adv, base
        self.r: dict[str, float] = {}
        self.draw_rate_ = 0.25

    @staticmethod
    def _expected(ra: float, rb: float) -> float:
        return 1.0 / (1.0 + 10 ** (-(ra - rb) / 400.0))

    def fit(self, matches: pd.DataFrame):
        df = matches.sort_values("date")
        draws = 0
        for _, m in df.iterrows():
            ra = self.r.get(m.home_team, self.base)
            rb = self.r.get(m.away_team, self.base)
            adv = 0.0 if bool(m.get("neutral", False)) else self.home_adv
            e = self._expected(ra + adv, rb)
            s = 1.0 if m.home_goals > m.away_goals else (0.5 if m.home_goals == m.away_goals else 0.0)
            self.r[m.home_team] = ra + self.k * (s - e)
            self.r[m.away_team] = rb + self.k * ((1 - s) - (1 - e))
            draws += int(m.home_goals == m.away_goals)
        self.draw_rate_ = float(draws / max(len(df), 1))
        return self

    def predict_proba(self, home: str, away: str, neutral: bool = False) -> dict:
        ra = self.r.get(home, self.base)
        rb = self.r.get(away, self.base)
        adv = 0.0 if neutral else self.home_adv
        e = self._expected(ra + adv, rb)
        d = self.draw_rate_
        return {"home_win": (1 - d) * e, "draw": d, "away_win": (1 - d) * (1 - e)}
