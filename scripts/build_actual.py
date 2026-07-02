"""Compare the pre-tournament forecast against the REAL 2026 World Cup results.

The deployed model is frozen at 2026-06-11 (kick-off), so every real match is a genuine
out-of-sample test. This reads the actual results from the martj42 cache (which now contains
the ongoing 2026 tournament), lines each one up against public/tournament.json, and writes
public/actual.json for the "Prediction vs Actual" page:

  * all 72 group matches: predicted score + W/D/L probs vs the real score/outcome;
  * actual group tables and who really advanced (ground-truth from the real round-of-32
    fixtures) vs who we predicted to advance;
  * knockout results played so far vs our modal bracket;
  * honest accuracy: outcome hit-rate, exact-score hit-rate, and RPS/log-loss of our
    probabilities on the real outcomes (vs a base-rate baseline).

    python scripts/build_actual.py [--results <martj42_results.csv>]
"""
import argparse
import json
import math
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_tournament import rank_group  # noqa: E402  (FIFA Art. 13 tiebreakers)

OUTCOMES = ("home", "draw", "away")


def _outcome(hs, as_):
    return 0 if hs > as_ else (1 if hs == as_ else 2)


def rps(probs, k):
    c = 0.0
    acc_p = acc_o = 0.0
    for i in range(len(probs) - 1):
        acc_p += probs[i]
        acc_o += 1.0 if i == k else 0.0
        c += (acc_p - acc_o) ** 2
    return c / (len(probs) - 1)


def log_loss(probs, k):
    return -math.log(max(probs[k], 1e-12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(
        os.environ.get("GOALFORGE_DATA_DIR", "data"), "martj42_results.csv"))
    ap.add_argument("--model", default="api/model.json")
    ap.add_argument("--pred", default="public/tournament.json")
    ap.add_argument("--out", default="public/actual.json")
    args = ap.parse_args()

    M = json.load(open(args.model))
    T = json.load(open(args.pred))
    grp = {t: g.replace("Group", "").strip()[:1] for t, g in M["meta"]["groups"].items()}

    res = pd.read_csv(args.results)
    res["date"] = pd.to_datetime(res["date"])
    wc = res[(res.tournament == "FIFA World Cup") & (res.date >= "2026-06-01")].copy()
    wc = wc.sort_values("date").reset_index(drop=True)
    wc["same_group"] = wc.apply(lambda r: grp.get(r.home_team) == grp.get(r.away_team), axis=1)
    wc["played"] = wc.home_score.notna()

    # actual results keyed by unordered pair -> (home, away, hs, as)
    actual = {}
    for _, r in wc[wc.played].iterrows():
        actual[frozenset((r.home_team, r.away_team))] = (
            r.home_team, r.away_team, int(r.home_score), int(r.away_score))

    # ---- group stage: 72 fixtures, predicted vs actual ----
    groups_out = {}
    n_out_hit = n_exact = n_group = 0
    sum_rps = sum_ll = sum_rps_base = 0.0
    base = [0.0, 0.0, 0.0]
    for blk in T["groups"].values():
        for mm in blk["matches"]:
            k = _outcome(mm["hg"], mm["ag"])
            base[k] += 1
    tot = sum(base)
    base = [b / tot for b in base]                          # predicted-outcome base rate

    for g, blk in T["groups"].items():
        matches = []
        for mm in blk["matches"]:
            pair = frozenset((mm["home"], mm["away"]))
            probs = [mm["p_home"], mm["p_draw"], mm["p_away"]]
            row = {"home": mm["home"], "away": mm["away"],
                   "pred": [mm["hg"], mm["ag"]], "probs": [round(p, 3) for p in probs]}
            if pair in actual:
                ah, aa, hs, as_ = actual[pair]
                if ah != mm["home"]:                         # align actual to predicted orientation
                    hs, as_ = as_, hs
                row["actual"] = [hs, as_]
                pk, ok = _outcome(mm["hg"], mm["ag"]), _outcome(hs, as_)
                # base-rate outcome prob aligned to this match's orientation is symmetric enough
                row["outcome_hit"] = pk == ok
                row["exact_hit"] = [mm["hg"], mm["ag"]] == [hs, as_]
                sum_rps += rps(probs, ok)
                sum_ll += log_loss(probs, ok)
                sum_rps_base += rps(base, ok)
                n_out_hit += row["outcome_hit"]
                n_exact += row["exact_hit"]
                n_group += 1
            matches.append(row)

        # actual standings from real scores (FIFA tiebreakers); predicted table already in blk
        teams = [r["team"] for r in blk["table"]]
        gres, xkey = {}, {}
        pts, gf, ga = defaultdict(int), defaultdict(int), defaultdict(int)
        wdl = defaultdict(lambda: [0, 0, 0])
        have_all = True
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                pair = frozenset((teams[i], teams[j]))
                if pair not in actual:
                    have_all = False
                    continue
                ah, aa, hs, as_ = actual[pair]
                gres[(ah, aa)] = (hs, as_)
                for t, f, a in ((ah, hs, as_), (aa, as_, hs)):
                    gf[t] += f
                    ga[t] += a
                    pts[t] += 3 if f > a else (1 if f == a else 0)
                    wdl[t][0 if f > a else (1 if f == a else 2)] += 1
        if have_all:
            xkey = {t: (pts[t], gf[t] - ga[t]) for t in teams}
            order, _ = rank_group(teams, gres, xkey)
        else:
            order = teams
        atable = [{"team": t, "w": wdl[t][0], "d": wdl[t][1], "l": wdl[t][2],
                   "gf": gf[t], "ga": ga[t], "gd": gf[t] - ga[t], "pts": pts[t]} for t in order]
        groups_out[g] = {"matches": matches, "actual_table": atable,
                         "pred_table": blk["table"]}

    # ---- who actually advanced: ground truth = teams appearing in the real round-of-32 ----
    ko_rows = wc[~wc.same_group].reset_index(drop=True)
    r32 = ko_rows.iloc[:16]                                  # M73-M88
    actual_adv = sorted(set(r32.home_team) | set(r32.away_team))
    pred_adv = sorted(set(T["thirds"]["advanced"])
                      | {r["team"] for blk in T["groups"].values() for r in blk["table"][:2]})
    adv_hit = len(set(actual_adv) & set(pred_adv))

    # per-group: did we call the top two?
    top2_hits = 0
    for g, blk in groups_out.items():
        actual_top2 = {r["team"] for r in blk["actual_table"][:2]} if len(blk["actual_table"]) == 4 \
            else set(a for a in actual_adv if grp[a] == g)      # fallback
        pred_top2 = {r["team"] for r in blk["pred_table"][:2]}
        top2_hits += len(actual_top2 & pred_top2)

    # ---- knockout played so far vs our modal bracket ----
    pred_ko = {frozenset((mm["home"], mm["away"])): mm
               for rnd in ("r32", "r16", "qf", "sf", "third_place", "final")
               for mm in (T["bracket"].get(rnd) or [])
               if isinstance(T["bracket"].get(rnd), list)}
    knockout = []
    for _, r in ko_rows.iterrows():
        item = {"home": r.home_team, "away": r.away_team,
                "actual": [int(r.home_score), int(r.away_score)] if r.played else None}
        pm = pred_ko.get(frozenset((r.home_team, r.away_team)))
        if pm:
            item["we_predicted_this_tie"] = True
            item["pred"] = [pm["hg"], pm["ag"]]
            item["pred_winner"] = pm.get("winner")
        knockout.append(item)

    champ = T["bracket"]["champion"]
    champ_alive = champ in actual_adv                       # still in (reached R32 at least)

    metrics = {
        "group_matches_scored": n_group,
        "outcome_acc": round(n_out_hit / n_group, 4) if n_group else None,
        "exact_acc": round(n_exact / n_group, 4) if n_group else None,
        "rps": round(sum_rps / n_group, 4) if n_group else None,
        "rps_baserate": round(sum_rps_base / n_group, 4) if n_group else None,
        "log_loss": round(sum_ll / n_group, 4) if n_group else None,
        "advancers_correct": adv_hit, "advancers_total": len(actual_adv),
        "top2_correct": top2_hits, "top2_total": 2 * len(groups_out),
        "champion": champ, "champion_alive": champ_alive,
    }
    out = {"as_of": str(wc[wc.played].date.max().date()),
           "groups": groups_out,
           "advancers": {"actual": actual_adv, "predicted": pred_adv},
           "knockout": knockout, "metrics": metrics}
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=0)

    print(f"as of {out['as_of']} | {n_group} group games scored")
    print(f"  outcome W/D/L accuracy : {n_out_hit}/{n_group} = {metrics['outcome_acc']:.1%}")
    print(f"  exact scoreline        : {n_exact}/{n_group} = {metrics['exact_acc']:.1%}")
    print(f"  RPS (ours / base-rate) : {metrics['rps']} / {metrics['rps_baserate']}")
    print(f"  qualifiers predicted   : {adv_hit}/{len(actual_adv)}")
    print(f"  group top-2 predicted  : {top2_hits}/{2 * len(groups_out)}")
    print(f"  predicted champion {champ}: {'still in' if champ_alive else 'OUT'}")
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
