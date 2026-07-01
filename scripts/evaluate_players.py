"""Step 1 — rigorous player-layer evaluation (leave-one-tournament-out).

The scoreline is a solved problem; GoalForge's real differentiator is the player layer:
given a starting XI, WHO scores / assists? This measures it honestly.

For each of the 6 international tournaments we fit per-player scoring/assist rates on the
OTHER five (leakage-free), then for every match rank each team's starting XI by predicted
scorer (and assister) probability and score it against the actual scorers/assisters:

  * recall@k  — is the real scorer among the team's top-k predicted? (k = 1, 3, 5)
  * log-loss & ECE — is P(player scores) = 1 - e^(-rate) calibrated vs actually scoring?

Methods:
  * uniform   — every XI player equally likely (recall@k -> k/11),
  * position  — a position prior only (FW > MF > DF > GK), no individual info,
  * model     — per-player rate shrunk to a GLOBAL prior (goalforge PlayerRatings),
  * model_pos — per-player rate shrunk to a POSITION prior (position robustness + individual
                signal). The key question: does model_pos beat the plain position baseline?

    python scripts/evaluate_players.py      # needs the 6 tournaments cached (goals+appearances)
"""
import math
import os

import numpy as np
import pandas as pd

from goalforge.data.statsbomb import load_competition
from goalforge.models.player import PlayerRatings

TOURN = [(43, 106, "WC2022"), (43, 3, "WC2018"), (55, 282, "Euro2024"),
         (55, 43, "Euro2020"), (223, 282, "Copa2024"), (1267, 107, "AFCON2023")]
SCORE_PRIOR = {"GK": 0.005, "DF": 0.04, "MF": 0.12, "FW": 0.35}
ASSIST_PRIOR = {"GK": 0.01, "DF": 0.05, "MF": 0.15, "FW": 0.11}
KAPPA = 6.0                       # shrinkage strength (in 90s) toward the position prior
KS = (1, 3, 5)
METHODS = ("uniform", "position", "model", "model_pos")


def _recall_at_k(ranked, actual, ks=KS):
    hits, n = {k: 0 for k in ks}, 0
    for s in actual:
        if s not in ranked:
            continue                       # scorer was a substitute (not in the starting XI)
        n += 1
        for k in ks:
            hits[k] += int(s in ranked[:k])
    return hits, n


def _ece(probs, ys, bins=10):
    probs, ys = np.asarray(probs), np.asarray(ys)
    e = 0.0
    for b in range(bins):
        m = (probs > b / bins) & (probs <= (b + 1) / bins)
        if m.any():
            e += m.mean() * abs(ys[m].mean() - probs[m].mean())
    return float(e)


def _order(d):
    return [p for p, _ in sorted(d.items(), key=lambda kv: -kv[1])]


def _posmap(lineups):
    """player -> most common position (a leakage-free feature, known at prediction time)."""
    return lineups.groupby("player").pos.agg(lambda s: s.mode().iloc[0]).to_dict()


def _load_club(cache):
    """Pooled club goals + appearances (cached by build_club_events), or None if not present."""
    idx = os.path.join(cache, "club_events_index.csv")
    if not os.path.exists(idx):
        return None
    comps = [load_competition(int(r.competition_id), int(r.season_id), verbose=False)
             for _, r in pd.read_csv(idx).iterrows()]
    return pd.concat([c.goals for c in comps]), pd.concat([c.appearances for c in comps])


def main():
    cache = os.environ.get("GOALFORGE_DATA_DIR", "data")
    data = {t[2]: load_competition(t[0], t[1], verbose=False) for t in TOURN}
    lineups = pd.read_parquet(os.path.join(cache, "intl_lineups_players.parquet"))
    posmap = _posmap(lineups)
    club = _load_club(cache)                            # (goals, appearances) pooled club data, or None
    methods = list(METHODS) + (["model_club"] if club else [])
    print(f"methods: {methods}" + (" (club data pooled in)" if club else " (no club data yet)"))

    for kind in ("scoring", "assist"):
        col = "scorer" if kind == "scoring" else "assister"
        prior = SCORE_PRIOR if kind == "scoring" else ASSIST_PRIOR
        cg = club[0][col].value_counts() if club else {}                 # club goals/assists per player
        cn = club[1].groupby("player").minutes.sum() / 90.0 if club else {}
        agg = {m: {k: 0 for k in KS} for m in methods}
        ntot = 0
        cal = {"p": [], "y": []}                        # calibration of model_pos
        for label in data:
            train_app = pd.concat([data[o].appearances for o in data if o != label])
            train_goal = pd.concat([data[o].goals for o in data if o != label])
            pr = PlayerRatings().fit(train_app, train_goal)
            gc = train_goal[col].value_counts()          # intl goals/assists per player (leakage-free)
            nn = train_app.groupby("player").minutes.sum() / 90.0
            d = data[label]
            lu = lineups[lineups.match_id.isin(set(d.matches.match_id))]

            def prate(p, pool_club=False):
                g = gc.get(p, 0) + (cg.get(p, 0) if pool_club else 0)
                n = nn.get(p, 0.0) + (cn.get(p, 0.0) if pool_club else 0.0)
                return (g + KAPPA * prior.get(posmap.get(p, "MF"), 0.08)) / (n + KAPPA)

            for mid in d.matches.match_id:
                row = d.matches.loc[d.matches.match_id == mid, ["home_team", "away_team"]].values[0]
                for team in row:
                    xi = lu[(lu.match_id == mid) & (lu.team == team)]
                    if len(xi) < 7:
                        continue
                    players = list(xi.player)
                    actual = list(d.goals[(d.goals.match_id == mid) & (d.goals.team == team)][col].dropna())
                    posrate = {p: prate(p) for p in players}
                    rankers = {"uniform": players,
                               "position": _order(dict(zip(xi.player, xi.pos.map(lambda z: prior.get(z, 0.08))))),
                               "model": _order({p: pr.rate(p, kind) for p in players}),
                               "model_pos": _order(posrate)}
                    if club:
                        rankers["model_club"] = _order({p: prate(p, pool_club=True) for p in players})
                    for m in methods:
                        hits, n = _recall_at_k(rankers[m], actual)
                        for k in KS:
                            agg[m][k] += hits[k]
                        if m == "model_pos":
                            ntot += n
                    scored = set(actual)
                    for p in players:
                        cal["p"].append(1 - math.exp(-posrate[p]))
                        cal["y"].append(int(p in scored))

        title = "SCORER" if kind == "scoring" else "ASSISTER"
        print(f"\n=== {title} recall@k, leave-one-tournament-out (n={ntot} in-XI events) ===")
        print(f"  {'method':<11}" + "".join(f"   r@{k}" for k in KS))
        for m in methods:
            print(f"  {m:<11}" + "".join(f"  {agg[m][k] / max(ntot, 1):5.1%}" for k in KS))
        ll = -np.mean([y * math.log(max(p, 1e-9)) + (1 - y) * math.log(max(1 - p, 1e-9))
                       for p, y in zip(cal["p"], cal["y"])])
        print(f"  model_pos calibration: log-loss {ll:.3f} | ECE {_ece(cal['p'], cal['y']):.3f} "
              f"| base rate {np.mean(cal['y']):.3f}")


if __name__ == "__main__":
    main()
