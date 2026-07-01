"""Download club-league goals + appearances (StatsBomb events) to enrich per-player rates.

Step-1 evaluation showed international-only scoring rates are too sparse to out-rank a plain
position prior. This caches each player's CLUB output (goals/assists/minutes) so we can pool
international + club data into a single, less-noisy rate. Uses the same load_competition path
as the internationals; frames are cached under GOALFORGE_DATA_DIR (regenerable, scratch).

    python scripts/build_club_events.py        # caches La Liga / Premier League events (2015+)

Non-commercial use with StatsBomb attribution. NOTE: this pulls full-season EVENTS and is a
large one-time download.
"""
import os
import re

from goalforge.data.statsbomb import load_competition

CLUB = [(11, "La Liga"), (2, "Premier League")]   # full-season sources with broad player coverage
MIN_YEAR = 2015


def main():
    from statsbombpy import sb
    comps = sb.competitions()
    done = []
    for cid, label in CLUB:
        for _, s in comps[comps.competition_id == cid].sort_values("season_name").iterrows():
            m = re.search(r"(\d{4})", str(s.season_name))
            if not m or int(m.group(1)) < MIN_YEAR:
                continue
            d = load_competition(cid, int(s.season_id), verbose=False)
            g = int(d.goals.scorer.notna().sum())
            print(f"{label} {s.season_name}: {len(d.matches)} matches | {g} goals | "
                  f"{len(d.appearances)} appearances")
            done.append((cid, int(s.season_id), f"{label} {s.season_name}"))
    # record which (cid, sid) were cached, for the combined-rate evaluation to pick up
    idx = os.path.join(os.environ.get("GOALFORGE_DATA_DIR", "data"), "club_events_index.csv")
    with open(idx, "w") as f:
        f.write("competition_id,season_id,label\n")
        for cid, sid, lab in done:
            f.write(f"{cid},{sid},{lab}\n")
    print(f"\ncached {len(done)} club seasons -> {idx}")


if __name__ == "__main__":
    main()
