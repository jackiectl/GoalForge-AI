"""Pydantic request/response models for the GoalForge API."""
from __future__ import annotations

from pydantic import BaseModel


class PredictRequest(BaseModel):
    home_team: str
    away_team: str
    home_xi: list[str] | None = None   # default = squad's top 11 by minutes
    away_xi: list[str] | None = None
    neutral: bool = True
    n_sims: int = 50_000


class ScorerProb(BaseModel):
    player: str
    prob: float


class ScoreCell(BaseModel):
    home: int
    away: int
    prob: float


class PredictResponse(BaseModel):
    home_team: str
    away_team: str
    prob_home: float
    prob_draw: float
    prob_away: float
    exp_home_goals: float
    exp_away_goals: float
    most_likely_score: list[int]
    top_scores: list[ScoreCell]
    home_scorers: list[ScorerProb]
    away_scorers: list[ScorerProb]
    home_assisters: list[ScorerProb]
    away_assisters: list[ScorerProb]
