"""Harder evaluation: leave-one-tournament-out generalization (hold out the 2022 World Cup).

    python scripts/evaluate.py

Trains on all internationals strictly before the 2022 World Cup and evaluates 1X2 forecasts on
the WC2022 matches — a whole tournament the model never saw — versus Elo and base-rate
baselines, reporting RPS, log-loss, and calibration (ECE). See docs/evaluation.md.
"""
import numpy as np
import pandas as pd

from goalforge.data.international import load_international
from goalforge.evaluation.baselines import EloBaseline, base_rates
from goalforge.evaluation.metrics import ece, log_loss, outcome_index, rps
from goalforge.models.scoreline import DixonColesModel


def _dc_probs(dc, row, fallback):
    if row.home_team in dc.attack_ and row.away_team in dc.attack_:
        p = dc.predict_proba(row.home_team, row.away_team, neutral=bool(row.get("neutral", False)))
        return [p["home_win"], p["draw"], p["away_win"]]
    return fallback


def _elo_probs(elo, row):
    p = elo.predict_proba(row.home_team, row.away_team, neutral=bool(row.get("neutral", False)))
    return [p["home_win"], p["draw"], p["away_win"]]


def main():
    d = load_international(start_year=2006)
    m = d.matches
    wc = m[(m.tournament == "FIFA World Cup") & (pd.to_datetime(m.date).dt.year == 2022)]
    if wc.empty:
        print("No WC2022 matches found in the data.")
        return
    cutoff = wc.date.min()
    train = m[m.date < cutoff]
    print(f"leave-one-tournament-out: train {len(train)} matches (< {pd.to_datetime(cutoff).date()}), "
          f"test = {len(wc)} WC2022 matches (unseen tournament)\n")

    dc = DixonColesModel(l2=0.3).fit(train, half_life_days=730, ref_date=cutoff)
    elo = EloBaseline().fit(train)
    base = base_rates(train)

    forecasters = [
        ("GoalForge DC", lambda r: _dc_probs(dc, r, base)),
        ("Elo", lambda r: _elo_probs(elo, r)),
        ("base-rate", lambda r: base),
    ]
    print(f"  {'model':<15} {'RPS':>7} {'logloss':>8} {'ECE':>7}")
    for name, fn in forecasters:
        P = np.array([fn(r) for _, r in wc.iterrows()])
        Y = np.array([outcome_index(r.home_goals, r.away_goals) for _, r in wc.iterrows()])
        r = float(np.mean([rps(P[i], Y[i]) for i in range(len(Y))]))
        ll = float(np.mean([log_loss(P[i], Y[i]) for i in range(len(Y))]))
        print(f"  {name:<15} {r:>7.4f} {ll:>8.4f} {ece(P, Y):>7.4f}")


if __name__ == "__main__":
    main()
