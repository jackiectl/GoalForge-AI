"""International match results loader (martj42 dataset, CC0).

Downloads and caches the martj42 "International football results 1872-present" dataset —
~49k men's internationals with scores, venues (neutral flag), tournament, and goal scorers.
It has **no lineups/minutes**, so it feeds the *team-level* scoreline model (and scorer
counts) at scale and across every national team; the *player-level* rates come from
StatsBomb event data instead. Source: https://github.com/martj42/international_results (CC0).
"""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import pandas as pd

from .synthetic import SyntheticData  # reused as a generic (matches, appearances, goals) bundle

BASE = "https://raw.githubusercontent.com/martj42/international_results/master"


def _download(name: str, cache_dir: Path) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw = cache_dir / f"martj42_{name}.csv"
    if not raw.exists():
        urllib.request.urlretrieve(f"{BASE}/{name}.csv", raw)
    return pd.read_csv(raw)


def load_international(cache_dir: str | Path = os.environ.get("GOALFORGE_DATA_DIR", "data/raw"),
                      start_year: int | None = None,
                      tournaments: list[str] | None = None) -> SyntheticData:
    """Load international results into (matches, appearances[empty], goals) frames.

    ``start_year`` keeps only matches from that year on; ``tournaments`` filters by name
    (e.g. ``["FIFA World Cup"]``). Files are cached under ``cache_dir`` (git-ignored).
    """
    cache = Path(cache_dir)
    res = _download("results", cache)
    res = res.dropna(subset=["home_score", "away_score"]).copy()
    res["date"] = pd.to_datetime(res["date"])
    if start_year:
        res = res[res.date.dt.year >= start_year]
    if tournaments:
        res = res[res.tournament.isin(tournaments)]
    res = res.sort_values("date").reset_index(drop=True)
    res["match_id"] = res.index
    res["home_goals"] = res.home_score.astype(int)
    res["away_goals"] = res.away_score.astype(int)
    matches = res[["match_id", "date", "home_team", "away_team",
                   "home_goals", "away_goals", "neutral", "tournament"]].copy()

    gs = _download("goalscorers", cache)
    gs["date"] = pd.to_datetime(gs["date"])
    key = ["date", "home_team", "away_team"]
    goals = gs.merge(matches[key + ["match_id"]], on=key, how="inner")
    goals["assister"] = None  # martj42 has no assist data
    goals = goals[["match_id", "team", "scorer", "assister", "minute"]].dropna(subset=["scorer"])

    appearances = pd.DataFrame(columns=["match_id", "team", "player", "minutes"])  # no lineups
    teams = sorted(set(matches.home_team) | set(matches.away_team))
    return SyntheticData(matches, appearances, goals, teams, rosters={})
