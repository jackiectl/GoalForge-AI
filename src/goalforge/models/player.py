"""Player-level scoring and creation rates with empirical-Bayes shrinkage.

Estimates each player's goals (or npxG) per 90 and assists (or xA) per 90 from appearance
minutes and goal events, shrinking small samples toward the global rate. These rates become
the per-player weights the Monte-Carlo layer allocates goals/assists over. Real xG/xA can be
substituted for raw goal/assist counts without changing the interface.
"""
from __future__ import annotations

import pandas as pd

from ..data.schema import Lineup, Player


class PlayerRatings:
    """Fit per-player per-90 scoring/assist rates; build lineups with those rates."""

    def __init__(self, prior_strength: float = 6.0):
        # prior_strength = equivalent 90s of prior data (shrinkage kappa).
        self.kappa = prior_strength
        self.scoring_: dict[str, float] = {}
        self.assist_: dict[str, float] = {}
        self.minutes_: dict[str, float] = {}
        self.position_: dict[str, str] = {}
        self.global_score_ = self.global_assist_ = 0.0

    def fit(self, appearances: pd.DataFrame, goals: pd.DataFrame, positions: dict | None = None):
        mins = appearances.groupby("player").minutes.sum()
        nineties = (mins / 90.0).clip(lower=1e-6)
        g = goals.groupby("scorer").size().reindex(mins.index).fillna(0.0)
        a = (goals.dropna(subset=["assister"]).groupby("assister").size()
             .reindex(mins.index).fillna(0.0))

        gp = float(g.sum() / nineties.sum())      # global goals per 90
        ap = float(a.sum() / nineties.sum())      # global assists per 90
        # empirical-Bayes shrink: (events + kappa*prior) / (90s + kappa)
        self.scoring_ = ((g + self.kappa * gp) / (nineties + self.kappa)).to_dict()
        self.assist_ = ((a + self.kappa * ap) / (nineties + self.kappa)).to_dict()
        self.minutes_ = mins.to_dict()
        self.global_score_, self.global_assist_ = gp, ap
        self.position_ = dict(positions) if positions else {}
        return self

    def rate(self, player: str, kind: str = "scoring") -> float:
        if kind == "scoring":
            return float(self.scoring_.get(player, self.global_score_))
        return float(self.assist_.get(player, self.global_assist_))

    def build_lineup(self, team: str, player_names, coach: str = "",
                     pen_taker: str | None = None, exp_minutes: dict | None = None) -> Lineup:
        """Construct a Lineup, attaching learned rates to each named player."""
        players = [
            Player(
                name=nm,
                position=self.position_.get(nm, "MID"),
                scoring_rate=self.rate(nm, "scoring"),
                assist_rate=self.rate(nm, "assist"),
                pen_taker=(nm == pen_taker),
                exp_minutes=(exp_minutes or {}).get(nm, 90.0),
            )
            for nm in player_names
        ]
        return Lineup(team=team, players=players, coach=coach)

    def most_used_xi(self, appearances: pd.DataFrame, team: str, n: int = 11) -> list[str]:
        """Pick a team's most-used XI by total minutes (a simple 'likely lineup')."""
        sub = appearances[appearances.team == team]
        return list(sub.groupby("player").minutes.sum().sort_values(ascending=False).head(n).index)
