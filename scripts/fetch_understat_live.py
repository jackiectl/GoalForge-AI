"""LIVE Understat scraper for the newest club xG/xA — run from a RESIDENTIAL IP.

understat.com blocks the cluster's datacenter IP (it serves a stripped page with no player
data). It does NOT block ordinary residential IPs, so run this ON YOUR LAPTOP, then copy the
output to the cluster:

    # on your laptop (residential IP):
    pip install pandas pyarrow
    python scripts/fetch_understat_live.py
    scp understat_players.parquet ctlang@gl-login.arc-ts.umich.edu:$GOALFORGE_DATA_DIR/

    # then on Great Lakes, rebuild with the fresh data:
    python scripts/build_player_form.py && python scripts/build_wc2026_model.py

...or run it on the cluster THROUGH a reverse SOCKS tunnel from your laptop:
    ssh -R 1080 ctlang@gl-login.arc-ts.umich.edu     # (keep open, on your laptop)
    HTTPS_PROXY=socks5h://localhost:1080 python scripts/fetch_understat_live.py   # (on the cluster)

Output matches fetch_understat.py (understat_players.parquet), so the rest of the pipeline is
unchanged. Data: Understat (free, non-commercial); attribution to Understat.
"""
import argparse
import json
import os
import re
import time
import urllib.request

import pandas as pd

LEAGUES = ["EPL", "La_liga", "Serie_A", "Bundesliga", "Ligue_1"]
SEASONS = [2023, 2024, 2025]                                   # 2023/24-2025/26 (year = season start)
SUM = ["time", "goals", "xG", "npg", "npxG", "assists", "xA", "shots", "key_passes"]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"}


def _players(html: str):
    m = re.search(r"playersData\s*=\s*JSON\.parse\('", html)
    if not m:
        return None                                            # stripped page (blocked IP)
    end = html.index("')", m.end())
    return json.loads(html[m.end():end].encode().decode("unicode_escape"))


def fetch(cache: str, verbose: bool = True) -> pd.DataFrame:
    num = ["time", "goals", "xG", "npg", "npxG", "assists", "xA", "shots", "key_passes"]
    rows = []
    for lg in LEAGUES:
        for yr in SEASONS:
            url = f"https://understat.com/league/{lg}/{yr}"
            html = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "replace")
            players = _players(html)
            if not players:
                print(f"  WARN {lg}/{yr}: no player data (blocked IP? run on a residential network)")
                continue
            for p in players:
                r = {"player_name": p["player_name"], "position": p["position"],
                     "team_title": p["team_title"]}
                r.update({k: float(p[k]) for k in num})
                rows.append(r)
            if verbose:
                print(f"  {lg}/{yr}: {len(players)} players")
            time.sleep(1.0)                                    # be polite
    allp = pd.DataFrame(rows)
    agg = allp.groupby("player_name", as_index=False).agg(
        {**{c: "sum" for c in SUM}, "team_title": "last"})
    pos = allp.groupby("player_name").position.agg(lambda s: s.mode().iloc[0]).rename("position")
    out = agg.merge(pos, on="player_name")
    out["nineties"] = out["time"] / 90.0
    dst = os.path.join(cache, "understat_players.parquet")
    os.makedirs(cache, exist_ok=True)
    out.to_parquet(dst, index=False)
    return out, dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("GOALFORGE_DATA_DIR", "."))
    args = ap.parse_args()
    out, dst = fetch(args.cache)
    if len(out):
        print(f"\n{len(out)} players over {SEASONS} x {len(LEAGUES)} leagues -> {dst}")
        print(out.sort_values("xA", ascending=False).head(5)
              [["player_name", "team_title", "nineties", "goals", "xG", "assists", "xA"]].round(1).to_string(index=False))
    else:
        print("\nNo data fetched — you are on a blocked IP. Run on your laptop or via an SSH SOCKS tunnel.")


if __name__ == "__main__":
    main()
