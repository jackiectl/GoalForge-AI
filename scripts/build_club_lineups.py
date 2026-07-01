"""Phase 3 follow-up (2): add CLUB starting-XI matches to grow the lineup dataset.

The lineup-aware model is starved by only ~314 international matches. StatsBomb's free club
data (La Liga, Champions League, top leagues) adds hundreds more matches with full XIs — and
many players overlap national squads, so their attack/defence deltas transfer. We cache the
same (matches, players) schema as the international set, tagged comp='CLUB:<name> <season>'.

    python scripts/build_club_lineups.py [--max-matches 700] [--min-year 2015]
        -> $GOALFORGE_DATA_DIR/club_lineups_{matches,players}.parquet

Non-commercial use with StatsBomb attribution.
"""
import argparse
import os
import re

import pandas as pd

# Club competitions to pull, in priority order (id, label). Season-filtered to modern years.
CLUB_COMPS = [(11, "La Liga"), (16, "Champions League"), (2, "Premier League"),
              (9, "Bundesliga"), (7, "Ligue 1"), (12, "Serie A"), (87, "Copa del Rey")]


def _pos_bucket(name: str) -> str:
    n = str(name)
    if "Goalkeeper" in n:
        return "GK"
    if "Back" in n:
        return "DF"
    if "Midfield" in n:
        return "MF"
    if any(k in n for k in ("Forward", "Wing", "Striker")):
        return "FW"
    return "MF"


def _starters(lineups: dict) -> list:
    out = []
    for team, df in lineups.items():
        for _, r in df.iterrows():
            start = next((p for p in (r.get("positions") or []) if str(p.get("from")) == "00:00"), None)
            if start:
                out.append((team, r["player_name"], _pos_bucket(start.get("position"))))
    return out


def _year(season_name: str) -> int:
    m = re.search(r"(\d{4})", str(season_name))
    return int(m.group(1)) if m else 0


def build(cache: str, max_matches: int, min_year: int, verbose: bool = True) -> tuple:
    from statsbombpy import sb
    comps = sb.competitions()
    m_rows, p_rows, total = [], [], 0
    for cid, label in CLUB_COMPS:
        seasons = comps[comps.competition_id == cid]
        for _, s in seasons.iterrows():
            if _year(s.season_name) < min_year:
                continue
            try:
                fx = sb.matches(competition_id=cid, season_id=int(s.season_id))
            except Exception:
                continue
            if verbose:
                print(f"{label} {s.season_name}: {len(fx)} matches (running total {total})")
            for _, f in fx.sort_values("match_date").iterrows():
                if total >= max_matches:
                    break
                mid = int(f["match_id"])
                try:
                    lu = sb.lineups(match_id=mid)
                except Exception:
                    continue
                st = _starters(lu)
                home, away = f["home_team"], f["away_team"]
                if sum(t == home for t, _, _ in st) < 7 or sum(t == away for t, _, _ in st) < 7:
                    continue
                comp_tag = f"CLUB:{label} {s.season_name}"
                m_rows.append((mid, comp_tag, f["match_date"], home, away,
                               int(f["home_score"]), int(f["away_score"])))
                for team, player, pos in st:
                    p_rows.append((mid, team, player, pos, int(team == home)))
                total += 1
            if total >= max_matches:
                break
        if total >= max_matches:
            break

    matches = pd.DataFrame(m_rows, columns=["match_id", "comp", "date", "home_team",
                                            "away_team", "home_goals", "away_goals"])
    players = pd.DataFrame(p_rows, columns=["match_id", "team", "player", "pos", "is_home"])
    os.makedirs(cache, exist_ok=True)
    matches.to_parquet(os.path.join(cache, "club_lineups_matches.parquet"), index=False)
    players.to_parquet(os.path.join(cache, "club_lineups_players.parquet"), index=False)
    return matches, players


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=os.environ.get("GOALFORGE_DATA_DIR", "data"))
    ap.add_argument("--max-matches", type=int, default=700)
    ap.add_argument("--min-year", type=int, default=2015)
    args = ap.parse_args()
    matches, players = build(args.cache, args.max_matches, args.min_year)
    print(f"\n{len(matches)} club matches, {players.player.nunique()} distinct starters")
    print(matches.assign(season=matches.comp).groupby("season").size().to_string())


if __name__ == "__main__":
    main()
