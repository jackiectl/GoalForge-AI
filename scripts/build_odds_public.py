"""Slim public odds table for the Prediction Game frontend.

api/model.json lives on the server path and is not a web asset, so public/game.js cannot fetch it.
This writes public/odds.json — the neutral Dixon-Coles score params (mu, rho + the 48 World Cup
squads' attack/defence) plus the deployed GBM ensemble table — so the game can compute exactly the
same blended win/draw/loss and scoreline odds the site's API serves, for any WC pairing, client-side.

    python scripts/build_odds_public.py   # api/model.json -> public/odds.json
"""
import argparse
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="api/model.json")
    ap.add_argument("--out", default="public/odds.json")
    args = ap.parse_args()

    M = json.load(open(args.model))
    wc = set(M["squads"])                                    # the 48 real 2026 squads
    s = M["score"]
    out = {
        "mu": s["mu"], "home_adv": s["home_adv"], "rho": s.get("rho", 0.0),
        "attack": {t: round(s["attack"].get(t, 0.0), 5) for t in wc},
        "defence": {t: round(s["defence"].get(t, 0.0), 5) for t in wc},
        "ens": M.get("ens", {}),                             # {w, probs: "H|A|neutral" -> [pH,pD,pA]}
    }
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=0)
    print(f"wrote {args.out}: {len(wc)} teams, ens {len(out['ens'].get('probs', {}))} pairs")


if __name__ == "__main__":
    main()
