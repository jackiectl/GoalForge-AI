"""Predict a team's most-likely starting XI from recent appearances.

A simple, transparent "likely XI": the players with the most minutes over the team's last few
matches. Used for forward prediction when the confirmed lineup isn't out yet (no free API
provides predicted XIs — see docs/workflow.md). Extend with position/formation constraints
once lineup positions are captured.
"""
from __future__ import annotations

import pandas as pd


def likely_xi(appearances: pd.DataFrame, matches: pd.DataFrame, team: str,
              n: int = 11, recent_matches: int = 6) -> list[str]:
    """Most-used XI over the team's most recent ``recent_matches`` games.

    Falls back to the player's whole history for that team if no recent appearances exist.
    """
    tm = matches[(matches.home_team == team) | (matches.away_team == team)].sort_values("date")
    recent_ids = set(tm.match_id.tail(recent_matches))
    sub = appearances[(appearances.team == team) & (appearances.match_id.isin(recent_ids))]
    if sub.empty:
        sub = appearances[appearances.team == team]
    return list(sub.groupby("player").minutes.sum().sort_values(ascending=False).head(n).index)
