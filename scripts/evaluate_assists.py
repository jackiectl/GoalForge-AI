"""Step 2 — does chance-creation (xA / key passes) rank assisters better than sparse assists?

Assists are rare (~0.05 per player-match), so an actual-assist rate is noisy. Expected assists
(xA) grade every key pass by the xG it creates — a ~10x denser signal that captures the passing
structure ("who creates chances"). Same leave-one-tournament-out protocol as evaluate_players.py,
assist task only, comparing:

  * position   — position prior only,
  * model_pos  — actual-assist rate, shrunk to position (the Step-1 winner),
  * model_xa   — xA/90 (chance creation), shrunk to position,
  * *_club      — the same, pooling club-league data (if cached).

    python scripts/build_creation_stats.py --club       # first: cache key-pass/xA stats
    python scripts/evaluate_assists.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evaluate_players import ASSIST_PRIOR, KAPPA, KS, TOURN, _order, _recall_at_k  # noqa: E402

from goalforge.data.statsbomb import load_competition  # noqa: E402


def _rate(counts, nineties, player, pos, prior, extra_c=0.0, extra_n=0.0):
    return ((counts.get(player, 0) + extra_c + KAPPA * prior.get(pos, 0.08))
            / (nineties.get(player, 0.0) + extra_n + KAPPA))


def main():
    cache = os.environ.get("GOALFORGE_DATA_DIR", "data")
    data = {t[2]: load_competition(t[0], t[1], verbose=False) for t in TOURN}
    lineups = pd.read_parquet(os.path.join(cache, "intl_lineups_players.parquet"))

    # per-tournament creation (key passes + xA); required — run build_creation_stats.py first
    crea = {}
    for cid, sid, label in TOURN:
        p = os.path.join(cache, f"creation_{cid}_{sid}.parquet")
        if not os.path.exists(p):
            print(f"missing {p} — run: python scripts/build_creation_stats.py --club")
            return
        crea[label] = pd.read_parquet(p)

    # optional pooled club data (goals for assists, creation for xA, appearances for minutes)
    club_idx = os.path.join(cache, "club_events_index.csv")
    club = None
    if os.path.exists(club_idx):
        seas = pd.read_csv(club_idx)
        cg = pd.concat([load_competition(int(r.competition_id), int(r.season_id), verbose=False).goals
                        for _, r in seas.iterrows()])
        capp = pd.concat([load_competition(int(r.competition_id), int(r.season_id), verbose=False).appearances
                          for _, r in seas.iterrows()])
        ccrea = pd.concat([pd.read_parquet(os.path.join(cache, f"creation_{int(r.competition_id)}_{int(r.season_id)}.parquet"))
                           for _, r in seas.iterrows()
                           if os.path.exists(os.path.join(cache, f"creation_{int(r.competition_id)}_{int(r.season_id)}.parquet"))])
        club = {"assist": cg.assister.value_counts(), "xa": ccrea.groupby("player").xa.sum(),
                "n": capp.groupby("player").minutes.sum() / 90.0}

    methods = ["position", "model_pos", "model_xa"] + (["model_pos_club", "model_xa_club"] if club else [])
    agg = {m: {k: 0 for k in KS} for m in methods}
    ntot = 0
    print(f"methods: {methods}\n")
    for label in data:
        assist_c = pd.concat([data[o].goals for o in data if o != label]).assister.value_counts()
        nineties = pd.concat([data[o].appearances for o in data if o != label]).groupby("player").minutes.sum() / 90.0
        xa_c = pd.concat([crea[o] for o in crea if o != label]).groupby("player").xa.sum()
        d = data[label]
        lu = lineups[lineups.match_id.isin(set(d.matches.match_id))]
        for mid in d.matches.match_id:
            for team in d.matches.loc[d.matches.match_id == mid, ["home_team", "away_team"]].values[0]:
                xi = lu[(lu.match_id == mid) & (lu.team == team)]
                if len(xi) < 7:
                    continue
                pos = dict(zip(xi.player, xi.pos))
                actual = list(d.goals[(d.goals.match_id == mid) & (d.goals.team == team)].assister.dropna())
                rank = {
                    "position": _order({p: ASSIST_PRIOR.get(pos[p], 0.08) for p in xi.player}),
                    "model_pos": _order({p: _rate(assist_c, nineties, p, pos[p], ASSIST_PRIOR) for p in xi.player}),
                    "model_xa": _order({p: _rate(xa_c, nineties, p, pos[p], ASSIST_PRIOR) for p in xi.player}),
                }
                if club:
                    rank["model_pos_club"] = _order({p: _rate(assist_c, nineties, p, pos[p], ASSIST_PRIOR,
                                                              club["assist"].get(p, 0), club["n"].get(p, 0.0)) for p in xi.player})
                    rank["model_xa_club"] = _order({p: _rate(xa_c, nineties, p, pos[p], ASSIST_PRIOR,
                                                             club["xa"].get(p, 0.0), club["n"].get(p, 0.0)) for p in xi.player})
                for m in methods:
                    hits, n = _recall_at_k(rank[m], actual)
                    for k in KS:
                        agg[m][k] += hits[k]
                    if m == "model_xa":
                        ntot += n

    print(f"=== ASSISTER recall@k, leave-one-tournament-out (n={ntot} in-XI assists) ===")
    print(f"  {'method':<15}" + "".join(f"   r@{k}" for k in KS))
    for m in methods:
        print(f"  {m:<15}" + "".join(f"  {agg[m][k] / max(ntot, 1):5.1%}" for k in KS))
    print("\n(does model_xa beat model_pos? i.e. does dense chance-creation rank assisters better?)")


if __name__ == "__main__":
    main()
