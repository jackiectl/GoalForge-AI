"""Train GoalForge checkpoints with a proper temporal split + honest held-out evaluation.

    python scripts/train.py [--start-year 2010] [--out models/agent_intl.pkl]

Team layer: Dixon-Coles on martj42 international results (broad, generalizes across national
teams; shrinkage l2 chosen on validation). Player layer: PlayerRatings on StatsBomb World Cup
events. Reports test-set RPS/log-loss vs base-rate and Elo baselines, fits the final models
on all data, and saves a GoalForgeAgent checkpoint for inference. See docs/evaluation.md.
"""
import argparse
import os

import numpy as np
import pandas as pd

from goalforge.data.international import load_international
from goalforge.data.statsbomb import WORLD_CUP_2022, load_competition
from goalforge.evaluation.baselines import EloBaseline, base_rates
from goalforge.evaluation.metrics import log_loss, outcome_index, rps
from goalforge.evaluation.split import temporal_split
from goalforge.models.player import PlayerRatings
from goalforge.models.scoreline import DixonColesModel
from goalforge.prediction.agent import GoalForgeAgent

HALF_LIFE = 730  # days; national-team strength drifts, ~2yr half-life


def _eval(forecast_fn, test) -> tuple[float, float]:
    r, ll = [], []
    for _, m in test.iterrows():
        oi = outcome_index(m.home_goals, m.away_goals)
        pv = forecast_fn(m)
        r.append(rps(pv, oi))
        ll.append(log_loss(pv, oi))
    return float(np.mean(r)), float(np.mean(ll))


def _dc_forecaster(model, fallback):
    def fc(m):
        if m.home_team in model.attack_ and m.away_team in model.attack_:
            p = model.predict_proba(m.home_team, m.away_team, neutral=bool(m.get("neutral", False)))
            return [p["home_win"], p["draw"], p["away_win"]]
        return fallback
    return fc


def main():
    ap = argparse.ArgumentParser(description="Train GoalForge checkpoint")
    ap.add_argument("--start-year", type=int, default=2010)
    ap.add_argument("--out", default=os.path.join(
        os.environ.get("GOALFORGE_MODELS_DIR", "models"), "agent_intl.pkl"))
    ap.add_argument("--l2-grid", default="0.03,0.1,0.3,1.0")
    args = ap.parse_args()

    print("[1/5] loading international results (martj42)...")
    d = load_international(start_year=args.start_year)
    train, val, test = temporal_split(d.matches, 0.15, 0.15)
    print(f"   {len(d.matches)} matches, {len(d.teams)} teams | "
          f"split train {len(train)} / val {len(val)} / test {len(test)}")

    print("[2/5] selecting shrinkage l2 on validation...")
    base_tr = base_rates(train)
    grid = [float(x) for x in args.l2_grid.split(",")]
    best = None
    for l2 in grid:
        m = DixonColesModel(l2=l2).fit(train, half_life_days=HALF_LIFE, ref_date=val.date.iloc[0])
        vr, _ = _eval(_dc_forecaster(m, base_tr), val)
        print(f"   l2={l2:<5} val RPS {vr:.4f}")
        if best is None or vr < best[1]:
            best = (l2, vr)
    best_l2 = best[0]
    print(f"   -> best l2 = {best_l2}")

    print("[3/5] held-out TEST evaluation (fit on train+val) vs baselines...")
    trval = pd.concat([train, val])
    dc = DixonColesModel(l2=best_l2).fit(trval, half_life_days=HALF_LIFE, ref_date=test.date.iloc[0])
    elo = EloBaseline().fit(trval)
    base = base_rates(trval)

    def elo_fc(m):
        p = elo.predict_proba(m.home_team, m.away_team, neutral=bool(m.get("neutral", False)))
        return [p["home_win"], p["draw"], p["away_win"]]

    print("   model            RPS      logloss")
    for name, fn in [("GoalForge DC", _dc_forecaster(dc, base)),
                     ("Elo", elo_fc),
                     ("base-rate", lambda m: base)]:
        r, ll = _eval(fn, test)
        print(f"   {name:<15} {r:.4f}   {ll:.4f}")

    print("[4/5] fitting FINAL team model (all data) + player rates (StatsBomb WC2022)...")
    final_dc = DixonColesModel(l2=best_l2).fit(d.matches, half_life_days=HALF_LIFE)
    wc = load_competition(*WORLD_CUP_2022, verbose=False)
    ratings = PlayerRatings(prior_strength=3.0).fit(wc.appearances, wc.goals)

    print("[5/5] saving checkpoint...")
    r_test, ll_test = _eval(_dc_forecaster(dc, base), test)
    meta = {"team_source": "martj42", "start_year": args.start_year,
            "n_matches": int(len(d.matches)), "l2": best_l2,
            "player_source": "statsbomb_wc2022",
            "cutoff": str(d.matches.date.max().date()),
            "test_rps": round(r_test, 4), "test_logloss": round(ll_test, 4)}
    squads = {t: list(wc.appearances[wc.appearances.team == t]
                      .groupby("player").minutes.sum().sort_values(ascending=False).index)
              for t in sorted(wc.appearances.team.unique())}
    agent = GoalForgeAgent(final_dc, ratings, meta, squads=squads)
    path = agent.save(args.out)
    print(f"   saved -> {path}\n   meta = {meta}")

    # sample inference straight from the saved checkpoint
    a = GoalForgeAgent.load(path)

    def xi(team):
        names = ratings.most_used_xi(wc.appearances, team)
        return a.build_lineup(team, names, pen_taker=max(names, key=lambda n: ratings.rate(n, "scoring")))

    print("\n[sample inference from checkpoint]")
    print(a.predict(xi("Argentina"), xi("France"), neutral=True,
                    n_sims=50_000, rng=np.random.default_rng(0)).summary())


if __name__ == "__main__":
    main()
