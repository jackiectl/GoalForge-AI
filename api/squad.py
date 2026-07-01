"""GET /api/squad?team=NAME — Vercel serverless function (stdlib only)."""
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find sibling _engine.py in the lambda
from _engine import load_model, send_json  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        M = load_model()
        if not M:
            return send_json(self, 503, {"detail": "model.json not found"})
        team = (parse_qs(urlparse(self.path).query).get("team") or [""])[0]
        if team not in M["squads"]:
            return send_json(self, 404, {"detail": f"unknown team: {team}"})
        players = M["squads"][team]
        info = M.get("player_info", {})
        send_json(self, 200, {"team": team, "players": players, "default_xi": players[:11],
                              "info": {p: info[p] for p in players if p in info}})

    def log_message(self, *args):
        pass
