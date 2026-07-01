"""GoalForge FastAPI backend.

Loads a trained ``GoalForgeAgent`` checkpoint and serves predictions. Run with:

    source slurm/env_setup.sh
    python -m uvicorn goalforge.api.app:app --host 127.0.0.1 --port 8000

The frontend in ``web/`` is served at ``/``; the JSON API lives under ``/api``.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..prediction.agent import GoalForgeAgent
from .schemas import PredictRequest, PredictResponse, ScoreCell, ScorerProb

_REPO = Path(__file__).resolve().parents[3]
CHECKPOINT = os.environ.get("GOALFORGE_CHECKPOINT") or str(
    Path(os.environ.get("GOALFORGE_MODELS_DIR", str(_REPO / "models"))) / "agent_intl.pkl")
WEB_DIR = _REPO / "web"

app = FastAPI(title="GoalForge API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_agent: GoalForgeAgent | None = None


def get_agent() -> GoalForgeAgent:
    global _agent
    if _agent is None:
        if not Path(CHECKPOINT).exists():
            raise HTTPException(503, f"checkpoint not found: {CHECKPOINT} — run scripts/train.py")
        _agent = GoalForgeAgent.load(CHECKPOINT)
    return _agent


@app.get("/api/health")
def health():
    return {"status": "ok" if Path(CHECKPOINT).exists() else "no_checkpoint",
            "checkpoint": CHECKPOINT}


@app.get("/api/teams")
def teams():
    a = get_agent()
    return {"teams": sorted(a.squads.keys()), "meta": a.meta}


@app.get("/api/teams/{team}/squad")
def squad(team: str):
    a = get_agent()
    if team not in a.squads:
        raise HTTPException(404, f"unknown team: {team}")
    return {"team": team, "players": a.squads[team], "default_xi": a.squads[team][:11]}


@app.post("/api/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    a = get_agent()
    for t in (req.home_team, req.away_team):
        if t not in a.squads:
            raise HTTPException(404, f"unknown team: {t}")
    if req.home_team == req.away_team:
        raise HTTPException(400, "home_team and away_team must differ")

    home_xi = req.home_xi or a.squads[req.home_team][:11]
    away_xi = req.away_xi or a.squads[req.away_team][:11]
    if not home_xi or not away_xi:
        raise HTTPException(400, "each team needs at least one player")
    hpen = max(home_xi, key=lambda n: a.ratings.rate(n, "scoring"))
    apen = max(away_xi, key=lambda n: a.ratings.rate(n, "scoring"))
    home = a.build_lineup(req.home_team, home_xi, pen_taker=hpen)
    away = a.build_lineup(req.away_team, away_xi, pen_taker=apen)

    n_sims = int(np.clip(req.n_sims, 1_000, 200_000))
    pred = a.predict(home, away, neutral=req.neutral, n_sims=n_sims, rng=np.random.default_rng(0))

    def probs(lst):
        return [ScorerProb(player=n, prob=float(p)) for n, p in lst[:8]]

    return PredictResponse(
        home_team=pred.home_team, away_team=pred.away_team,
        prob_home=pred.prob_home, prob_draw=pred.prob_draw, prob_away=pred.prob_away,
        exp_home_goals=pred.exp_home_goals, exp_away_goals=pred.exp_away_goals,
        most_likely_score=list(pred.most_likely_score),
        top_scores=[ScoreCell(home=h, away=aw, prob=float(p)) for (h, aw), p in pred.top_scores[:6]],
        home_scorers=probs(pred.home_scorers), away_scorers=probs(pred.away_scorers),
        home_assisters=probs(pred.home_assisters), away_assisters=probs(pred.away_assisters),
    )


# Serve the static frontend at "/" (declared after the API routes so /api/* wins).
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
