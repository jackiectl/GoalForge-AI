"""Reproducible synthetic soccer data generator.

Produces a self-contained dataset (matches, appearances, goal events, rosters) so the whole
pipeline runs and is testable offline, without any external data provider. The generative
process mirrors the modelling assumptions: team attack/defence strengths drive Poisson
goals; goals are allocated to players by latent scoring weights; assists by latent creation
weights. Swap this out for :mod:`goalforge.data.statsbomb` to use real data.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .schema import Player

# Per-90 priors by position (goals, assists).
_SCORE_PRIOR = {"GK": 0.001, "DEF": 0.05, "MID": 0.12, "FWD": 0.45}
_ASSIST_PRIOR = {"GK": 0.001, "DEF": 0.06, "MID": 0.15, "FWD": 0.20}
# Squad composition and the starting formation (1 GK, 4 DEF, 3 MID, 3 FWD = 4-3-3).
_SQUAD = ["GK", "GK"] + ["DEF"] * 6 + ["MID"] * 5 + ["FWD"] * 3
_FORMATION = {"GK": 1, "DEF": 4, "MID": 3, "FWD": 3}


@dataclass
class SyntheticData:
    matches: pd.DataFrame       # match_id, date, home_team, away_team, home_goals, away_goals
    appearances: pd.DataFrame   # match_id, team, player, minutes
    goals: pd.DataFrame         # match_id, team, scorer, assister, minute
    teams: list[str]
    rosters: dict[str, list[Player]]   # ground-truth latent rates (for reference/tests)


def _make_roster(team: str, rng: np.random.Generator) -> list[Player]:
    players: list[Player] = []
    for i, pos in enumerate(_SQUAD):
        # gamma(shape=2, scale=prior/2) has mean=prior and stays positive.
        sr = float(rng.gamma(2.0, _SCORE_PRIOR[pos] / 2.0))
        ar = float(rng.gamma(2.0, _ASSIST_PRIOR[pos] / 2.0))
        players.append(Player(f"{team}_P{i + 1:02d}", pos, scoring_rate=sr, assist_rate=ar))
    # Designated penalty taker = highest latent scorer.
    pen = max(range(len(players)), key=lambda k: players[k].scoring_rate)
    players[pen].pen_taker = True
    return players


def _pick_xi(roster: list[Player], rng: np.random.Generator) -> list[Player]:
    by_pos: dict[str, list[Player]] = {}
    for p in roster:
        by_pos.setdefault(p.position, []).append(p)
    xi: list[Player] = []
    for pos, k in _FORMATION.items():
        cands = by_pos.get(pos, [])
        idx = rng.choice(len(cands), size=min(k, len(cands)), replace=False)
        xi += [cands[i] for i in idx]
    return xi


def _weights(xi: list[Player], attr: str) -> np.ndarray:
    w = np.array([max(getattr(p, attr), 0.0) for p in xi], dtype=float)
    return w / w.sum() if w.sum() > 0 else np.ones(len(xi)) / len(xi)


def generate_dataset(
    n_teams: int = 14,
    n_rounds: int = 2,
    start_date: str = "2019-01-01",
    seed: int = 7,
    assisted_rate: float = 0.78,
) -> SyntheticData:
    """Generate a synthetic round-robin competition with player-level goal/assist events."""
    rng = np.random.default_rng(seed)
    teams = [f"T{t:02d}" for t in range(1, n_teams + 1)]
    attack = {t: float(rng.normal(0, 0.35)) for t in teams}
    defence = {t: float(rng.normal(0, 0.35)) for t in teams}   # higher = concedes more
    rosters = {t: _make_roster(t, rng) for t in teams}
    mu, home_adv = 0.1, 0.25

    fixtures = [(h, a) for _ in range(n_rounds) for h in teams for a in teams if h != a]
    rng.shuffle(fixtures)
    dates = pd.date_range(start=start_date, periods=len(fixtures), freq="D")

    m_rows, app_rows, goal_rows = [], [], []
    for mid, ((h, a), date) in enumerate(zip(fixtures, dates)):
        lam_h = np.exp(mu + home_adv + attack[h] + defence[a])
        lam_a = np.exp(mu + attack[a] + defence[h])
        gh, ga = int(rng.poisson(lam_h)), int(rng.poisson(lam_a))
        m_rows.append((mid, date, h, a, gh, ga))

        for team, n_goals in ((h, gh), (a, ga)):
            xi = _pick_xi(rosters[team], rng)
            for p in xi:
                app_rows.append((mid, team, p.name, 90))
            sw, aw = _weights(xi, "scoring_rate"), _weights(xi, "assist_rate")
            for _ in range(n_goals):
                s = int(rng.choice(len(xi), p=sw))
                assister = None
                if rng.random() < assisted_rate:
                    a_w = aw.copy()
                    a_w[s] = 0.0                     # a player cannot assist their own goal
                    if a_w.sum() > 0:
                        assister = xi[int(rng.choice(len(xi), p=a_w / a_w.sum()))].name
                goal_rows.append((mid, team, xi[s].name, assister, int(rng.integers(1, 91))))

    matches = pd.DataFrame(m_rows, columns=["match_id", "date", "home_team", "away_team",
                                            "home_goals", "away_goals"])
    appearances = pd.DataFrame(app_rows, columns=["match_id", "team", "player", "minutes"])
    goals = pd.DataFrame(goal_rows, columns=["match_id", "team", "scorer", "assister", "minute"])
    return SyntheticData(matches, appearances, goals, teams, rosters)
