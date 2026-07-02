"""Shared inference for the GoalForge Vercel functions — Python standard library only.

No third-party dependencies, so each function has nothing to install and cannot fail to import.
Inference is analytic: a Poisson scoreline plus per-player "anytime" probabilities via Poisson
thinning (1 - e^-lambda_i), matching the local Monte-Carlo engine closely. Sibling endpoint
files (health.py, teams.py, squad.py, predict.py) import these helpers — the same pattern as
the reference project's api/cafe.py importing api/cafe_nn.py.
"""
import json
import math
from pathlib import Path

_MODEL = None


def load_model():
    global _MODEL
    if _MODEL is None:
        here = Path(__file__).resolve().parent
        for p in (here / "model.json", Path("/var/task/api/model.json")):
            if p.exists():
                _MODEL = json.loads(p.read_text())
                break
    return _MODEL


def send_json(h, code, obj):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _rg(lam):
    """Nearest-integer expected goals -> projected (mean) scoreline; the modal exact cell is
    biased low (Poisson mode < mean, tau inflates 0-0/1-1), so favourites read 3-0 not 2-0."""
    return int(lam + 0.5)


def _score(lh, la, pw, pd, pa):
    """Rounded expected goals; a level rounding stays a draw only for a genuinely open game
    (neither side reaches a 45% win probability), else the favourite takes it by one goal."""
    hg, ag = _rg(lh), _rg(la)
    if hg == ag and max(pw, pa) >= 0.45:
        if pw >= pa:
            hg += 1
        else:
            ag += 1
    return hg, ag


def _expected_goals(M, home, away, neutral):
    s = M["score"]
    att, dfc = s["attack"], s["defence"]
    ha = 0.0 if neutral else s["home_adv"]
    lh = math.exp(s["mu"] + ha + att.get(home, 0.0) + dfc.get(away, 0.0))
    la = math.exp(s["mu"] + att.get(away, 0.0) + dfc.get(home, 0.0))
    return lh, la


def _rate(M, name, kind):
    p = M["players"]
    table = p["scoring"] if kind == "scoring" else p["assist"]
    default = p["global_score"] if kind == "scoring" else p["global_assist"]
    return float(table.get(name, default))


def _players(M, team_lambda, xi, kind, pen_fraction=0.10, assisted_rate=0.78):
    w = [max(_rate(M, n, kind), 0.0) for n in xi]
    sw = sum(w) or 1.0
    out = []
    if kind == "scoring":
        lam_open, lam_pen = team_lambda * (1 - pen_fraction), team_lambda * pen_fraction
        pen = max(range(len(xi)), key=lambda k: w[k]) if xi else -1
        for k, n in enumerate(xi):
            li = lam_open * (w[k] / sw) + (lam_pen if k == pen else 0.0)
            out.append({"player": n, "prob": 1 - math.exp(-li)})
    else:
        lam_a = team_lambda * assisted_rate
        for k, n in enumerate(xi):
            out.append({"player": n, "prob": 1 - math.exp(-(lam_a * (w[k] / sw)))})
    out.sort(key=lambda o: -o["prob"])
    return out[:8]


def _blend_outcome(M, home, away, neutral, p_dc):
    """Bake-off winner: 50/50 blend of DC outcome probs with the precomputed GBM table
    (scripts/build_ens_layer.py). Falls back to pure DC when the pair is missing."""
    ens = M.get("ens")
    if not ens:
        return p_dc
    p_gbm = ens["probs"].get(f"{home}|{away}|{int(not neutral)}")
    if not p_gbm:
        return p_dc
    w = float(ens.get("w", 0.5))
    p = [w * a + (1 - w) * b for a, b in zip(p_dc, p_gbm)]
    s = sum(p)
    return [x / s for x in p]


def predict_dict(M, home, away, home_xi, away_xi, neutral, K=10):
    lh, la = _expected_goals(M, home, away, neutral)
    ph = [_pois(i, lh) for i in range(K + 1)]
    pa = [_pois(j, la) for j in range(K + 1)]
    grid = [[ph[i] * pa[j] for j in range(K + 1)] for i in range(K + 1)]
    tot = sum(sum(r) for r in grid)
    grid = [[c / tot for c in r] for r in grid]
    p_dc = [sum(grid[i][j] for i in range(K + 1) for j in range(K + 1) if i > j),
            sum(grid[i][i] for i in range(K + 1)),
            sum(grid[i][j] for i in range(K + 1) for j in range(K + 1) if i < j)]
    prob_home, prob_draw, prob_away = _blend_outcome(M, home, away, neutral, p_dc)
    cells = sorted(((grid[i][j], i, j) for i in range(K + 1) for j in range(K + 1)), reverse=True)
    top = [{"home": i, "away": j, "prob": p} for p, i, j in cells[:6]]
    return {
        "home_team": home, "away_team": away,
        "prob_home": prob_home, "prob_draw": prob_draw, "prob_away": prob_away,
        "exp_home_goals": lh, "exp_away_goals": la,
        "projected_score": list(_score(lh, la, prob_home, prob_draw, prob_away)),
        "most_likely_score": [top[0]["home"], top[0]["away"]], "top_scores": top,
        "home_scorers": _players(M, lh, home_xi, "scoring"),
        "away_scorers": _players(M, la, away_xi, "scoring"),
        "home_assisters": _players(M, lh, home_xi, "assist"),
        "away_assisters": _players(M, la, away_xi, "assist"),
    }
