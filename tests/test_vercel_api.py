"""The Vercel serverless functions (api/*.py, stdlib only) must import and produce valid output."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "api"


def _load(name):
    sys.path.insert(0, str(API))          # so `from _engine import ...` resolves, as on Vercel
    try:
        spec = importlib.util.spec_from_file_location(name, API / f"{name}.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(API))


def _model():
    return json.loads((API / "model.json").read_text())


def test_engine_predict_valid():
    eng = _load("_engine")
    model = _model()
    teams = sorted(model["squads"])
    assert len(teams) >= 2
    home, away = teams[0], teams[1]
    r = eng.predict_dict(model, home, away,
                         model["squads"][home][:11], model["squads"][away][:11], True)
    assert abs(r["prob_home"] + r["prob_draw"] + r["prob_away"] - 1.0) < 1e-6
    assert len(r["most_likely_score"]) == 2
    probs = [s["prob"] for s in r["home_scorers"]]
    assert probs == sorted(probs, reverse=True)          # scorers ranked high→low
    assert r["home_scorers"][0]["player"] in model["squads"][home]


def test_model_shape():
    model = _model()
    meta = model.get("meta", {})
    assert meta.get("n_teams") == len(model["squads"])   # 48 for the 2026 World Cup build
    for host in meta.get("hosts", []):                   # hosts must be real teams in the model
        assert host in model["squads"]
    for players in model["squads"].values():             # every squad player is rateable
        assert len(players) >= 11
        for p in players:
            assert p in model["players"]["scoring"] and p in model["players"]["assist"]


def test_handlers_import():
    for name in ("health", "teams", "squad", "predict"):
        assert hasattr(_load(name), "handler")
