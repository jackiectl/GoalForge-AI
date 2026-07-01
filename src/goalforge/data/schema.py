"""Lightweight data structures for players and starting lineups.

A ``Player`` carries per-90 scoring/creation rates (goals or npxG per 90, assists or
xA per 90). ``scoring_weight`` / ``assist_weight`` scale those rates by expected minutes
and are what the Monte-Carlo allocation layer consumes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Position buckets used across the project.
POSITIONS = ("GK", "DEF", "MID", "FWD")


@dataclass
class Player:
    name: str
    position: str = "MID"        # one of POSITIONS
    scoring_rate: float = 0.0    # goals (or npxG) per 90
    assist_rate: float = 0.0     # assists (or xA) per 90
    pen_taker: bool = False
    exp_minutes: float = 90.0    # expected minutes on the pitch this match

    @property
    def scoring_weight(self) -> float:
        return max(self.scoring_rate, 0.0) * (self.exp_minutes / 90.0)

    @property
    def assist_weight(self) -> float:
        return max(self.assist_rate, 0.0) * (self.exp_minutes / 90.0)


@dataclass
class Lineup:
    team: str
    players: list[Player] = field(default_factory=list)
    coach: str = ""

    def __len__(self) -> int:
        return len(self.players)

    @property
    def pen_index(self) -> int | None:
        """Index of the designated penalty taker; falls back to top scorer."""
        if not self.players:
            return None
        for i, p in enumerate(self.players):
            if p.pen_taker:
                return i
        return max(range(len(self.players)), key=lambda i: self.players[i].scoring_weight)
