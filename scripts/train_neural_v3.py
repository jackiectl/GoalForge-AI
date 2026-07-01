"""Phase 3 follow-up (2): grow the lineup data with CLUB matches — do XI deltas help now?

Follow-up (1) learned player attack/defence deltas from only ~314 international matches. Here
we pool ~700 club matches (StatsBomb: La Liga, Premier League, ...) with the internationals, so
each player's delta is estimated from ~3x more starting-XIs (many players appear in both). The
team baseline stays honest per match type:

  * international match: fixed Dixon-Coles log-lambda (martj42 minus the held-out tournament),
  * club match:         a learnable club-team attack/defence embedding + club mu.

The SAME per-player deltas are shared across both. Leave-one-tournament-out on the 6 internationals.
Compares DC-prior-only vs DC-prior + shared-deltas(club+intl) vs Elo vs base. Honest either way.

    python scripts/train_neural_v3.py           # needs build_intl_lineups + build_club_lineups first
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
L2_PLAYER, L2_POS, L2_CLUB = 1.5, 0.05, 0.1
EPOCHS, LR = 500, 0.05


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


class SharedDelta(nn.Module):
    """Shared per-player deltas over two baselines: fixed DC (intl) or learnable club embeddings."""

    def __init__(self, n_players, n_clubs):
        super().__init__()
        self.p_att = nn.Embedding(n_players + 1, 1, padding_idx=0)
        self.p_def = nn.Embedding(n_players + 1, 1, padding_idx=0)
        self.pos_att = nn.Embedding(4, 1)
        self.pos_def = nn.Embedding(4, 1)
        self.c_att = nn.Embedding(n_clubs + 1, 1, padding_idx=0)
        self.c_def = nn.Embedding(n_clubs + 1, 1, padding_idx=0)
        self.club_mu = nn.Parameter(torch.zeros(1))
        for e in (self.p_att, self.p_def, self.pos_att, self.pos_def, self.c_att, self.c_def):
            nn.init.zeros_(e.weight)

    def _delta(self, pidx, ppos, mask):
        a = ((self.p_att(pidx).squeeze(-1) + self.pos_att(ppos).squeeze(-1)) * mask).sum(1)
        d = ((self.p_def(pidx).squeeze(-1) + self.pos_def(ppos).squeeze(-1)) * mask).sum(1)
        n = mask.sum(1).clamp(min=1)
        return a / n, d / n

    def forward(self, b):
        dah, ddh = self._delta(b["hp"], b["hpos"], b["hmask"])
        daa, dda = self._delta(b["ap"], b["apos"], b["amask"])
        club_h = self.club_mu + self.c_att(b["ch"]).squeeze(-1) - self.c_def(b["ca"]).squeeze(-1)
        club_a = self.club_mu + self.c_att(b["ca"]).squeeze(-1) - self.c_def(b["ch"]).squeeze(-1)
        base_h = b["is_club"] * club_h + (1 - b["is_club"]) * b["dc_lh"]
        base_a = b["is_club"] * club_a + (1 - b["is_club"]) * b["dc_la"]
        log_lh = (base_h + dah - dda).clamp(-2.0, 2.5)
        log_la = (base_a + daa - ddh).clamp(-2.0, 2.5)
        return log_lh, log_la

    def l2(self):
        return (L2_PLAYER * (self.p_att.weight.pow(2).sum() + self.p_def.weight.pow(2).sum())
                + L2_POS * (self.pos_att.weight.pow(2).sum() + self.pos_def.weight.pow(2).sum())
                + L2_CLUB * (self.c_att.weight.pow(2).sum() + self.c_def.weight.pow(2).sum()))


def _batch(rows, lineups, pvoc, device):
    n = len(rows)
    t = {k: torch.zeros(n, MAXP, dtype=torch.long) for k in ("hp", "ap", "hpos", "apos")}
    m = {k: torch.zeros(n, MAXP) for k in ("hmask", "amask")}
    sc = {k: torch.zeros(n) for k in ("yh", "ya", "dc_lh", "dc_la", "is_club")}
    ci = {k: torch.zeros(n, dtype=torch.long) for k in ("ch", "ca")}
    for i, (_, r) in enumerate(rows.iterrows()):
        sc["yh"][i], sc["ya"][i] = r.home_goals, r.away_goals
        sc["dc_lh"][i], sc["dc_la"][i] = r.dc_lh, r.dc_la
        sc["is_club"][i] = r.is_club
        ci["ch"][i], ci["ca"][i] = r.ch, r.ca
        for pk, ok, mk, home in (("hp", "hpos", "hmask", 1), ("ap", "apos", "amask", 0)):
            for k, (pl, pos) in enumerate(lineups.get((r.match_id, home), [])[:MAXP]):
                t[pk][i, k] = pvoc.get(pl, 0)
                t[ok][i, k] = POS[pos]
                m[mk][i, k] = 1.0
    d = {**t, **m, **sc, **ci}
    return {k: v.to(device) for k, v in d.items()}


def _fit(train, lineups, pvoc, n_clubs, device, seed=0):
    torch.manual_seed(seed)
    model = SharedDelta(len(pvoc), n_clubs).to(device)
    b = _batch(train, lineups, pvoc, device)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    for _ in range(EPOCHS):
        opt.zero_grad()
        lh, la = model(b)
        nll = (lh.exp() - b["yh"] * lh).mean() + (la.exp() - b["ya"] * la).mean()
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

    im = pd.read_parquet(os.path.join(args.cache, "intl_lineups_matches.parquet"))
    ip = pd.read_parquet(os.path.join(args.cache, "intl_lineups_players.parquet"))
    cm = pd.read_parquet(os.path.join(args.cache, "club_lineups_matches.parquet"))
    cp = pd.read_parquet(os.path.join(args.cache, "club_lineups_players.parquet"))
    im["dkey"] = (pd.to_datetime(im.date).dt.strftime("%Y-%m-%d") + "|"
                  + im[["home_team", "away_team"]].apply(lambda r: "|".join(sorted(r)), axis=1))

    lineups = {(mid, h): list(zip(g.player, g.pos))
               for (mid, h), g in pd.concat([ip, cp]).groupby(["match_id", "is_home"])}
    pvoc = {p: i + 1 for i, p in enumerate(sorted(set(ip.player) | set(cp.player)))}
    cvoc = {t: i + 1 for i, t in enumerate(sorted(set(cm.home_team) | set(cm.away_team)))}
    comps = sorted(im.comp.unique())
    print(f"intl {len(im)} + club {len(cm)} matches | {len(pvoc)} players | {len(cvoc)} clubs")

    # club rows are constant across folds (no DC offset, learnable club baseline)
    club = cm.copy()
    club["is_club"], club["dc_lh"], club["dc_la"] = 1.0, 0.0, 0.0
    club["ch"] = club.home_team.map(cvoc)
    club["ca"] = club.away_team.map(cvoc)

    agg = {n: {"rps": [], "ll": [], "ece": [], "n": []}
           for n in ("DC+lineup(club)", "DC-prior", "Elo", "Base")}
    print(f"\nleave-one-tournament-out over {comps}\n")
    print(f"{'held-out':<11}{'n':>4}   {'DC+lineup(club)':>17}{'DC-prior':>15}{'Elo':>9}{'Base':>8}")
    for comp in comps:
        te = im[im.comp == comp].copy()
        tr_intl = im[im.comp != comp].copy()
        base_matches = m2[~m2.key.isin(set(te.dkey))]
        dc = DixonColesModel(l2=0.1).fit(base_matches, half_life_days=730,
                                         ref_date=pd.to_datetime(te.date).min())
        elo = EloBaseline().fit(base_matches)
        base = base_rates(base_matches)

        def dc_off(df):
            df = df.copy()
            lam = [dc.expected_goals(r.home_team, r.away_team, neutral=True) for _, r in df.iterrows()]
            df["dc_lh"] = [math.log(x[0]) for x in lam]
            df["dc_la"] = [math.log(x[1]) for x in lam]
            df["is_club"], df["ch"], df["ca"] = 0.0, 0, 0
            return df

        tr = pd.concat([club, dc_off(tr_intl)], ignore_index=True)
        te2 = dc_off(te)
        model = _fit(tr, lineups, pvoc, len(cvoc), args.device)
        b = _batch(te2, lineups, pvoc, args.device)
        with torch.no_grad():
            lh, la = model(b)
        lh, la, rho = lh.exp().cpu().numpy(), la.exp().cpu().numpy(), float(dc.rho_)
        preds_l, preds_dc, preds_elo, preds_base = [], [], [], []
        for i, (_, m) in enumerate(te.iterrows()):
            preds_l.append(outcome_probs(lh[i], la[i], rho))
            dh, da = dc.expected_goals(m.home_team, m.away_team, neutral=True)
            preds_dc.append(outcome_probs(dh, da, rho))
            pe = elo.predict_proba(m.home_team, m.away_team, neutral=True)
            preds_elo.append([pe["home_win"], pe["draw"], pe["away_win"]])
            preds_base.append(base)

        cells = {}
        for name, preds in (("DC+lineup(club)", preds_l), ("DC-prior", preds_dc),
                            ("Elo", preds_elo), ("Base", preds_base)):
            r, ll, e = _metrics(preds, te)
            agg[name]["rps"].append(r * len(te))
            agg[name]["ll"].append(ll * len(te))
            agg[name]["ece"].append(e * len(te))
            agg[name]["n"].append(len(te))
            cells[name] = r
        print(f"{comp:<11}{len(te):>4}   {cells['DC+lineup(club)']:.4f}          "
              f"{cells['DC-prior']:.4f}       {cells['Elo']:.4f}  {cells['Base']:.4f}")

    print("\n=== weighted overall (RPS / logloss / ECE) ===")
    for name in ("DC+lineup(club)", "DC-prior", "Elo", "Base"):
        N = sum(agg[name]["n"])
        r = sum(agg[name]["rps"]) / N
        ll = sum(agg[name]["ll"]) / N
        e = sum(agg[name]["ece"]) / N
        print(f"  {name:<16} RPS {r:.4f}   logloss {ll:.3f}   ECE {e:.3f}")
    print("\n(Does 'DC+lineup(club)' beat 'DC-prior' now that deltas saw 3x more XIs?)")


if __name__ == "__main__":
    main()
