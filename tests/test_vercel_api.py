"""The Vercel serverless function (api/index.py) is pure stdlib and must produce valid output."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("vercel_index", ROOT / "api" / "index.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_vercel_function_valid():
    m = _load()
    model = json.loads((ROOT / "api" / "model.json").read_text())
    r = m.predict_dict(model, "Argentina", "France",
                       model["squads"]["Argentina"][:11], model["squads"]["France"][:11], True)
    assert abs(r["prob_home"] + r["prob_draw"] + r["prob_away"] - 1.0) < 1e-6
    assert len(r["most_likely_score"]) == 2
    assert len(r["home_scorers"]) >= 1
    probs = [s["prob"] for s in r["home_scorers"]]
    assert probs == sorted(probs, reverse=True)
    assert r["home_scorers"][0]["player"] in model["squads"]["Argentina"]
