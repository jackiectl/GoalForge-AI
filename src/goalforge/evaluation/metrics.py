"""Evaluation metrics for match-outcome probabilities.

Outcomes are ordered (home_win, draw, away_win) so the Ranked Probability Score (RPS)
respects the natural ordering of results.
"""
from __future__ import annotations

import numpy as np

OUTCOMES = ("home_win", "draw", "away_win")


def outcome_index(home_goals: int, away_goals: int) -> int:
    """Map a scoreline to an ordered outcome index: 0=home win, 1=draw, 2=away win."""
    if home_goals > away_goals:
        return 0
    if home_goals == away_goals:
        return 1
    return 2


def rps(probs, outcome: int) -> float:
    """Ranked Probability Score for one ordered forecast (lower is better)."""
    p = np.asarray(probs, dtype=float)
    o = np.zeros_like(p)
    o[outcome] = 1.0
    cum = np.cumsum(p) - np.cumsum(o)
    return float(np.sum(cum**2) / (len(p) - 1))


def mean_rps(prob_matrix, outcomes) -> float:
    """Average RPS over many forecasts. prob_matrix: (n, r); outcomes: (n,) indices."""
    prob_matrix = np.asarray(prob_matrix, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    return float(np.mean([rps(prob_matrix[i], outcomes[i]) for i in range(len(outcomes))]))


def log_loss(probs, outcome: int, eps: float = 1e-15) -> float:
    p = np.clip(np.asarray(probs, dtype=float), eps, 1.0)
    return float(-np.log(p[outcome]))


def mean_log_loss(prob_matrix, outcomes, eps: float = 1e-15) -> float:
    prob_matrix = np.asarray(prob_matrix, dtype=float)
    outcomes = np.asarray(outcomes, dtype=int)
    return float(np.mean([log_loss(prob_matrix[i], outcomes[i], eps) for i in range(len(outcomes))]))


def ece(prob_matrix, outcomes, n_bins: int = 10) -> float:
    """Top-label Expected Calibration Error for multiclass forecasts (lower is better)."""
    P = np.asarray(prob_matrix, dtype=float)
    y = np.asarray(outcomes, dtype=int)
    conf = P.max(axis=1)
    correct = (P.argmax(axis=1) == y).astype(float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    n = len(y)
    total = 0.0
    for i in range(n_bins):
        m = (conf > edges[i]) & (conf <= edges[i + 1])
        if m.sum() == 0:
            continue
        total += m.sum() / n * abs(correct[m].mean() - conf[m].mean())
    return float(total)


def brier_score(probs, outcome: int) -> float:
    p = np.asarray(probs, dtype=float)
    o = np.zeros_like(p)
    o[outcome] = 1.0
    return float(np.sum((p - o) ** 2))
