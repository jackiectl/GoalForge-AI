"""Scrape the real 2026 FIFA World Cup squads (48 teams) from Wikipedia.

Public, attribution-required data (Wikipedia, CC BY-SA 4.0). We distill each roster to
(team, group, shirt no., position, player, caps, international goals, club) and cache it;
``scripts/export_model.py`` turns it into ``api/model.json``. The raw cache is regenerable,
so it lives under ``GOALFORGE_DATA_DIR`` (scratch), not git.

    python scripts/scrape_wc2026.py            # -> $GOALFORGE_DATA_DIR/wc2026_squads.parquet

Why Wikipedia: as of the tournament every squad is officially finalized and the squad
tables carry each player's caps and international goals — exactly the "last-years record"
signal GoalForge needs for the scorer layer.
"""
import io
import os
import re
import urllib.request

import pandas as pd
from bs4 import BeautifulSoup

SQUADS_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_squads"
HOSTS = ["United States", "Canada", "Mexico"]           # 2026 co-hosts get home advantage
UA = {"User-Agent": "GoalForge-research/0.1 (ctlang@umich.edu; educational, non-commercial)"}
SQUAD_COLS = {"No.", "Pos.", "Player", "Caps", "Goals", "Club"}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def _clean(s: str) -> str:
    s = re.sub(r"\[.*?\]", "", str(s))     # footnote refs [a], [1]
    s = re.sub(r"\(.*?\)", "", s)          # (captain), (c)
    return re.sub(r"\s+", " ", s).strip()


def _int(x) -> int:
    m = re.sub(r"[^\d]", "", str(x))
    return int(m) if m else 0


def scrape() -> pd.DataFrame:
    soup = BeautifulSoup(_get(SQUADS_URL), "lxml")
    rows = []
    for tbl in soup.find_all("table", class_="wikitable"):
        df = pd.read_html(io.StringIO(str(tbl)))[0]
        if not SQUAD_COLS.issubset(set(map(str, df.columns))):
            continue                       # skip non-squad tables (coaching staff, summaries)
        team = group = None
        for el in tbl.find_all_previous(["h2", "h3"]):
            t = el.get_text(" ", strip=True).replace("[edit]", "").strip()
            if el.name == "h3" and team is None:
                team = t
            elif el.name == "h2" and group is None and t.lower().startswith("group"):
                group = t
            if team and group:
                break
        for _, r in df.iterrows():
            name = _clean(r["Player"])
            if not name:
                continue
            rows.append({"team": team, "group": group, "no": _int(r["No."]),
                         "pos": str(r["Pos."]).strip(), "player": name,
                         "caps": _int(r["Caps"]), "goals": _int(r["Goals"]),
                         "club": _clean(r["Club"])})
    return pd.DataFrame(rows)


def main():
    cache = os.environ.get("GOALFORGE_DATA_DIR", "data")
    os.makedirs(cache, exist_ok=True)
    df = scrape()
    teams = sorted(df.team.unique())
    print(f"scraped {len(df)} players across {len(teams)} teams")
    by_group = df.drop_duplicates("team").groupby("group").team.apply(list)
    for g, ts in by_group.items():
        print(f"  {g}: {', '.join(ts)}")
    bad = [(t, n) for t, n in df.groupby("team").player.count().items() if not 20 <= n <= 27]
    if bad:
        print("  WARN unusual squad sizes:", bad)
    missing_hosts = [h for h in HOSTS if h not in teams]
    if missing_hosts:
        print("  WARN hosts missing from squads:", missing_hosts)
    out = os.path.join(cache, "wc2026_squads.parquet")
    df.to_parquet(out, index=False)
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
