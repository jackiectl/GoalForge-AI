"""Team-layer bake-off: Dixon-Coles vs ML (LightGBM) vs neural nets vs ensembles.

The user's ask: try different methods and ship whichever has the smallest error. This is the
unified harness for the SCORELINE/outcome layer (the model that drives every site prediction):

  * protocol — strict walk-forward: for each major tournament 2014-2024 (WC/Euro/Copa, ~11
    folds), train ONLY on matches dated before its first match, test on the tournament. No
    leave-one-out leakage of later data; every fold is a genuine "predict the future" test.
  * metric  — RPS (primary; rewards ordered W/D/L probabilities), log-loss, ECE.
  * contenders
      base    global W/D/L rates
      elo     Elo baseline
      dc      Dixon-Coles, time-decayed (the deployed model)
      gbm     LightGBM multiclass W/D/L on engineered features (Elo/DC strengths/form/venue)
      gbmp    two LightGBM Poisson goal regressors -> DC-style score grid -> probs
              (the "can ML replace DC as the score engine" test)
      mlp     small neural net on the same features
      ens     50/50 probability blend dc+gbm, plus a walk-forward logistic stack
              (meta-model trained on previous folds' out-of-sample predictions)

    python scripts/team_bakeoff.py            # CPU fine (~minutes); --device cuda optional
"""
import argparse
import math

import numpy as np
import pandas as pd

from goalforge.data.international import load_international
from goalforge.evaluation.baselines import EloBaseline, base_rates
from goalforge.evaluation.metrics import log_loss, outcome_index, rps
from goalforge.models.scoreline import DixonColesModel

FOLDS = [("FIFA World Cup", 2014), ("Copa América", 2015), ("UEFA Euro", 2016),
         ("Copa América", 2016), ("FIFA World Cup", 2018), ("Copa América", 2019),
         ("UEFA Euro", 2021), ("Copa América", 2021), ("FIFA World Cup", 2022),
         ("UEFA Euro", 2024), ("Copa América", 2024)]
KGRID = 10
FORM_N = 10


def outcome_probs(lh, la, rho=0.0, K=KGRID):
    i = np.arange(K + 1)
    fact = np.array([math.factorial(k) for k in i], dtype=float)
    ph, pa = np.exp(-lh) * lh ** i / fact, np.exp(-la) * la ** i / fact
    P = np.outer(ph, pa)
    P[0, 0] *= 1 - lh * la * rho
    P[0, 1] *= 1 + lh * rho
    P[1, 0] *= 1 + la * rho
    P[1, 1] *= 1 - rho
    P = np.clip(P, 1e-12, None)
    P /= P.sum()
    return [float(np.tril(P, -1).sum()), float(np.trace(P)), float(np.triu(P, 1).sum())]


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


# ---- feature engineering (train-history only; frozen during the tournament) -------------------
def _form(hist, team):
    g = hist[(hist.home_team == team) | (hist.away_team == team)].tail(FORM_N)
    if not len(g):
        return 1.3, 1.3, 0.34
    gf = np.where(g.home_team == team, g.home_goals, g.away_goals)
    ga = np.where(g.home_team == team, g.away_goals, g.home_goals)
    return float(gf.mean()), float(ga.mean()), float((gf > ga).mean())


def features(rows, hist, dc, elo):
    X = []
    cache = {}
    for _, m in rows.iterrows():
        f = []
        for t in (m.home_team, m.away_team):
            if t not in cache:
                e = elo.r.get(t, 1500.0)
                att = dc.attack_.get(t, 0.0)
                dfc = dc.defence_.get(t, 0.0)
                cache[t] = (e, att, dfc, *_form(hist, t))
            f.extend(cache[t])
        lh, la = dc.expected_goals(m.home_team, m.away_team, neutral=bool(m.neutral))
        f.extend([f[0] - f[6], lh, la, lh - la, float(not m.neutral)])
        X.append(f)
    return np.array(X, dtype=float)


def _targets(rows):
    return (np.array([outcome_index(m.home_goals, m.away_goals) for _, m in rows.iterrows()]),
            rows.home_goals.to_numpy(float), rows.away_goals.to_numpy(float))


# ---- contenders --------------------------------------------------------------------------------
def fit_gbm(Xtr, ytr, seed=0):
    from lightgbm import LGBMClassifier
    return LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15,
                          min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
                          reg_lambda=1.0, random_state=seed, verbose=-1).fit(Xtr, ytr)


def fit_gbm_poisson(Xtr, gh, ga, seed=0):
    from lightgbm import LGBMRegressor
    kw = dict(objective="poisson", n_estimators=300, learning_rate=0.03, num_leaves=15,
              min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
              reg_lambda=1.0, random_state=seed, verbose=-1)
    return LGBMRegressor(**kw).fit(Xtr, gh), LGBMRegressor(**kw).fit(Xtr, ga)


def fit_mlp(Xtr, ytr, device, seed=0):
    import torch
    import torch.nn as nn
    torch.manual_seed(seed)
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    net = nn.Sequential(nn.Linear(Xtr.shape[1], 32), nn.ReLU(), nn.Dropout(0.3),
                        nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 3)).to(device)
    X = torch.tensor((Xtr - mu) / sd, dtype=torch.float32, device=device)
    y = torch.tensor(ytr, dtype=torch.long, device=device)
    opt = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-3)
    lossf = nn.CrossEntropyLoss()
    for _ in range(300):
        opt.zero_grad()
        lossf(net(X), y).backward()
        opt.step()
    def predict(Xte):
        with torch.no_grad():
            Z = torch.tensor((Xte - mu) / sd, dtype=torch.float32, device=device)
            return torch.softmax(net(Z), 1).cpu().numpy()
    return predict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2000)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()
    intl = load_international(start_year=args.start_year)
    m = intl.matches.copy()
    m["date"] = pd.to_datetime(m.date)

    names = ["base", "elo", "dc", "gbm", "gbmp", "mlp", "ens_avg", "ens_stack"]
    agg = {n: {"rps": 0.0, "ll": 0.0, "n": 0} for n in names}
    meta_X, meta_y = [], []                       # walk-forward stacking memory
    have_stack = False

    print(f"martj42 matches since {args.start_year}: {len(m)}")
    hdr = f"{'fold':<22}{'n':>4} " + "".join(f"{n:>10}" for n in names)
    print("\n" + hdr + "\n" + "-" * len(hdr))

    for comp, year in FOLDS:
        te = m[(m.tournament == comp) & (m.date.dt.year == year)]
        if not len(te):
            print(f"{comp} {year}: no matches, skipped")
            continue
        cutoff = te.date.min()
        tr = m[m.date < cutoff]
        dc = DixonColesModel(l2=0.1).fit(tr, half_life_days=730, ref_date=cutoff)
        elo = EloBaseline().fit(tr)
        base = base_rates(tr)
        rho = float(dc.rho_)

        # feature matrices (train targets on the last 12y to keep regimes comparable)
        tr_recent = tr[tr.date >= cutoff - pd.Timedelta(days=365 * 12)]
        Xtr = features(tr_recent, tr, dc, elo)
        ytr, ghtr, gatr = _targets(tr_recent)
        Xte = features(te, tr, dc, elo)
        yte, _, _ = _targets(te)

        gbm = fit_gbm(Xtr, ytr)
        rh, ra = fit_gbm_poisson(Xtr, ghtr, gatr)
        mlp = fit_mlp(Xtr, ytr, args.device)

        preds = {n: [] for n in names}
        p_gbm = gbm.predict_proba(Xte)
        p_mlp = mlp(Xte)
        lh_p = np.clip(rh.predict(Xte), 0.05, 6.0)
        la_p = np.clip(ra.predict(Xte), 0.05, 6.0)
        for i, (_, row) in enumerate(te.iterrows()):
            lh, la = dc.expected_goals(row.home_team, row.away_team, neutral=bool(row.neutral))
            p_dc = outcome_probs(lh, la, rho)
            pe = elo.predict_proba(row.home_team, row.away_team, neutral=bool(row.neutral))
            p_elo = [pe["home_win"], pe["draw"], pe["away_win"]]
            preds["base"].append(base)
            preds["elo"].append(p_elo)
            preds["dc"].append(p_dc)
            preds["gbm"].append(p_gbm[i].tolist())
            preds["gbmp"].append(outcome_probs(lh_p[i], la_p[i], 0.0))
            preds["mlp"].append(p_mlp[i].tolist())
            preds["ens_avg"].append((0.5 * np.asarray(p_dc) + 0.5 * p_gbm[i]).tolist())

        # walk-forward stack: logistic meta-model on previous folds' out-of-sample preds
        stack_feats = np.hstack([np.asarray(preds["dc"]), np.asarray(preds["gbm"]),
                                 np.asarray(preds["elo"])])
        if have_stack:
            from sklearn.linear_model import LogisticRegression
            meta = LogisticRegression(max_iter=2000, C=1.0).fit(np.vstack(meta_X),
                                                                np.concatenate(meta_y))
            preds["ens_stack"] = meta.predict_proba(stack_feats).tolist()
        else:
            preds["ens_stack"] = preds["ens_avg"]              # cold start: fall back to blend
        meta_X.append(stack_feats)
        meta_y.append(yte)
        have_stack = True

        cells = {}
        for n in names:
            r = float(np.mean([rps(p, y) for p, y in zip(preds[n], yte)]))
            ll = float(np.mean([log_loss(p, y) for p, y in zip(preds[n], yte)]))
            agg[n]["rps"] += r * len(te)
            agg[n]["ll"] += ll * len(te)
            agg[n]["n"] += len(te)
            cells[n] = r
        print(f"{comp[:15] + ' ' + str(year):<22}{len(te):>4} "
              + "".join(f"{cells[n]:>10.4f}" for n in names))

    print("-" * len(hdr))
    order = sorted(names, key=lambda n: agg[n]["rps"] / agg[n]["n"])
    print(f"{'POOLED RPS':<22}{agg['dc']['n']:>4} "
          + "".join(f"{agg[n]['rps'] / agg[n]['n']:>10.4f}" for n in names))
    print(f"{'POOLED log-loss':<22}{'':>4} "
          + "".join(f"{agg[n]['ll'] / agg[n]['n']:>10.4f}" for n in names))
    print("\nranking (pooled RPS, lower better):")
    for i, n in enumerate(order):
        print(f"  {i + 1}. {n:<10} {agg[n]['rps'] / agg[n]['n']:.4f}")
    print("\nnote: ens_stack is cold-start (=ens_avg) on the first fold; later folds use a "
          "logistic stack fit on previous folds' out-of-sample predictions only.")


if __name__ == "__main__":
    main()
