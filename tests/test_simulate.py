"""Edge-case tests for the 2026 World Cup Monte-Carlo simulator (scripts/simulate_wc2026.py)."""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
MODEL = ROOT / "api" / "model.json"

sim = pytest.importorskip("simulate_wc2026")   # needs numpy; skip if unavailable


def _run(n=400, seed=1):
    M = json.load(open(MODEL))
    groups = defaultdict(list)
    for t, g in M["meta"]["groups"].items():
        groups[g].append(t)
    groups = dict(sorted(groups.items()))
    keys = ["group_winner", "advance", "r32", "r16", "qf", "sf", "final", "champion",
            "golden_boot", "playmaker", "mvp", "pg", "pa", "final_pair"]
    stats = {k: defaultdict(int) for k in keys}
    stats["total_goals"] = []
    rng = np.random.default_rng(seed)
    for _ in range(n):
        sim.run_once(M, groups, rng, stats)
    return M, groups, stats, n


def test_round_size_conservation():
    """Summed over teams, each round must hold exactly its field size every sim."""
    _, _, s, n = _run()
    for rnd, size in [("r32", 32), ("r16", 16), ("qf", 8), ("sf", 4), ("final", 2), ("champion", 1)]:
        assert sum(s[rnd].values()) == size * n, f"{rnd} field size wrong"
    assert sum(s["advance"].values()) == 32 * n           # 24 top-two + 8 best thirds
    assert sum(s["group_winner"].values()) == 12 * n      # one winner per group


def test_per_team_monotonic_nesting():
    """A team cannot reach round R without reaching every earlier round (per team)."""
    M, _, s, _ = _run()
    for t in M["squads"]:
        chain = [s["advance"][t], s["r32"][t], s["r16"][t], s["qf"][t], s["sf"][t],
                 s["final"][t], s["champion"][t]]
        assert chain == sorted(chain, reverse=True), f"{t} non-monotone: {chain}"
    # r32 field == the 32 that advanced (same set)
    assert dict(s["r32"]) == dict(s["advance"])


def test_group_winner_probabilities_sum_per_group():
    M, groups, s, n = _run()
    for g, teams in groups.items():
        assert sum(s["group_winner"][t] for t in teams) == n, f"group {g} winners != n"


def test_reproducible_with_seed():
    _, _, s1, _ = _run(n=200, seed=7)
    _, _, s2, _ = _run(n=200, seed=7)
    assert dict(s1["champion"]) == dict(s2["champion"])
    assert dict(s1["pg"]) == dict(s2["pg"])


def test_outputs_are_real_entities():
    M, _, s, _ = _run()
    for team in s["champion"]:
        assert team in M["squads"]
    squad_players = {p for xi in M["squads"].values() for p in xi}
    for p in list(s["golden_boot"])[:20]:
        assert p in squad_players
    assert 1.5 < np.mean(s["total_goals"]) / 104 < 3.5    # sane goals-per-match over 104 games


def test_knockout_never_draws():
    """With allow_draw=False, sim_match must always return a winner."""
    M = json.load(open(MODEL))
    rng = np.random.default_rng(0)
    g, a = defaultdict(int), defaultdict(int)
    for _ in range(300):
        *_, w = sim.sim_match(M, "Brazil", "Argentina", rng, True, g, a, allow_draw=False)
        assert w in ("Brazil", "Argentina")


def test_host_advantage_raises_lambda():
    M = json.load(open(MODEL))
    host = M["meta"]["hosts"][0]
    opp = next(t for t in M["squads"] if t not in M["meta"]["hosts"])
    lh_home, _ = sim.expected_goals(M, host, opp, neutral=False)
    lh_neu, _ = sim.expected_goals(M, host, opp, neutral=True)
    assert lh_home > lh_neu                                # home advantage lifts expected goals
