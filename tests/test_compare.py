"""The shipped Prediction-vs-Actual artifact (public/actual.json) and the deployed ensemble
blend (api/model.json["ens"] + api/_engine.py) must be well-formed and self-consistent."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"
ACTUAL = ROOT / "public" / "actual.json"


def _engine():
    sys.path.insert(0, str(API))
    try:
        spec = importlib.util.spec_from_file_location("_engine", API / "_engine.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(API))


# ---------- prediction vs actual ----------
@pytest.mark.skipif(not ACTUAL.exists(), reason="actual.json not built")
def test_actual_json_wellformed():
    A = json.loads(ACTUAL.read_text())
    assert len(A["groups"]) == 12
    m = A["metrics"]
    assert 0.0 <= m["outcome_acc"] <= 1.0
    assert 0.0 <= m["exact_acc"] <= m["outcome_acc"]          # exact ⊆ outcome-correct
    assert m["rps"] < m["rps_baserate"]                       # forecast beats base-rate out-of-sample
    assert m["advancers_total"] == 32 and 0 <= m["advancers_correct"] <= 32
    assert m["top2_correct"] <= m["top2_total"] == 24


@pytest.mark.skipif(not ACTUAL.exists(), reason="actual.json not built")
def test_actual_matches_consistent():
    A = json.loads(ACTUAL.read_text())
    scored = 0
    for blk in A["groups"].values():
        assert len(blk["matches"]) == 6
        for mm in blk["matches"]:
            probs = mm["probs"]
            assert abs(sum(probs) - 1.0) < 0.02 and all(p >= 0 for p in probs)
            if "actual" in mm:
                scored += 1
                pk = 0 if mm["pred"][0] > mm["pred"][1] else (1 if mm["pred"][0] == mm["pred"][1] else 2)
                ak = 0 if mm["actual"][0] > mm["actual"][1] else (1 if mm["actual"][0] == mm["actual"][1] else 2)
                assert mm["outcome_hit"] == (pk == ak)
                assert mm["exact_hit"] == (mm["pred"] == mm["actual"])
                assert not (mm["exact_hit"] and not mm["outcome_hit"])   # exact ⇒ outcome
    assert scored == A["metrics"]["group_matches_scored"]


@pytest.mark.skipif(not ACTUAL.exists(), reason="actual.json not built")
def test_actual_advancers_are_32_real_teams():
    A = json.loads(ACTUAL.read_text())
    model = json.loads((API / "model.json").read_text())
    adv = A["advancers"]["actual"]
    assert len(set(adv)) == 32
    assert all(t in model["squads"] for t in adv)


# ---------- deployed ensemble blend ----------
def test_ens_layer_present_and_valid():
    model = json.loads((API / "model.json").read_text())
    ens = model.get("ens")
    assert ens and 0.0 <= ens["w"] <= 1.0
    teams = sorted(model["squads"])
    # 48*47 ordered pairs * 2 venue flags
    assert len(ens["probs"]) == len(teams) * (len(teams) - 1) * 2
    for p in list(ens["probs"].values())[:50]:
        assert abs(sum(p) - 1.0) < 1e-3 and all(x >= 0 for x in p)


def test_blend_changes_probs_and_stays_normalised():
    eng = _engine()
    model = json.loads((API / "model.json").read_text())
    teams = sorted(model["squads"])
    home, away = teams[0], teams[5]
    r = eng.predict_dict(model, home, away,
                         model["squads"][home][:11], model["squads"][away][:11], True)
    assert abs(r["prob_home"] + r["prob_draw"] + r["prob_away"] - 1.0) < 1e-6
    # the blend must actually move the number away from pure Dixon-Coles
    lh, la = eng._expected_goals(model, home, away, True)
    K = 10
    ph = [eng._pois(i, lh) for i in range(K + 1)]
    pa = [eng._pois(j, la) for j in range(K + 1)]
    grid = [[ph[i] * pa[j] for j in range(K + 1)] for i in range(K + 1)]
    tot = sum(sum(row) for row in grid)
    dc_home = sum(grid[i][j] for i in range(K + 1) for j in range(K + 1) if i > j) / tot
    assert abs(r["prob_home"] - dc_home) > 1e-6


def test_blend_absent_falls_back_to_dc():
    eng = _engine()
    model = json.loads((API / "model.json").read_text())
    model.pop("ens", None)                                   # simulate a model without the layer
    teams = sorted(model["squads"])
    r = eng.predict_dict(model, teams[0], teams[1],
                         model["squads"][teams[0]][:11], model["squads"][teams[1]][:11], True)
    assert abs(r["prob_home"] + r["prob_draw"] + r["prob_away"] - 1.0) < 1e-6
