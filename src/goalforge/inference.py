"""Portable, dependency-light inference — NumPy only (no SciPy / Pandas / pickle).

Loads a model exported by ``scripts/export_model.py`` (a small JSON) and predicts a match by
reusing the Monte-Carlo engine (which is pure NumPy). Used by both the FastAPI backend and the
Vercel serverless function, so predictions are identical and the serverless bundle stays tiny.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .data.schema import Lineup, Player
from .simulation.montecarlo import MatchPrediction, simulate_match


def load_model(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def expected_goals(model: dict, home: str, away: str, neutral: bool = False):
    s = model["score"]
    att, dfc = s["attack"], s["defence"]
    ha = 0.0 if neutral else s["home_adv"]
    lh = math.exp(s["mu"] + ha + att.get(home, 0.0) + dfc.get(away, 0.0))
    la = math.exp(s["mu"] + att.get(away, 0.0) + dfc.get(home, 0.0))
    return lh, la


def rate(model: dict, name: str, kind: str = "scoring") -> float:
    p = model["players"]
    table = p["scoring"] if kind == "scoring" else p["assist"]
    default = p["global_score"] if kind == "scoring" else p["global_assist"]
    return float(table.get(name, default))


def build_lineup(model: dict, team: str, names: list[str]) -> Lineup:
    pen = max(names, key=lambda n: rate(model, n, "scoring")) if names else None
    players = [Player(name=n, scoring_rate=rate(model, n, "scoring"),
                      assist_rate=rate(model, n, "assist"), pen_taker=(n == pen))
               for n in names]
    return Lineup(team=team, players=players)


def predict(model: dict, home: str, away: str, home_xi: list[str] | None = None,
            away_xi: list[str] | None = None, neutral: bool = False,
            n_sims: int = 50_000, seed: int = 0) -> MatchPrediction:
    home_xi = home_xi or model["squads"].get(home, [])[:11]
    away_xi = away_xi or model["squads"].get(away, [])[:11]
    lh, la = expected_goals(model, home, away, neutral)
    return simulate_match(build_lineup(model, home, home_xi), build_lineup(model, away, away_xi),
                          lh, la, n_sims=n_sims, rng=np.random.default_rng(seed))
