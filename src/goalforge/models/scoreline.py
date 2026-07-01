"""Team-level Dixon-Coles scoreline model.

Fits attack/defence strengths, home advantage, and the low-score dependence parameter rho
by (optionally time-decayed) maximum likelihood, then produces expected goals and a full
scoreline probability matrix. Pure NumPy/SciPy — CPU, sub-second for a season.
Reference: Dixon & Coles (1997), "Modelling Association Football Scores".
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson


def _tau(x, y, lh, la, rho):
    """Dixon-Coles low-score correction, vectorized over matches."""
    t = np.ones_like(lh, dtype=float)
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    t[m00] = 1.0 - lh[m00] * la[m00] * rho
    t[m01] = 1.0 + lh[m01] * rho
    t[m10] = 1.0 + la[m10] * rho
    t[m11] = 1.0 - rho
    return t


class DixonColesModel:
    """Dixon-Coles goals model. Call :meth:`fit` then :meth:`expected_goals` /
    :meth:`score_matrix` / :meth:`predict_proba`."""

    def __init__(self, max_goals: int = 10, l2: float = 1e-4):
        self.max_goals = max_goals
        self.l2 = l2                      # tiny ridge on strengths for stability
        self.teams_: list[str] | None = None
        self.attack_: dict[str, float] | None = None
        self.defence_: dict[str, float] | None = None
        self.home_adv_ = self.rho_ = self.mu_ = None

    def fit(self, matches: pd.DataFrame, half_life_days: float | None = None, ref_date=None):
        teams = sorted(set(matches.home_team) | set(matches.away_team))
        idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        hi = matches.home_team.map(idx).to_numpy()
        ai = matches.away_team.map(idx).to_numpy()
        x = matches.home_goals.to_numpy()
        y = matches.away_goals.to_numpy()

        if half_life_days:  # exponential time decay: recent matches weigh more
            ref = pd.to_datetime(ref_date) if ref_date is not None else pd.to_datetime(matches.date).max()
            age = (ref - pd.to_datetime(matches.date)).dt.days.to_numpy().astype(float)
            w = np.exp(-(np.log(2) / half_life_days) * np.clip(age, 0, None))
        else:
            w = np.ones(len(matches))

        def unpack(theta):
            mu, home, rho = theta[0], theta[1], theta[2]
            att = theta[3:3 + n]
            deff = theta[3 + n:3 + 2 * n]
            return mu, home, rho, att - att.mean(), deff - deff.mean()  # sum-to-zero

        def negll(theta):
            mu, home, rho, att, deff = unpack(theta)
            lh = np.exp(mu + home + att[hi] + deff[ai])
            la = np.exp(mu + att[ai] + deff[hi])
            t = np.clip(_tau(x, y, lh, la, rho), 1e-10, None)
            ll = poisson.logpmf(x, lh) + poisson.logpmf(y, la) + np.log(t)
            return -np.sum(w * ll) + self.l2 * (np.sum(att**2) + np.sum(deff**2))

        theta0 = np.concatenate([[0.0, 0.2, -0.05], np.zeros(2 * n)])
        bounds = [(None, None), (None, None), (-0.2, 0.2)] + [(None, None)] * (2 * n)
        res = minimize(negll, theta0, method="L-BFGS-B", bounds=bounds)
        mu, home, rho, att, deff = unpack(res.x)
        self.teams_, self.mu_, self.home_adv_, self.rho_ = teams, float(mu), float(home), float(rho)
        self.attack_ = dict(zip(teams, att))
        self.defence_ = dict(zip(teams, deff))
        self.result_ = res
        return self

    def expected_goals(self, home: str, away: str, neutral: bool = False):
        """Return (lambda_home, lambda_away). Set neutral=True to drop home advantage."""
        a, d = self.attack_, self.defence_
        ha = 0.0 if neutral else self.home_adv_
        lh = np.exp(self.mu_ + ha + a.get(home, 0.0) + d.get(away, 0.0))
        la = np.exp(self.mu_ + a.get(away, 0.0) + d.get(home, 0.0))
        return float(lh), float(la)

    def score_matrix(self, home: str, away: str, neutral: bool = False) -> np.ndarray:
        lh, la = self.expected_goals(home, away, neutral)
        k = np.arange(self.max_goals + 1)
        M = np.outer(poisson.pmf(k, lh), poisson.pmf(k, la))
        rho = self.rho_
        M[0, 0] *= 1 - lh * la * rho
        M[0, 1] *= 1 + lh * rho
        M[1, 0] *= 1 + la * rho
        M[1, 1] *= 1 - rho
        M = np.clip(M, 0, None)
        return M / M.sum()

    def predict_proba(self, home: str, away: str, neutral: bool = False) -> dict:
        M = self.score_matrix(home, away, neutral)
        return {"home_win": float(np.tril(M, -1).sum()),
                "draw": float(np.trace(M)),
                "away_win": float(np.triu(M, 1).sum())}
