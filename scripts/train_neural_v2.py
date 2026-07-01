"""Phase 3 follow-up (1): a STRONG team prior + lineup deltas — does the XI add anything now?

The weak part of the first neural test was that every model was trained on only ~314
tournament matches. Here the team baseline is Dixon-Coles fit on martj42 international results
(~16k matches) with the held-out tournament's OWN games removed (no leakage), giving strong,
well-generalizing team strengths. On top of that FIXED baseline we learn per-player
attack/defence deltas from the other tournaments' starting XIs:

    log lambda_home = log lambda_DC(home, away) + mean_XI(delta_att_home) - mean_XI(delta_def_away)

Leave-one-tournament-out. Compares DC-prior-only vs DC-prior + lineup deltas vs Elo vs base.
Question: once you already have a good team model, do the actual XIs help? Honest either way.

    python scripts/train_neural_v2.py           # CPU ok (DC fits dominate); --device cuda on a GPU
"""
import argparse
import math
import os

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from goalforge.data.international import load_international
from goalforge.evaluation.baselines import EloBaseline, base_rates
from goalforge.evaluation.metrics import log_loss, outcome_index, rps
from goalforge.models.scoreline import DixonColesModel

POS = {"GK": 0, "DF": 1, "MF": 2, "FW": 3}
MAXP, KGRID = 11, 10
L2_PLAYER, L2_POS = 1.5, 0.05           # deltas are strongly shrunk (a priori)
EPOCHS, LR = 400, 0.05


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


def outcome_probs(lh, la, rho, K=KGRID):
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


class LineupDelta(nn.Module):
    """Per-player attack/defence deltas on top of a fixed Dixon-Coles log-lambda offset."""

    def __init__(self, n_players):
        super().__init__()
        self.p_att = nn.Embedding(n_players + 1, 1, padding_idx=0)
        self.p_def = nn.Embedding(n_players + 1, 1, padding_idx=0)
        self.pos_att = nn.Embedding(4, 1)
        self.pos_def = nn.Embedding(4, 1)
        for e in (self.p_att, self.p_def, self.pos_att, self.pos_def):
            nn.init.zeros_(e.weight)

    def _delta(self, pidx, ppos, mask):
        a = ((self.p_att(pidx).squeeze(-1) + self.pos_att(ppos).squeeze(-1)) * mask).sum(1)
        d = ((self.p_def(pidx).squeeze(-1) + self.pos_def(ppos).squeeze(-1)) * mask).sum(1)
        n = mask.sum(1).clamp(min=1)
        return a / n, d / n

    def forward(self, b):
        ah, dh = self._delta(b["hp"], b["hpos"], b["hmask"])
        aa, da = self._delta(b["ap"], b["apos"], b["amask"])
        log_lh = (b["dc_lh"] + ah - da).clamp(-2.0, 2.5)
        log_la = (b["dc_la"] + aa - dh).clamp(-2.0, 2.5)
        return log_lh, log_la

    def l2(self):
        return (L2_PLAYER * (self.p_att.weight.pow(2).sum() + self.p_def.weight.pow(2).sum())
                + L2_POS * (self.pos_att.weight.pow(2).sum() + self.pos_def.weight.pow(2).sum()))


def _batch(rows, lineups, dc, pvoc, device):
    n = len(rows)
    hp = torch.zeros(n, MAXP, dtype=torch.long)
    ap = torch.zeros(n, MAXP, dtype=torch.long)
    hpos = torch.zeros(n, MAXP, dtype=torch.long)
    apos = torch.zeros(n, MAXP, dtype=torch.long)
    hmask = torch.zeros(n, MAXP)
    amask = torch.zeros(n, MAXP)
    yh = torch.zeros(n)
    ya = torch.zeros(n)
    dc_lh = torch.zeros(n)
    dc_la = torch.zeros(n)
    for i, (_, m) in enumerate(rows.iterrows()):
        lh, la = dc.expected_goals(m.home_team, m.away_team, neutral=True)
        dc_lh[i], dc_la[i] = math.log(lh), math.log(la)
        yh[i], ya[i] = m.home_goals, m.away_goals
        for pidx, ppos, mask, home in ((hp, hpos, hmask, 1), (ap, apos, amask, 0)):
            for k, (pl, pos) in enumerate(lineups.get((m.match_id, home), [])[:MAXP]):
                pidx[i, k] = pvoc.get(pl, 0)
                ppos[i, k] = POS[pos]
                mask[i, k] = 1.0
    d = {"hp": hp, "ap": ap, "hpos": hpos, "apos": apos, "hmask": hmask, "amask": amask,
         "yh": yh, "ya": ya, "dc_lh": dc_lh, "dc_la": dc_la}
    return {k: v.to(device) for k, v in d.items()}


def _fit(train, lineups, dc, pvoc, device, seed=0):
    torch.manual_seed(seed)
    model = LineupDelta(len(pvoc)).to(device)
    b = _batch(train, lineups, dc, pvoc, device)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    for _ in range(EPOCHS):
        opt.zero_grad()
        log_lh, log_la = model(b)
        nll = (log_lh.exp() - b["yh"] * log_lh).mean() + (log_la.exp() - b["ya"] * log_la).mean()
        (nll + model.l2() / len(train)).backward()
        opt.step()
    return model


def _metrics(preds, rows):
    ys = [outcome_index(m.home_goals, m.away_goals) for _, m in rows.iterrows()]
    return (float(np.mean([rps(p, y) for p, y in zip(preds, ys)])),
            float(np.mean([log_loss(p, y) for p, y in zip(preds, ys)])), ece(preds, ys))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("GOALFORGE_DATA_DIR", "data"))
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--start-year", type=int, default=2010)
    args = ap.parse_args()
    print(f"device={args.device} | torch={torch.__version__} | cuda={torch.cuda.is_available()}")

    intl = load_international(start_year=args.start_year)
    m2 = intl.matches.copy()
    m2["key"] = (pd.to_datetime(m2.date).dt.strftime("%Y-%m-%d") + "|"
                 + m2[["home_team", "away_team"]].apply(lambda r: "|".join(sorted(r)), axis=1))

    matches = pd.read_parquet(os.path.join(args.cache, "intl_lineups_matches.parquet"))
    players = pd.read_parquet(os.path.join(args.cache, "intl_lineups_players.parquet"))
    matches["dkey"] = (pd.to_datetime(matches.date).dt.strftime("%Y-%m-%d") + "|"
                       + matches[["home_team", "away_team"]].apply(lambda r: "|".join(sorted(r)), axis=1))
    lineups = {(mid, h): list(zip(g.player, g.pos))
               for (mid, h), g in players.groupby(["match_id", "is_home"])}
    pvoc = {p: i + 1 for i, p in enumerate(sorted(players.player.unique()))}
    comps = sorted(matches.comp.unique())

    agg = {n: {"rps": [], "ll": [], "ece": [], "n": []} for n in ("DC+lineup", "DC-prior", "Elo", "Base")}
    print(f"\nleave-one-tournament-out over {comps} | martj42 base = {len(m2)} matches\n")
    print(f"{'held-out':<11}{'n':>4}   {'DC+lineup':>16}{'DC-prior':>16}{'Elo':>10}{'Base':>8}")
    for comp in comps:
        te = matches[matches.comp == comp]
        tr = matches[matches.comp != comp]
        leak = set(te.dkey)
        base_matches = m2[~m2.key.isin(leak)]                 # martj42 minus the held-out tournament
        dc = DixonColesModel(l2=0.1).fit(base_matches, half_life_days=730,
                                         ref_date=pd.to_datetime(te.date).min())
        elo = EloBaseline().fit(base_matches)
        base = base_rates(base_matches)

        model = _fit(tr, lineups, dc, pvoc, args.device)
        b = _batch(te, lineups, dc, pvoc, args.device)
        with torch.no_grad():
            log_lh, log_la = model(b)
        lh, la = log_lh.exp().cpu().numpy(), log_la.exp().cpu().numpy()
        rho = float(dc.rho_)
        preds_lineup, preds_dc, preds_elo, preds_base = [], [], [], []
        for i, (_, m) in enumerate(te.iterrows()):
            preds_lineup.append(outcome_probs(lh[i], la[i], rho))
            dh, da = dc.expected_goals(m.home_team, m.away_team, neutral=True)
            preds_dc.append(outcome_probs(dh, da, rho))
            pe = elo.predict_proba(m.home_team, m.away_team, neutral=True)
            preds_elo.append([pe["home_win"], pe["draw"], pe["away_win"]])
            preds_base.append(base)

        cells = {}
        for name, preds in (("DC+lineup", preds_lineup), ("DC-prior", preds_dc),
                            ("Elo", preds_elo), ("Base", preds_base)):
            r, ll, e = _metrics(preds, te)
            agg[name]["rps"].append(r * len(te))
            agg[name]["ll"].append(ll * len(te))
            agg[name]["ece"].append(e * len(te))
            agg[name]["n"].append(len(te))
            cells[name] = (r, ll, e)
        print(f"{comp:<11}{len(te):>4}   {cells['DC+lineup'][0]:.4f}/{cells['DC+lineup'][1]:.3f}  "
              f"{cells['DC-prior'][0]:.4f}/{cells['DC-prior'][1]:.3f}  "
              f"{cells['Elo'][0]:.4f}  {cells['Base'][0]:.4f}")

    print("\n=== weighted overall (RPS / logloss / ECE) ===")
    for name in ("DC+lineup", "DC-prior", "Elo", "Base"):
        N = sum(agg[name]["n"])
        r = sum(agg[name]["rps"]) / N
        ll = sum(agg[name]["ll"]) / N
        e = sum(agg[name]["ece"]) / N
        print(f"  {name:<11} RPS {r:.4f}   logloss {ll:.3f}   ECE {e:.3f}")
    print("\n(Does 'DC+lineup' beat 'DC-prior'? That is whether the actual XI adds signal.)")


if __name__ == "__main__":
    main()
