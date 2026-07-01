"""Monte-Carlo match simulation: team goals -> individual scorers -> assisters.

Given each team's expected goals and per-player scoring/assist weights, simulate many
matches (vectorized over sims with NumPy) and aggregate into scoreline, outcome, and
per-player anytime-scorer / anytime-assister probabilities. This is the integration layer
that ties the team model and player model together; it is also the natural GPU workload
(swap NumPy for a torch backend to push 1e6+ sims onto CUDA).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..data.schema import Lineup


@dataclass
class MatchPrediction:
    home_team: str
    away_team: str
    n_sims: int
    prob_home: float
    prob_draw: float
    prob_away: float
    exp_home_goals: float
    exp_away_goals: float
    score_matrix: np.ndarray
    top_scores: list                 # [((h, a), prob), ...]
    home_scorers: list               # [(player, anytime_prob), ...] desc
    away_scorers: list
    home_assisters: list
    away_assisters: list

    @property
    def most_likely_score(self):
        return self.top_scores[0][0]

    def summary(self, k: int = 5) -> str:
        (h, a), p = self.top_scores[0]
        lines = [
            f"{self.home_team} vs {self.away_team}  ({self.n_sims:,} sims)",
            f"  outcome:  home {self.prob_home:.0%} | draw {self.prob_draw:.0%} | "
            f"away {self.prob_away:.0%}",
            f"  expected goals:  {self.exp_home_goals:.2f} - {self.exp_away_goals:.2f}",
            f"  most likely score:  {h}-{a}  ({p:.1%})",
            "  top scorelines:  " + ", ".join(f"{i}-{j} {pr:.0%}" for (i, j), pr in self.top_scores[:k]),
            f"  {self.home_team} scorers:  "
            + ", ".join(f"{n} {pr:.0%}" for n, pr in self.home_scorers[:k]),
            f"  {self.away_team} scorers:  "
            + ", ".join(f"{n} {pr:.0%}" for n, pr in self.away_scorers[:k]),
            f"  {self.home_team} assists:  "
            + ", ".join(f"{n} {pr:.0%}" for n, pr in self.home_assisters[:k]),
            f"  {self.away_team} assists:  "
            + ", ".join(f"{n} {pr:.0%}" for n, pr in self.away_assisters[:k]),
        ]
        return "\n".join(lines)


def _normalize(w: np.ndarray) -> np.ndarray:
    s = w.sum()
    return w / s if s > 0 else np.ones(len(w)) / len(w)


def _allocate(counts: np.ndarray, weights: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Distribute per-sim integer counts among players ~ Multinomial(count, weights).

    Vectorized by looping only over the few distinct goal counts (0..~8)."""
    out = np.zeros((len(counts), len(weights)), dtype=np.int64)
    w = _normalize(weights)
    for g in np.unique(counts):
        if g <= 0:
            continue
        mask = counts == g
        out[mask] = rng.multinomial(int(g), w, size=int(mask.sum()))
    return out


def simulate_match(
    home: Lineup,
    away: Lineup,
    lam_home: float,
    lam_away: float,
    *,
    n_sims: int = 50_000,
    rng: np.random.Generator | None = None,
    assisted_rate: float = 0.78,
    pen_fraction: float = 0.10,
    max_goals: int = 10,
) -> MatchPrediction:
    rng = rng if rng is not None else np.random.default_rng()

    gh = rng.poisson(lam_home, n_sims)
    ga = rng.poisson(lam_away, n_sims)

    prob_home = float(np.mean(gh > ga))
    prob_draw = float(np.mean(gh == ga))
    prob_away = float(np.mean(gh < ga))

    K = max_goals
    M = np.zeros((K + 1, K + 1))
    np.add.at(M, (np.clip(gh, 0, K), np.clip(ga, 0, K)), 1.0)
    M /= n_sims
    order = np.argsort(M, axis=None)[::-1][:6]
    top_scores = [((int(i), int(j)), float(M[i, j]))
                  for i, j in (np.unravel_index(o, M.shape) for o in order)]

    def team_alloc(counts, lineup: Lineup):
        sw = np.array([p.scoring_weight for p in lineup.players], dtype=float)
        aw = np.array([p.assist_weight for p in lineup.players], dtype=float)
        pen = lineup.pen_index
        # penalty channel: a fraction of goals are penalties assigned to the taker
        gp = rng.binomial(counts, pen_fraction) if (pen is not None and pen_fraction > 0) \
            else np.zeros_like(counts)
        scorers = _allocate(counts - gp, sw, rng)
        if pen is not None:
            scorers[:, pen] += gp
        assisters = _allocate(rng.binomial(counts, assisted_rate), aw, rng)
        names = [p.name for p in lineup.players]
        scorer_prob = sorted(zip(names, (scorers >= 1).mean(0)), key=lambda t: -t[1])
        assist_prob = sorted(zip(names, (assisters >= 1).mean(0)), key=lambda t: -t[1])
        return [(n, float(p)) for n, p in scorer_prob], [(n, float(p)) for n, p in assist_prob]

    home_sc, home_as = team_alloc(gh, home)
    away_sc, away_as = team_alloc(ga, away)

    return MatchPrediction(
        home_team=home.team, away_team=away.team, n_sims=n_sims,
        prob_home=prob_home, prob_draw=prob_draw, prob_away=prob_away,
        exp_home_goals=float(gh.mean()), exp_away_goals=float(ga.mean()),
        score_matrix=M, top_scores=top_scores,
        home_scorers=home_sc, away_scorers=away_sc,
        home_assisters=home_as, away_assisters=away_as,
    )
