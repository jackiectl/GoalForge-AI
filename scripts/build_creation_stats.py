"""Per-player chance-creation stats (key passes + expected assists) from StatsBomb events.

Step-1 showed actual assists are too sparse to rank assisters well. Chance creation is a much
denser signal: a KEY PASS (a pass that leads to a shot) happens ~10x more often than an assist,
and EXPECTED ASSISTS (xA = the xG of the shot each key pass creates) grade those chances. This
processor re-reads events and caches, per (match, team, player): key_passes and xa. The assist
evaluation then ranks likely assisters by xA/90 instead of the rare actual-assist count.

    python scripts/build_creation_stats.py            # 6 internationals -> creation_{cid}_{sid}.parquet
    python scripts/build_creation_stats.py --club     # also the cached club seasons

Non-commercial use with StatsBomb attribution.
"""
import argparse
import os

import pandas as pd

TOURN = [(43, 106, "WC2022"), (43, 3, "WC2018"), (55, 282, "Euro2024"),
         (55, 43, "Euro2020"), (223, 282, "Copa2024"), (1267, 107, "AFCON2023")]


def _creation(ev) -> list:
    """One row per key pass: (team, player, xa) — xa = xG of the shot the pass created."""
    if "type" not in ev.columns or "pass_shot_assist" not in ev.columns:
        return []
    shots = ev[ev["type"] == "Shot"]
    xg = (dict(zip(shots["id"], shots["shot_statsbomb_xg"].fillna(0.0)))
          if "shot_statsbomb_xg" in shots.columns else {})
    out = []
    for _, p in ev[ev["pass_shot_assist"] == True].iterrows():  # noqa: E712
        out.append((p["team"], p["player"], float(xg.get(p.get("pass_assisted_shot_id"), 0.0))))
    return out


def build_one(cid: int, sid: int, cache: str, verbose: bool = True) -> str:
    from statsbombpy import sb
    out = os.path.join(cache, f"creation_{cid}_{sid}.parquet")
    if os.path.exists(out):
        if verbose:
            print(f"  (cache hit: {out})")
        return out
    rows = []
    fixtures = sb.matches(competition_id=cid, season_id=sid)
    for mid in fixtures["match_id"].astype(int):
        try:
            ev = sb.events(match_id=int(mid))
        except Exception:  # pragma: no cover
            continue
        for team, player, xa in _creation(ev):
            rows.append((int(mid), team, player, 1, xa))
    df = pd.DataFrame(rows, columns=["match_id", "team", "player", "key_passes", "xa"])
    df = df.groupby(["match_id", "team", "player"], as_index=False).sum()
    df.to_parquet(out, index=False)
    if verbose:
        print(f"{cid}/{sid}: {len(df)} player-match creation rows, {int(df.key_passes.sum())} key passes")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("GOALFORGE_DATA_DIR", "data"))
    ap.add_argument("--club", action="store_true", help="also process cached club seasons")
    args = ap.parse_args()
    seasons = [(c, s) for c, s, _ in TOURN]
    if args.club:
        idx = os.path.join(args.cache, "club_events_index.csv")
        if os.path.exists(idx):
            seasons += [(int(r.competition_id), int(r.season_id)) for _, r in pd.read_csv(idx).iterrows()]
    for cid, sid in seasons:
        build_one(cid, sid, args.cache)
    print(f"DONE: {len(seasons)} seasons of creation stats")


if __name__ == "__main__":
    main()
