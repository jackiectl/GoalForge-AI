"""Edge-case tests for the deterministic tournament walk (scripts/build_tournament.py)."""
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
MODEL = ROOT / "api" / "model.json"

bt = pytest.importorskip("build_tournament")

# Official per-match third-place candidate groups (FIFA Regulations Art. 12.6) — the Annex C
# table must never place a third outside these lists.
CANDIDATES = {"M74": "ABCDF", "M77": "CDFGH", "M79": "CEFHI", "M80": "EHIJK",
              "M81": "BEFIJ", "M82": "AEHIJ", "M85": "EFGIJ", "M87": "DEIJL"}


@pytest.fixture(scope="module")
def T(tmp_path_factory):
    out = tmp_path_factory.mktemp("t") / "tournament.json"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_tournament.py"),
                    "--out", str(out)], check=True, cwd=ROOT, capture_output=True)
    return json.load(open(out))


@pytest.fixture(scope="module")
def M():
    return json.load(open(MODEL))


def _grp(M):
    return {t: g.replace("Group", "").strip()[:1] for t, g in M["meta"]["groups"].items()}


# ---------- annex C integrity ----------
def test_annex_c_full_coverage_and_constraints():
    annex = json.load(open(ROOT / "configs" / "annex_c.json"))
    from itertools import combinations
    assert len(annex["table"]) == 495
    hosts = annex["hosts"]
    match_of = {"A": "M79", "B": "M85", "D": "M81", "E": "M74", "G": "M82",
                "I": "M77", "K": "M87", "L": "M80"}
    for combo in combinations("ABCDEFGHIJKL", 8):
        key = "".join(combo)
        assert key in annex["table"], f"missing combination {key}"
        assigns = annex["table"][key]
        assert sorted(assigns) == sorted(combo)                    # 8 thirds used exactly once
        for host, third in zip(hosts, assigns):
            assert third != host                                   # never own group
            assert third in CANDIDATES[match_of[host]], \
                f"{key}: 1{host} vs 3{third} outside official candidates"


# ---------- group stage ----------
def test_every_group_six_matches_and_round_robin(T):
    for g, blk in T["groups"].items():
        assert len(blk["matches"]) == 6
        c = Counter()
        for m in blk["matches"]:
            c[m["home"]] += 1
            c[m["away"]] += 1
        assert set(c.values()) == {3}                               # each team plays 3


def test_table_arithmetic_consistent_with_matches(T):
    for g, blk in T["groups"].items():
        gf = defaultdict(int)
        ga = defaultdict(int)
        pts = defaultdict(int)
        for m in blk["matches"]:
            gf[m["home"]] += m["hg"]
            ga[m["home"]] += m["ag"]
            gf[m["away"]] += m["ag"]
            ga[m["away"]] += m["hg"]
            if m["hg"] > m["ag"]:
                pts[m["home"]] += 3
            elif m["hg"] < m["ag"]:
                pts[m["away"]] += 3
            else:
                pts[m["home"]] += 1
                pts[m["away"]] += 1
        for r in blk["table"]:
            assert (r["gf"], r["ga"], r["pts"]) == (gf[r["team"]], ga[r["team"]], pts[r["team"]])
            assert r["gd"] == r["gf"] - r["ga"]
            assert r["pts"] == 3 * r["w"] + r["d"] and r["w"] + r["d"] + r["l"] == 3


def test_tables_sorted_by_points_first(T):
    for blk in T["groups"].values():
        pts = [r["pts"] for r in blk["table"]]
        assert pts == sorted(pts, reverse=True)


def test_host_home_advantage_only_for_hosts(T, M):
    hosts = set(M["meta"]["hosts"])
    for blk in T["groups"].values():
        for m in blk["matches"]:
            one_host = (m["home"] in hosts) != (m["away"] in hosts)
            assert m["neutral"] == (not one_host)
            if not m["neutral"]:
                assert m["home"] in hosts                           # host always the home side


# ---------- tiebreaker unit tests (synthetic, 2026 rules: head-to-head first) ----------
def test_h2h_beats_overall_gd():
    # A beat B; B has much better overall GD. 2026 rules: A above B (pre-2026 would flip).
    teams = ["A", "B", "C", "D"]
    res = {("A", "B"): (1, 0), ("A", "C"): (0, 1), ("A", "D"): (2, 0),
           ("B", "C"): (5, 0), ("B", "D"): (4, 0), ("C", "D"): (0, 0)}
    xkey = {t: (0, 0) for t in teams}
    order, overall = bt.rank_group(teams, res, xkey)
    assert overall["A"][0] == overall["B"][0] == 6                 # both 6 pts
    assert overall["B"][1] > overall["A"][1]                       # B better overall GD
    assert order.index("A") < order.index("B")                     # ...but A won the h2h


def test_three_way_tie_mini_table():
    # A,B,C all 3 pts in a cycle; mini-table GD decides among them.
    teams = ["A", "B", "C", "D"]
    res = {("A", "B"): (2, 0), ("B", "C"): (2, 1), ("C", "A"): (1, 0),
           ("A", "D"): (0, 1), ("B", "D"): (0, 1), ("C", "D"): (0, 1)}
    xkey = {t: (0, 0) for t in teams}
    order, overall = bt.rank_group(teams, res, xkey)
    assert order[0] == "D"                                          # 9 pts
    # cycle mini-table: A +1 (2-0,0-1), B -1, C 0 -> A, C, B
    assert order[1:] == ["A", "C", "B"]


def test_fully_tied_falls_back_to_xkey():
    teams = ["A", "B", "C", "D"]
    res = {("A", "B"): (0, 0), ("A", "C"): (0, 0), ("A", "D"): (0, 0),
           ("B", "C"): (0, 0), ("B", "D"): (0, 0), ("C", "D"): (0, 0)}
    xkey = {"A": (1.0, 0), "B": (3.0, 0), "C": (2.0, 0), "D": (0.5, 0)}
    order, _ = bt.rank_group(teams, res, xkey)
    assert order == ["B", "C", "A", "D"]


# ---------- knockout ----------
def test_bracket_sizes_and_progression(T):
    b = T["bracket"]
    assert [len(b[r]) for r in ("r32", "r16", "qf", "sf", "final")] == [16, 8, 4, 2, 1]
    assert len(b["third_place"]) == 1
    for rnd, nxt in (("r32", "r16"), ("r16", "qf"), ("qf", "sf"), ("sf", "final")):
        winners = {m["winner"] for m in b[rnd]}
        entrants = {m["home"] for m in b[nxt]} | {m["away"] for m in b[nxt]}
        assert entrants <= winners                                  # every entrant won prior round
    assert b["champion"] == b["final"][0]["winner"]
    sf_losers = {x for m in b["sf"] for x in (m["home"], m["away"])} - \
                {m["winner"] for m in b["sf"]}
    tp = b["third_place"][0]
    assert {tp["home"], tp["away"]} == sf_losers                    # 3rd-place = the two SF losers


def test_r32_field_is_exactly_the_advancers(T):
    top2 = {r["team"] for blk in T["groups"].values() for r in blk["table"][:2]}
    thirds = set(T["thirds"]["advanced"])
    field = {x for m in T["bracket"]["r32"] for x in (m["home"], m["away"])}
    assert field == top2 | thirds and len(field) == 32


def test_no_same_group_meeting_in_r32(T, M):
    grp = _grp(M)
    for m in T["bracket"]["r32"]:
        assert grp[m["home"]] != grp[m["away"]], m["id"]


def test_thirds_slotting_follows_annex_c(T, M):
    grp = _grp(M)
    key = T["meta"]["annex_c_key"]
    assert key == "".join(sorted(grp[t] for t in T["thirds"]["advanced"]))
    annex = json.load(open(ROOT / "configs" / "annex_c.json"))
    match_of = {"A": "M79", "B": "M85", "D": "M81", "E": "M74", "G": "M82",
                "I": "M77", "K": "M87", "L": "M80"}
    by_id = {m["id"]: m for m in T["bracket"]["r32"]}
    third_by_group = {grp[t]: t for t in T["thirds"]["advanced"]}
    for host, third_grp in zip(annex["hosts"], annex["table"][key]):
        m = by_id[match_of[host]]
        assert third_by_group[third_grp] in (m["home"], m["away"])


def test_knockout_always_has_winner_and_decided_flag(T):
    for rnd in ("r32", "r16", "qf", "sf", "third_place", "final"):
        for m in T["bracket"][rnd] if isinstance(T["bracket"][rnd], list) else []:
            assert m["winner"] in (m["home"], m["away"])
            assert m["decided"] == ("90min" if m["hg"] != m["ag"] else "et_pens")
            assert m["p_win"] >= 0.5 - 1e-9                          # winner is the likelier side


def test_thirds_ranking_order(T):
    r = T["thirds"]["ranking"]
    keys = [(x["pts"], x["gd"], x["gf"]) for x in r]
    # non-increasing up to the xpts stand-in (ties allowed)
    assert all(keys[i] >= keys[i + 1] for i in range(len(keys) - 1))
    assert [x["team"] for x in r[:8]] == T["thirds"]["advanced"]


# ---------- honors ----------
def test_honors_boards_sane(T, M):
    hb = T["honors"]
    squad_players = {p for xi in M["squads"].values() for p in xi}
    for board in (hb["golden_boot"], hb["playmaker"]):
        assert 10 <= len(board) <= 25
        vals = [r["exp"] for r in board]
        assert vals == sorted(vals, reverse=True) and vals[0] > 0
        for r in board[:10]:
            assert r["player"] in squad_players
    gg = hb["golden_glove"]
    assert gg and gg["matches"] == 8                                # a semifinalist+
    assert gg["player"] in M["squads"][gg["team"]][:11]
    assert 100 <= hb["total_goals"] <= 400                          # 104 matches, sane range


def test_deterministic_output(T, tmp_path):
    out2 = tmp_path / "t2.json"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_tournament.py"),
                    "--out", str(out2)], check=True, cwd=ROOT, capture_output=True)
    assert json.load(open(out2)) == T
