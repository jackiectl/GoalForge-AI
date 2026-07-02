"""Ship the bake-off winner: add the DC+GBM ensemble outcome layer to api/model.json.

scripts/team_bakeoff.py showed (walk-forward over 11 major tournaments, 489 matches) that a
50/50 probability blend of Dixon-Coles and a LightGBM outcome classifier has the lowest error
(RPS 0.1980 vs DC-alone 0.2000; best log-loss too). The GBM's features are team-level only
(Elo, DC strengths, recent form, venue) — they do not depend on the XI — so the deployed
stdlib-only API can use the winner exactly by looking up a precomputed table:

  for every ordered pair of the 48 teams x {neutral, home-advantage}: the GBM's [pW,pD,pL]
  -> api/model.json["ens"] = {"w": 0.5, "probs": {"home|away|neutral01": [pW,pD,pL], ...}}

api/_engine.py then blends: p = w * p_DC + (1-w) * p_GBM (renormalised). Score matrices and
scorer/assist attribution stay Dixon-Coles (the GBM has no score distribution; its Poisson
variant LOST the bake-off). Run on a compute node:  sbatch slurm/build_ens.sbatch

The production GBM is fit exactly like the bake-off contender, on all matches to date.
"""
import json
import os
import pickle
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_bakeoff import features, fit_gbm, _targets  # noqa: E402

from goalforge.data.international import load_international  # noqa: E402
from goalforge.evaluation.baselines import EloBaseline  # noqa: E402

ENS_W = 0.5           # DC weight in the blend (bake-off used 50/50)
START_YEAR = 2000
TRAIN_WINDOW_Y = 12   # GBM targets drawn from the last N years (same as the bake-off)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default=None,
                    help="drop matches on/after this date (keep the ens layer pre-tournament)")
    args = ap.parse_args()

    M = json.load(open("api/model.json"))
    teams = sorted(M["squads"])
    dc = pickle.load(open("models/agent_intl.pkl", "rb")).scoreline   # GoalForgeAgent dataclass

    intl = load_international(start_year=START_YEAR)
    hist = intl.matches.copy()
    hist["date"] = pd.to_datetime(hist.date)
    if args.cutoff:
        hist = hist[hist.date < pd.to_datetime(args.cutoff)].reset_index(drop=True)
    now = hist.date.max()
    tr = hist[hist.date >= now - pd.Timedelta(days=365 * TRAIN_WINDOW_Y)]
    elo = EloBaseline().fit(hist)

    print(f"history {len(hist)} matches (to {now.date()}), GBM train {len(tr)}")
    Xtr = features(tr, hist, dc, elo)
    ytr, _, _ = _targets(tr)
    gbm = fit_gbm(Xtr, ytr)

    pairs = [dict(match_id=i, home_team=h, away_team=a, neutral=neu,
                  home_goals=0, away_goals=0, date=now)
             for i, (h, a, neu) in enumerate((h, a, neu) for h in teams for a in teams
                                             if h != a for neu in (True, False))]
    rows = pd.DataFrame(pairs)
    P = gbm.predict_proba(features(rows, hist, dc, elo))
    probs = {f"{r.home_team}|{r.away_team}|{int(not r.neutral)}":
             [round(float(x), 4) for x in P[i]] for i, r in enumerate(rows.itertuples())}

    M["ens"] = {"w": ENS_W, "probs": probs, "cutoff": args.cutoff or str(now.date()),
                "note": "LightGBM outcome probs (team-level features); blended with DC "
                        "per team_bakeoff.py (walk-forward RPS 0.1980 vs 0.2000 DC-alone)"}
    M["meta"]["method"]["scoreline"] = (
        "Dixon-Coles (time-decayed, low-score corrected) blended 50/50 with a gradient-boosting "
        "outcome model for win/draw/loss — the lowest-error combo in a walk-forward bake-off "
        "over 11 major tournaments. Scorelines & player attribution stay Dixon-Coles.")
    json.dump(M, open("api/model.json", "w"), ensure_ascii=False)
    print(f"ens table: {len(probs)} entries | model.json -> "
          f"{os.path.getsize('api/model.json') / 1024:.0f} KB")


if __name__ == "__main__":
    main()
