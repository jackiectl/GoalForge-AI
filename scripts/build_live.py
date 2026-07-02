"""Live re-forecast: re-predict the rest of the 2026 World Cup given the results SO FAR.

The deployed forecast is frozen at kick-off (2026-06-11) and never sees a 2026 result — that is
the honest pre-tournament baseline. This is the complementary "nowcast": refit the Dixon-Coles
team model on *all* international matches **including** the 2026 games played to date, then walk
the REAL knockout bracket (real qualifiers, real round-of-32 pairings) forward from where the
tournament actually stands — actual results for matches already played, model predictions
(with the same penalty-shootout logic as the modal bracket) for the rest — down to a live champion.

Run it after each daily refresh of results (scripts/build_actual.py first, then this):

    python scripts/build_actual.py && python scripts/build_live.py

Output: public/live.json — the live bracket (actual past + predicted future) + the live champion,
alongside the original frozen champion for side-by-side comparison on the Live Re-forecast page.
"""
import argparse
import json
import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_tournament import LATER, R32, _pens_tally  # noqa: E402

from goalforge.data.international import load_international  # noqa: E402
from goalforge.models.scoreline import DixonColesModel  # noqa: E402

K = 10
HALF_LIFE = 730


def _grid(dc, home, away):
    lh, la = dc.expected_goals(home, away, neutral=True)
    rho = float(dc.rho_)
    fact = [math.factorial(k) for k in range(K + 1)]
    ph = [math.exp(-lh) * lh ** i / fact[i] for i in range(K + 1)]
    pa = [math.exp(-la) * la ** j / fact[j] for j in range(K + 1)]
    g = [[ph[i] * pa[j] for j in range(K + 1)] for i in range(K + 1)]
    g[0][0] *= 1 - lh * la * rho
    g[0][1] *= 1 + lh * rho
    g[1][0] *= 1 + la * rho
    g[1][1] *= 1 - rho
    tot = sum(map(sum, g))
    return [[c / tot for c in r] for r in g]


def predict_live(dc, mid, home, away):
    p = dc.predict_proba(home, away, neutral=True)
    ph, pa = p["home_win"], p["away_win"]
    g = _grid(dc, home, away)
    pw_cond = ph / max(ph + pa, 1e-9)
    winner = home if pw_cond >= 0.5 else away
    m = {"home": home, "away": away, "winner": winner, "id": mid, "pred": True, "played": False}
    if abs(pw_cond - 0.5) < 0.10:                       # coin-flip tie -> penalties (see build_tournament)
        i = max(range(K + 1), key=lambda k: g[k][k])
        wp, lp = _pens_tally(mid + home + away)
        m.update(reg=[i, i], hs=i, as_=i, pens=([wp, lp] if winner == home else [lp, wp]), decided="pens")
    else:
        win_home = winner == home
        cells = [(i, j) for i in range(K + 1) for j in range(K + 1) if (i > j) == win_home and i != j]
        i, j = max(cells, key=lambda c: g[c[0]][c[1]])
        m.update(reg=[i, j], hs=i, as_=j, pens=None, decided="reg")
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--actual", default="public/actual.json")
    ap.add_argument("--pred", default="public/tournament.json")
    ap.add_argument("--forecast", default="public/forecast.json")
    ap.add_argument("--out", default="public/live.json")
    args = ap.parse_args()

    A = json.load(open(args.actual))
    as_of = A["as_of"]
    cutoff = (pd.to_datetime(as_of) + pd.Timedelta(days=1)).date()

    # refit DC on ALL international matches including the 2026 games played so far
    intl = load_international(start_year=2010)
    matches = intl.matches[pd.to_datetime(intl.matches.date) < pd.to_datetime(cutoff)]
    print(f"live refit: {len(matches)} matches through {as_of} (cutoff {cutoff})")
    dc = DixonColesModel(l2=0.1).fit(matches, half_life_days=HALF_LIFE, ref_date=pd.to_datetime(cutoff))

    # walk the REAL bracket forward: actual result where played, live prediction otherwise
    ab = A["bracket"]
    won, out = {}, {}

    def resolve(mid, home, away):
        a = ab.get(mid, {})
        if a.get("winner") and a.get("played"):        # already played -> keep the real result
            out[mid] = {"home": a["home"], "away": a["away"], "hs": a["actual"][0], "as_": a["actual"][1],
                        "reg": a["reg"], "pens": a.get("pens"), "decided": a.get("decided"),
                        "winner": a["winner"], "played": True, "pred": False, "id": mid}
        else:
            out[mid] = predict_live(dc, mid, home, away)
        won[mid] = out[mid]["winner"]

    for mid, _, _ in R32:                              # real R32 teams come from the actual bracket
        a = ab.get(mid, {})
        resolve(mid, a.get("home"), a.get("away"))
    for _, tpl in LATER.items():
        for mid, fa, fb in tpl:
            resolve(mid, won.get(fa), won.get(fb))
    champion_live = won.get("M104")

    # rename as_ -> as for the JSON the frontend reads
    for m in out.values():
        m["as"] = m.pop("as_")

    forecast = json.load(open(args.forecast)) if os.path.exists(args.forecast) else {}
    odds = list(forecast.get("champion", {}).items())[:6]
    result = {"as_of": as_of, "cutoff": str(cutoff),
              "bracket": out, "champion_live": champion_live,
              "champion_original": json.load(open(args.pred))["bracket"]["champion"],
              "original_odds": [{"team": t, "p": p} for t, p in odds],
              "note": "Team ratings refit on every international match through " + as_of +
                      "; the real bracket walked forward with actual results where played."}
    json.dump(result, open(args.out, "w"), ensure_ascii=False, indent=0)

    n_pred = sum(1 for m in out.values() if m["pred"])
    print(f"live champion: {champion_live}  (original frozen pick: {result['champion_original']})")
    print(f"bracket: {len(out)} matches, {len(out) - n_pred} actual / {n_pred} predicted")
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
