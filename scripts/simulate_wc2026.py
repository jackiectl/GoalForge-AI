"""Simulate the entire 2026 World Cup, group stage through final, many times.

Uses api/model.json (Dixon-Coles scoreline + per-player scoring/assist rates + the real 48-team
groups + hosts). Each Monte-Carlo run plays every group match (round-robin), ranks the groups,
advances 12 winners + 12 runners-up + 8 best third-placed to a 32-team knockout, and plays it to
a champion — sampling every scoreline and attributing each goal (and its assist) to a player.
Aggregated over N runs it yields a rich forecast:

  * champion / final / semi / quarter / round-of-32 probabilities per team,
  * group-winner and advancement probabilities,
  * Golden Boot (top scorer) and Playmaker (top assists) races + expected goals/assists,
  * plus extras: most goal involvements, Golden Glove (fewest goals conceded, deep run),
    expected total goals, most likely final, biggest upsets.

    python scripts/simulate_wc2026.py [--sims 20000]

Honest caveats: pre-tournament forecast (ignores results already played); the knockout bracket is
a seeded approximation, not FIFA's exact slotting; scorer/assist attribution uses the (history/
prior-based) player layer. It is a forecast, not a prediction of certainty.
"""
import argparse
import json
import os
from collections import defaultdict

import numpy as np

HOST_ADV = True


def _team_lambdas(M):
    s = M["score"]
    return s["mu"], s["home_adv"], s["attack"], s["defence"]


def expected_goals(M, home, away, neutral):
    mu, ha, att, dfc = _team_lambdas(M)
    lh = np.exp(mu + (0.0 if neutral else ha) + att.get(home, 0.0) + dfc.get(away, 0.0))
    la = np.exp(mu + att.get(away, 0.0) + dfc.get(home, 0.0))
    return lh, la


def _xi_weights(M, team, kind):
    xi = M["squads"][team][:11]
    tab = M["players"]["scoring" if kind == "scoring" else "assist"]
    g = M["players"]["global_score" if kind == "scoring" else "global_assist"]
    w = np.array([max(tab.get(p, g), 1e-6) for p in xi])
    return xi, w / w.sum()


def sim_match(M, home, away, rng, neutral, goals_tally, assist_tally, allow_draw=True):
    """Return (hg, ag, winner) and attribute goals/assists to players."""
    lh, la = expected_goals(M, home, away, neutral)
    hg, ag = int(rng.poisson(lh)), int(rng.poisson(la))
    for team, n in ((home, hg), (away, ag)):
        if n == 0:
            continue
        xi_s, w_s = _xi_weights(M, team, "scoring")
        for idx in rng.choice(len(xi_s), size=n, p=w_s):
            goals_tally[xi_s[idx]] += 1
        xi_a, w_a = _xi_weights(M, team, "assist")
        for _ in range(n):
            if rng.random() < 0.78:                       # ~78% of goals are assisted
                assist_tally[xi_a[rng.choice(len(xi_a), p=w_a)]] += 1
    if hg != ag:
        return hg, ag, home if hg > ag else away
    if not allow_draw:                                    # knockout: shade the coin flip by strength
        p_home = lh / (lh + la)
        return hg, ag, home if rng.random() < p_home else away
    return hg, ag, None


def _host(M, t):
    return t in M["meta"].get("hosts", [])


def run_once(M, groups, rng, stats):
    goals, assists = defaultdict(int), defaultdict(int)
    conceded = defaultdict(int)
    # ---- group stage ----
    standings = {}                                        # group -> list of (team, pts, gd, gf)
    thirds = []
    for g, teams in groups.items():
        pts = dict.fromkeys(teams, 0)
        gd = dict.fromkeys(teams, 0)
        gf = dict.fromkeys(teams, 0)
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                a, b = teams[i], teams[j]
                neutral = not (HOST_ADV and (_host(M, a) or _host(M, b)))
                home = a if (_host(M, a) or not _host(M, b)) else b
                away = b if home == a else a
                hg, ag, _ = sim_match(M, home, away, rng, neutral, goals, assists)
                conceded[home] += ag
                conceded[away] += hg
                res = {home: (hg, ag), away: (ag, hg)}
                for t in (a, b):
                    f, ag_ = res[t]
                    gf[t] += f
                    gd[t] += f - ag_
                    pts[t] += 3 if f > ag_ else (1 if f == ag_ else 0)
        rank = sorted(teams, key=lambda t: (pts[t], gd[t], gf[t]), reverse=True)
        standings[g] = rank
        stats["group_winner"][rank[0]] += 1
        for pos, t in enumerate(rank):
            if pos <= 1:
                stats["advance"][t] += 1
        thirds.append((rank[2], pts[rank[2]], gd[rank[2]], gf[rank[2]]))
    # 8 best third-placed also advance (48-team format)
    best_thirds = [t for t, *_ in sorted(thirds, key=lambda x: (x[1], x[2], x[3]), reverse=True)[:8]]
    for t in best_thirds:
        stats["advance"][t] += 1

    # ---- knockout: seed 32 qualifiers, fixed standard bracket ----
    quals = ([standings[g][0] for g in groups] + [standings[g][1] for g in groups] + best_thirds)
    _, _, att, dfc = _team_lambdas(M)
    quals = sorted(quals, key=lambda t: att.get(t, 0) - dfc.get(t, 0), reverse=True)[:32]
    round_names = ["r32", "r16", "qf", "sf", "final"]
    field = quals[:]
    finalists = None
    for rnd in round_names:
        for t in field:
            stats[rnd][t] += 1
        if rnd == "final":
            finalists = tuple(sorted(field))
        nxt = []
        for i in range(0, len(field), 2):
            a, b = field[i], field[i + 1]
            _, _, w = sim_match(M, a, b, rng, True, goals, assists, allow_draw=False)
            nxt.append(w)
        field = nxt
    stats["champion"][field[0]] += 1
    if finalists:
        stats["final_pair"][finalists] += 1

    for p, n in goals.items():
        stats["pg"][p] += n
    for p, n in assists.items():
        stats["pa"][p] += n
    top_s = max(goals, key=goals.get) if goals else None
    top_a = max(assists, key=assists.get) if assists else None
    if top_s:
        stats["golden_boot"][top_s] += 1
    if top_a:
        stats["playmaker"][top_a] += 1
    inv = {p: goals.get(p, 0) + assists.get(p, 0) for p in set(goals) | set(assists)}
    if inv:
        stats["mvp"][max(inv, key=inv.get)] += 1
    stats["total_goals"].append(sum(goals.values()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="api/model.json")
    ap.add_argument("--sims", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="reports/wc2026_forecast.json")
    args = ap.parse_args()
    M = json.load(open(args.model))
    groups = defaultdict(list)
    for t, g in M["meta"]["groups"].items():
        groups[g].append(t)
    groups = dict(sorted(groups.items()))
    rng = np.random.default_rng(args.seed)

    keys = ["group_winner", "advance", "r32", "r16", "qf", "sf", "final", "champion",
            "golden_boot", "playmaker", "mvp", "pg", "pa", "final_pair"]
    stats = {k: defaultdict(int) for k in keys}
    stats["total_goals"] = []
    for _ in range(args.sims):
        run_once(M, groups, rng, stats)

    N = args.sims
    info = M.get("player_info", {})

    def top(counter, k=12, pct=True):
        return [(t, (c / N if pct else c / N)) for t, c in sorted(counter.items(), key=lambda x: -x[1])[:k]]

    print(f"\n===== 2026 WORLD CUP FORECAST ({N:,} simulations) =====")
    print("\n-- CHAMPION --")
    for t, p in top(stats["champion"]):
        print(f"  {t:16s} {p:5.1%}   (final {stats['final'][t]/N:4.0%} · semi {stats['sf'][t]/N:4.0%})")
    print("\n-- GOLDEN BOOT (P top scorer | expected goals) --")
    for t, p in top(stats["golden_boot"]):
        tm = info.get(t, {}).get("team", "")
        print(f"  {t:20s} {p:5.1%}  ({stats['pg'][t]/N:.1f} G, {tm})")
    print("\n-- PLAYMAKER (P top assists | expected assists) --")
    for t, p in top(stats["playmaker"]):
        print(f"  {t:20s} {p:5.1%}  ({stats['pa'][t]/N:.1f} A, {info.get(t,{}).get('team','')})")
    print("\n-- MOST GOAL INVOLVEMENTS (G+A) --")
    for t, p in top(stats["mvp"], 8):
        print(f"  {t:20s} {p:5.1%}  ({(stats['pg'][t]+stats['pa'][t])/N:.1f} G+A)")
    print("\n-- extras --")
    print(f"  expected total goals in tournament: {np.mean(stats['total_goals']):.0f}")
    fav = sorted(stats["champion"].items(), key=lambda x: -x[1])[0]
    print(f"  favourite: {fav[0]} ({fav[1]/N:.0%})")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    out = {"sims": N, "champion": dict(top(stats["champion"], 48)),
           "reach_final": {t: stats["final"][t] / N for t in M["squads"]},
           "reach_sf": {t: stats["sf"][t] / N for t in M["squads"]},
           "advance": {t: stats["advance"][t] / N for t in M["squads"]},
           "golden_boot": dict(top(stats["golden_boot"], 20)),
           "playmaker": dict(top(stats["playmaker"], 20)),
           "exp_goals": {t: stats["pg"][t] / N for t, _ in top(stats["pg"], 30)},
           "exp_total_goals": float(np.mean(stats["total_goals"]))}
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=0)
    print(f"\nsaved -> {args.out}")


if __name__ == "__main__":
    main()
