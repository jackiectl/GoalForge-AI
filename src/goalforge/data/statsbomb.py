"""Optional StatsBomb open-data loader (real-data path).

Wraps ``statsbombpy`` to produce the same (matches, appearances, goals) frames the pipeline
expects (see :class:`goalforge.data.synthetic.SyntheticData`, reused as a generic bundle).
``statsbombpy`` is an optional dependency: ``pip install statsbombpy``. The free open data
covers FIFA World Cups (1958-2022), Euros, Champions League, and more — non-commercial use
with StatsBomb attribution.
"""
from __future__ import annotations

import pandas as pd

from .synthetic import SyntheticData  # reused as a generic (matches, appearances, goals) bundle

# Common competition/season ids in StatsBomb open data.
WORLD_CUP_2022 = (43, 106)
WORLD_CUP_2018 = (43, 3)
EURO_2024 = (55, 282)


def _require_sb():
    try:
        from statsbombpy import sb
        return sb
    except ImportError as e:  # pragma: no cover
        raise ImportError("statsbombpy not installed; run `pip install statsbombpy`.") from e


def _parse_clock(s) -> float | None:
    if not isinstance(s, str) or ":" not in s:
        return None
    mm, ss = s.split(":")[:2]
    return int(mm) + int(ss) / 60.0


def _minutes(positions) -> float:
    """Sum a player's on-pitch minutes from StatsBomb lineup position spells."""
    if not isinstance(positions, list):
        return 0.0
    total = 0.0
    for spell in positions:
        f = _parse_clock(spell.get("from"))
        if f is None:
            continue
        t = _parse_clock(spell.get("to"))
        total += max(0.0, (t if t is not None else 95.0) - f)  # None 'to' = played to the end
    return total


def load_competition(competition_id: int, season_id: int, max_matches: int | None = None,
                     verbose: bool = True) -> SyntheticData:
    """Load a StatsBomb competition-season into (matches, appearances, goals) frames."""
    sb = _require_sb()
    fixtures = sb.matches(competition_id=competition_id, season_id=season_id).sort_values("match_date")
    if max_matches:
        fixtures = fixtures.head(max_matches)
    matches = fixtures.rename(columns={
        "match_date": "date", "home_score": "home_goals", "away_score": "away_goals",
    })[["match_id", "date", "home_team", "away_team", "home_goals", "away_goals"]].copy()

    app_rows, goal_rows = [], []
    for mid in matches.match_id:
        mid = int(mid)
        try:
            ev = sb.events(match_id=mid)
            lu = sb.lineups(match_id=mid)
        except Exception as e:  # network / parse hiccup on one match -> skip
            if verbose:
                print(f"  skip match {mid}: {e}")
            continue

        # goals + assists from shot events
        assist_map = {}
        if {"pass_goal_assist", "pass_assisted_shot_id"} <= set(ev.columns):
            ap = ev[ev["pass_goal_assist"] == True]  # noqa: E712
            assist_map = dict(zip(ap["pass_assisted_shot_id"], ap["player"]))
        shots = ev[ev["type"] == "Shot"] if "type" in ev.columns else ev.iloc[0:0]
        if "shot_outcome" in shots.columns:
            for _, s in shots[shots["shot_outcome"] == "Goal"].iterrows():
                goal_rows.append((mid, s["team"], s["player"],
                                  assist_map.get(s["id"]), int(s["minute"])))

        # appearances (minutes from lineup position spells)
        for team, df in lu.items():
            for _, r in df.iterrows():
                mins = _minutes(r.get("positions"))
                if mins > 0:
                    app_rows.append((mid, team, r["player_name"], mins))

    appearances = pd.DataFrame(app_rows, columns=["match_id", "team", "player", "minutes"])
    goals = pd.DataFrame(goal_rows, columns=["match_id", "team", "scorer", "assister", "minute"])
    teams = sorted(set(matches.home_team) | set(matches.away_team))
    return SyntheticData(matches.reset_index(drop=True), appearances, goals, teams, rosters={})
