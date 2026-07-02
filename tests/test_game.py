"""The Prediction Game's odds source (public/odds.json) must be well-formed and its client-side
blended win/draw/loss odds must match the bracket engine (build_tournament), so game.js shows the
same numbers the site does; the game's knockout mids must all exist in the real bracket."""
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
ODDS = ROOT / "public" / "odds.json"
MODEL = ROOT / "api" / "model.json"
ACTUAL = ROOT / "public" / "actual.json"

bt = pytest.importorskip("build_tournament")
K = 10


def _pois(k, lam):
    f = 1
    for i in range(2, k + 1):
        f *= i
    return math.exp(-lam) * lam ** k / f


def _js_outcome(od, h, a):
    """Mirror of public/game.js grid()+outcome(): neutral Dixon-Coles (with tau) blended 50/50
    with the ensemble table — the exact client-side computation."""
    rho = od["rho"]
    lh = math.exp(od["mu"] + od["attack"].get(h, 0) + od["defence"].get(a, 0))
    la = math.exp(od["mu"] + od["attack"].get(a, 0) + od["defence"].get(h, 0))
    g = [[_pois(i, lh) * _pois(j, la) for j in range(K + 1)] for i in range(K + 1)]
    g[0][0] *= 1 - lh * la * rho
    g[0][1] *= 1 + lh * rho
    g[1][0] *= 1 + la * rho
    g[1][1] *= 1 - rho
    t = sum(map(sum, g))
    g = [[c / t for c in r] for r in g]
    ph = sum(g[i][j] for i in range(K + 1) for j in range(K + 1) if i > j)
    pd = sum(g[i][i] for i in range(K + 1))
    pa = 1 - ph - pd
    key = f"{h}|{a}|0"
    ens = od["ens"]
    if key in ens["probs"]:
        pg, w = ens["probs"][key], ens["w"]
        p = [w * ph + (1 - w) * pg[0], w * pd + (1 - w) * pg[1], w * pa + (1 - w) * pg[2]]
        s = sum(p)
        return [x / s for x in p]
    return [ph, pd, pa]


@pytest.mark.skipif(not ODDS.exists(), reason="odds.json not built")
def test_odds_json_wellformed():
    od = json.loads(ODDS.read_text())
    M = json.loads(MODEL.read_text())
    assert set(od["attack"]) == set(M["squads"]) == set(od["defence"])
    assert len(od["attack"]) == 48
    assert od["ens"]["probs"] and 0.0 <= od["ens"]["w"] <= 1.0
    for p in list(od["ens"]["probs"].values())[:30]:
        assert abs(sum(p) - 1.0) < 1e-3 and all(x >= 0 for x in p)


@pytest.mark.skipif(not ODDS.exists(), reason="odds.json not built")
def test_game_odds_match_bracket_engine():
    od = json.loads(ODDS.read_text())
    M = json.loads(MODEL.read_text())
    teams = list(M["squads"])
    for h, a in [(teams[0], teams[7]), (teams[3], teams[20]), (teams[10], teams[30]), (teams[5], teams[6])]:
        got = _js_outcome(od, h, a)
        r = bt.predict(M, h, a, True)                     # neutral bracket odds (same tau + blend)
        for x, y in zip(got, [r["p_home"], r["p_draw"], r["p_away"]]):
            assert abs(x - y) < 2e-3                       # only the 5-dp rounding in odds.json
        assert abs(sum(got) - 1.0) < 1e-9


@pytest.mark.skipif(not ACTUAL.exists(), reason="actual.json not built")
def test_game_knockout_mids_exist_in_bracket():
    A = json.loads(ACTUAL.read_text())
    # R32 M73-M88, R16 M89-M96, QF M97-M100, SF M101-M102, Final M104 (M103 third-place isn't in the game)
    mids = [f"M{n}" for n in range(73, 103)] + ["M104"]
    assert len(mids) == 31
    for m in mids:
        assert m in A["bracket"], m
