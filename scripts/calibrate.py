"""Step 3 — fix the scoreline model's over-confidence with post-hoc calibration.

Leave-one-tournament-out found the Dixon-Coles forecaster is over-confident (ECE ~0.13). Two
cheap, honest fixes, each with their one parameter fit on the *other* tournaments (never on the
held-out one):

  * temperature  — soften the probabilities: softmax(log p / T),
  * base-shrink  — interpolate toward the base rate: (1-a) p + a * base.

We report leave-one-tournament-out ECE and RPS for raw vs calibrated. Calibration should cut ECE
markedly while barely moving RPS (RPS rewards sharpness, ECE rewards honesty).

    python scripts/calibrate.py            # DC fits on martj42 dominate the runtime
"""
import os

import numpy as np
import pandas as pd

from goalforge.data.international import load_international
from goalforge.evaluation.baselines import base_rates
from goalforge.evaluation.metrics import outcome_index, rps
from goalforge.models.scoreline import DixonColesModel


def ece(probs, ys, bins=10):
    probs, ys = np.asarray(probs), np.asarray(ys)
    conf, pred = probs.max(1), probs.argmax(1)
    correct = (pred == ys).astype(float)
    e = 0.0
    for b in range(bins):
        m = (conf > b / bins) & (conf <= (b + 1) / bins)
        if m.any():
            e += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(e)


def rps_mean(probs, ys):
    return float(np.mean([rps(p, y) for p, y in zip(probs, ys)]))


def temp(probs, t):
    lp = np.log(np.clip(np.asarray(probs), 1e-9, None)) / t
    e = np.exp(lp - lp.max(1, keepdims=True))
    return e / e.sum(1, keepdims=True)


def shrink(probs, a, base):
    return (1 - a) * np.asarray(probs) + a * np.asarray(base)


def _nll(probs, ys):
    p = np.asarray(probs)[np.arange(len(ys)), ys]
    return -np.mean(np.log(np.clip(p, 1e-9, None)))


def main():
    intl = load_international(start_year=2010)
    m2 = intl.matches.copy()
    m2["key"] = (pd.to_datetime(m2.date).dt.strftime("%Y-%m-%d") + "|"
                 + m2[["home_team", "away_team"]].apply(lambda r: "|".join(sorted(r)), axis=1))
    im = pd.read_parquet(os.path.join(os.environ.get("GOALFORGE_DATA_DIR", "data"),
                                      "intl_lineups_matches.parquet"))
    im["dkey"] = (pd.to_datetime(im.date).dt.strftime("%Y-%m-%d") + "|"
                  + im[["home_team", "away_team"]].apply(lambda r: "|".join(sorted(r)), axis=1))
    comps = sorted(im.comp.unique())

    # pass 1: leakage-free raw DC predictions per tournament
    preds = {}
    for comp in comps:
        te = im[im.comp == comp]
        dc = DixonColesModel(l2=0.1).fit(m2[~m2.key.isin(set(te.dkey))], half_life_days=730,
                                         ref_date=pd.to_datetime(te.date).min())
        rows = []
        for _, m in te.iterrows():
            p = dc.predict_proba(m.home_team, m.away_team, neutral=True)
            rows.append(([p["home_win"], p["draw"], p["away_win"]], outcome_index(m.home_goals, m.away_goals)))
        preds[comp] = (np.array([r[0] for r in rows]), np.array([r[1] for r in rows]),
                       base_rates(m2[~m2.key.isin(set(te.dkey))]))

    # pass 2: fit calibration on the OTHER tournaments, apply to the held-out one
    grid_t = np.linspace(0.7, 2.5, 19)
    grid_a = np.linspace(0.0, 0.6, 13)
    out = {"raw": [], "temp": [], "shrink": []}
    n = []
    for comp in comps:
        othp = np.vstack([preds[o][0] for o in comps if o != comp])
        othy = np.concatenate([preds[o][1] for o in comps if o != comp])
        t_best = min(grid_t, key=lambda t: _nll(temp(othp, t), othy))
        base = preds[comp][2]
        a_best = min(grid_a, key=lambda a: _nll(shrink(othp, a, base), othy))
        p, y, _ = preds[comp]
        for name, cal in (("raw", p), ("temp", temp(p, t_best)), ("shrink", shrink(p, a_best, base))):
            out[name].append((cal, y))
        n.append(len(y))

    print(f"leave-one-tournament-out calibration over {comps} (n={sum(n)} matches)\n")
    print(f"  {'method':<9}{'RPS':>9}{'ECE':>9}")
    for name in ("raw", "temp", "shrink"):
        allp = np.vstack([c for c, _ in out[name]])
        ally = np.concatenate([y for _, y in out[name]])
        print(f"  {name:<9}{rps_mean(allp, ally):>9.4f}{ece(allp, ally):>9.3f}")
    print("\n(temperature/shrink should cut ECE a lot while barely changing RPS.)")


if __name__ == "__main__":
    main()
