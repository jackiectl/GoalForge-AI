"""Self-contained GoalForge prediction API for Vercel — Python standard library ONLY.

No third-party dependencies (no numpy / fastapi), so the serverless function has nothing to
install and cannot fail to import. Inference is analytic: a Poisson scoreline plus per-player
"anytime" probabilities via Poisson thinning (1 - e^-lambda_i), which closely match the
Monte-Carlo engine used locally. The model is loaded lazily from api/model.json.
"""
import json
import math
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse

_MODEL = None


def _load_model():
    here = Path(__file__).resolve().parent
    for p in (here / "model.json", here.parent / "model.json", Path("/var/task/api/model.json")):
        if p.exists():
            return json.loads(p.read_text())
    return None


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = _load_model()
    return _MODEL


def _pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


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


def predict_dict(M, home, away, home_xi, away_xi, neutral, K=10):
    lh, la = _expected_goals(M, home, away, neutral)
    ph = [_pois(i, lh) for i in range(K + 1)]
    pa = [_pois(j, la) for j in range(K + 1)]
    grid = [[ph[i] * pa[j] for j in range(K + 1)] for i in range(K + 1)]
    tot = sum(sum(r) for r in grid)
    grid = [[c / tot for c in r] for r in grid]
    prob_home = sum(grid[i][j] for i in range(K + 1) for j in range(K + 1) if i > j)
    prob_draw = sum(grid[i][i] for i in range(K + 1))
    prob_away = sum(grid[i][j] for i in range(K + 1) for j in range(K + 1) if i < j)
    cells = sorted(((grid[i][j], i, j) for i in range(K + 1) for j in range(K + 1)), reverse=True)
    top = [{"home": i, "away": j, "prob": p} for p, i, j in cells[:6]]
    return {
        "home_team": home, "away_team": away,
        "prob_home": prob_home, "prob_draw": prob_draw, "prob_away": prob_away,
        "exp_home_goals": lh, "exp_away_goals": la,
        "most_likely_score": [top[0]["home"], top[0]["away"]], "top_scores": top,
        "home_scorers": _players(M, lh, home_xi, "scoring"),
        "away_scorers": _players(M, la, away_xi, "scoring"),
        "home_assisters": _players(M, lh, home_xi, "assist"),
        "away_assisters": _players(M, la, away_xi, "assist"),
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        M = model()
        if path.endswith("/health"):
            return self._send(200, {"status": "ok" if M else "no_model",
                                    "teams": len(M["squads"]) if M else 0})
        if M is None:
            return self._send(503, {"detail": "model.json not found"})
        if path.endswith("/teams"):
            return self._send(200, {"teams": sorted(M["squads"]), "meta": M.get("meta", {})})
        if path.endswith("/squad"):
            parts = path.split("/")
            team = unquote(parts[-2]) if len(parts) >= 2 else ""
            if team not in M["squads"]:
                return self._send(404, {"detail": f"unknown team: {team}"})
            return self._send(200, {"team": team, "players": M["squads"][team],
                                    "default_xi": M["squads"][team][:11]})
        return self._send(404, {"detail": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        M = model()
        if M is None:
            return self._send(503, {"detail": "model.json not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"detail": "invalid JSON body"})
        if path.endswith("/predict"):
            h, a = req.get("home_team"), req.get("away_team")
            if h not in M["squads"] or a not in M["squads"]:
                return self._send(404, {"detail": "unknown team"})
            if h == a:
                return self._send(400, {"detail": "home_team and away_team must differ"})
            hx = req.get("home_xi") or M["squads"][h][:11]
            ax = req.get("away_xi") or M["squads"][a][:11]
            return self._send(200, predict_dict(M, h, a, hx, ax, bool(req.get("neutral", True))))
        return self._send(404, {"detail": "not found"})
