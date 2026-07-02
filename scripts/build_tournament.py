"""Predict the whole 2026 World Cup match-by-match (deterministic most-likely path).

Unlike scripts/simulate_wc2026.py (Monte-Carlo *probabilities* over thousands of tournaments),
this walks ONE tournament — the modal path — exactly as a fan would fill in a bracket:

  1. all 72 group matches: Dixon-Coles score matrix (tau low-score correction) -> most likely
     score; W/D/L probs use the bake-off winner (50/50 DC + GBM blend from model.json "ens",
     see scripts/team_bakeoff.py); hosts get a down-weighted home edge (HOST_ADV_SCALE);
  2. group tables from those scores with the REAL FIFA 2026 tiebreakers (Art. 13: head-to-head
     first among tied teams, then overall GD/GF; conduct-points & FIFA-ranking steps are not
     modellable, so expected points then expected GD stand in — documented honestly);
  3. the 8 best thirds (Art. 13 ranking) are slotted with FIFA's actual Annex C 495-row table
     (configs/annex_c.json) into the official round-of-32 template (M73-M88), then the official
     bracket tree (M89-M104, incl. the third-place match) is played to the final;
  4. per-player expected goals/assists accumulate along each team's predicted run ->
     Golden Boot / Playmaker leaderboards + a Golden Glove pick.

Output: public/tournament.json (consumed by the site's tournament & honors pages).

    python scripts/build_tournament.py [--host-scale 0.5] [--out public/tournament.json]
"""
import argparse
import json
import math
from collections import defaultdict

HOST_ADV_SCALE = 0.5          # keep in sync with scripts/simulate_wc2026.py
K = 10                        # score grid 0..K
ASSISTED = 0.78               # share of goals with an assist (matches the MC engine)

# ---- official knockout structure (FIFA WC2026 Regulations Art. 12.6-12.11) --------------------
# Round of 32: (match, home_slot, away_slot); "1A"=winner A, "2A"=runner-up, "3@M79"=Annex C third
R32 = [("M73", "2A", "2B"), ("M74", "1E", "3rd"), ("M75", "1F", "2C"), ("M76", "1C", "2F"),
       ("M77", "1I", "3rd"), ("M78", "2E", "2I"), ("M79", "1A", "3rd"), ("M80", "1L", "3rd"),
       ("M81", "1D", "3rd"), ("M82", "1G", "3rd"), ("M83", "2K", "2L"), ("M84", "1H", "2J"),
       ("M85", "1B", "3rd"), ("M86", "1J", "2H"), ("M87", "1K", "3rd"), ("M88", "2D", "2G")]
# Annex C assigns thirds to the eight group winners in host order A,B,D,E,G,I,K,L; those
# winners sit in these R32 matches:
THIRD_MATCH = {"A": "M79", "B": "M85", "D": "M81", "E": "M74", "G": "M82",
               "I": "M77", "K": "M87", "L": "M80"}
LATER = {"r16": [("M89", "M74", "M77"), ("M90", "M73", "M75"), ("M91", "M76", "M78"),
                 ("M92", "M79", "M80"), ("M93", "M83", "M84"), ("M94", "M81", "M82"),
                 ("M95", "M86", "M88"), ("M96", "M85", "M87")],
         "qf": [("M97", "M89", "M90"), ("M98", "M93", "M94"),
                ("M99", "M91", "M92"), ("M100", "M95", "M96")],
         "sf": [("M101", "M97", "M98"), ("M102", "M99", "M100")],
         "final": [("M104", "M101", "M102")]}


# ---- Dixon-Coles match prediction --------------------------------------------------------------
def _pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_matrix(M, home, away, neutral, host_scale):
    s = M["score"]
    ha = 0.0 if neutral else s["home_adv"] * host_scale
    lh = math.exp(s["mu"] + ha + s["attack"].get(home, 0) + s["defence"].get(away, 0))
    la = math.exp(s["mu"] + s["attack"].get(away, 0) + s["defence"].get(home, 0))
    g = [[_pois(i, lh) * _pois(j, la) for j in range(K + 1)] for i in range(K + 1)]
    rho = s.get("rho", 0.0)                      # DC low-score correction
    g[0][0] *= 1 - lh * la * rho
    g[0][1] *= 1 + lh * rho
    g[1][0] *= 1 + la * rho
    g[1][1] *= 1 - rho
    tot = sum(map(sum, g))
    return lh, la, [[c / tot for c in r] for r in g]


def _blend(M, home, away, neutral, p_dc, host_scale):
    """Outcome probs from the bake-off winner: 50/50 DC + precomputed GBM table (model.json
    "ens"). A scaled host edge sits between the table's neutral/full-home entries, so those
    two GBM rows are averaged with the same scale. Falls back to DC if the table is absent."""
    ens = M.get("ens")
    if not ens:
        return p_dc
    tab = ens["probs"]
    if neutral:
        p_gbm = tab.get(f"{home}|{away}|0")
    else:
        p0, p1 = tab.get(f"{home}|{away}|0"), tab.get(f"{home}|{away}|1")
        p_gbm = ([(1 - host_scale) * a + host_scale * b for a, b in zip(p0, p1)]
                 if p0 and p1 else (p1 or p0))
    if not p_gbm:
        return p_dc
    w = float(ens.get("w", 0.5))
    p = [w * a + (1 - w) * b for a, b in zip(p_dc, p_gbm)]
    s = sum(p)
    return [x / s for x in p]


def predict(M, home, away, neutral, host_scale=HOST_ADV_SCALE):
    lh, la, g = score_matrix(M, home, away, neutral, host_scale)
    p_dc = [sum(g[i][j] for i in range(K + 1) for j in range(K + 1) if i > j),
            sum(g[i][i] for i in range(K + 1)), 0.0]
    p_dc[2] = 1 - p_dc[0] - p_dc[1]
    pw, pd, pa = _blend(M, home, away, neutral, p_dc, host_scale)
    hg, ag = max(((i, j) for i in range(K + 1) for j in range(K + 1)), key=lambda c: g[c[0]][c[1]])
    return {"home": home, "away": away, "hg": hg, "ag": ag,
            "p_home": round(pw, 4), "p_draw": round(pd, 4), "p_away": round(pa, 4),
            "lh": round(lh, 3), "la": round(la, 3), "neutral": neutral}


# ---- FIFA 2026 group tiebreakers (Art. 13; head-to-head FIRST among tied teams) ---------------
def _mini(teams, res):
    """Points/GD/GF restricted to matches among `teams`."""
    t = {x: [0, 0, 0] for x in teams}
    for (a, b), (ga, gb) in res.items():
        if a in t and b in t:
            for x, f, ag in ((a, ga, gb), (b, gb, ga)):
                t[x][0] += 3 if f > ag else (1 if f == ag else 0)
                t[x][1] += f - ag
                t[x][2] += f
    return t


def _rank(cluster, res, overall, xkey, depth=0):
    """Order a set of point-tied teams: h2h pts/GD/GF (reapplied recursively among still-tied),
    then overall GD/GF, then expected points/GD (stand-in for conduct & FIFA-ranking steps)."""
    if len(cluster) == 1:
        return list(cluster)
    mini = _mini(cluster, res)
    buckets = defaultdict(list)
    for t in cluster:
        buckets[tuple(mini[t])].append(t)
    if len(buckets) > 1 and depth < 6:
        out = []
        for key in sorted(buckets, reverse=True):
            out += _rank(buckets[key], res, overall, xkey, depth + 1)
        return out
    return sorted(cluster, key=lambda t: (overall[t][1], overall[t][2], xkey[t]), reverse=True)


def rank_group(teams, res, xkey):
    overall = _mini(teams, res)
    by_pts = defaultdict(list)
    for t in teams:
        by_pts[overall[t][0]].append(t)
    order = []
    for pts in sorted(by_pts, reverse=True):
        order += _rank(by_pts[pts], res, overall, xkey)
    return order, overall


# ---- player expectation layer ------------------------------------------------------------------
def _shares(M, team, kind):
    xi = M["squads"][team][:11]
    tab = M["players"]["scoring" if kind == "scoring" else "assist"]
    default = M["players"]["global_score" if kind == "scoring" else "global_assist"]
    w = [max(tab.get(p, default), 1e-6) for p in xi]
    s = sum(w)
    return xi, [x / s for x in w]


def credit(M, team, lam, xg, xa):
    for p, sh in zip(*_shares(M, team, "scoring")):
        xg[p] += lam * sh
    for p, sh in zip(*_shares(M, team, "assist")):
        xa[p] += lam * ASSISTED * sh


# ---- tournament walk -----------------------------------------------------------------------------
def _host(M, t):
    return t in M["meta"].get("hosts", [])


def _oriented(M, a, b):
    """Host plays 'home' with the scaled edge; otherwise neutral in the given order."""
    if _host(M, a) != _host(M, b):
        return ((a, b) if _host(M, a) else (b, a)), False
    return (a, b), True


def play_group_stage(M, groups, host_scale, xg, xa, conceded):
    out = {}
    for gname, teams in groups.items():
        order = [(0, 1), (2, 3), (0, 2), (3, 1), (3, 0), (1, 2)]      # matchdays 1-3
        res, matches = {}, []
        for i, j in order:
            (h, a), neutral = _oriented(M, teams[i], teams[j])
            m = predict(M, h, a, neutral, host_scale)
            matches.append(m)
            res[(h, a)] = (m["hg"], m["ag"])
            credit(M, h, m["lh"], xg, xa)
            credit(M, a, m["la"], xg, xa)
            conceded[h] += m["ag"]
            conceded[a] += m["hg"]
        xpts = {t: 0.0 for t in teams}
        xgd = {t: 0.0 for t in teams}
        for m in matches:
            xpts[m["home"]] += 3 * m["p_home"] + m["p_draw"]
            xpts[m["away"]] += 3 * m["p_away"] + m["p_draw"]
            xgd[m["home"]] += m["lh"] - m["la"]
            xgd[m["away"]] += m["la"] - m["lh"]
        xkey = {t: (round(xpts[t], 4), round(xgd[t], 4)) for t in teams}
        rank, overall = rank_group(teams, res, xkey)
        table = []
        for t in rank:
            w = sum(1 for (h, a), (x, y) in res.items()
                    if (t == h and x > y) or (t == a and y > x))
            d = sum(1 for (h, a), (x, y) in res.items() if t in (h, a) and x == y)
            ga = sum(y if t == h else x for (h, a), (x, y) in res.items() if t in (h, a))
            table.append({"team": t, "w": w, "d": d, "l": 3 - w - d,
                          "gf": overall[t][2], "ga": ga, "gd": overall[t][1],
                          "pts": overall[t][0], "xpts": round(xpts[t], 2)})
        out[gname] = {"matches": matches, "table": table}
    return out


def play_knockout(M, slots, host_scale, xg, xa, conceded):
    """slots: match id -> (home, away). Returns list-of-rounds with winners; extends slots."""
    annex = json.load(open("configs/annex_c.json"))
    rounds = {"r32": []}
    winners = {}

    def ko_match(mid, a, b):
        (h, aw), neutral = _oriented(M, a, b)
        m = predict(M, h, aw, neutral, host_scale)
        pw_cond = m["p_home"] / max(m["p_home"] + m["p_away"], 1e-9)
        m["winner"] = h if pw_cond >= 0.5 else aw
        m["p_win"] = round(pw_cond if m["winner"] == h else 1 - pw_cond, 4)
        if (m["hg"] > m["ag"]) != (m["winner"] == h) and m["hg"] != m["ag"]:
            # blended winner disagrees with the DC modal score: show the most likely score
            # in which that winner actually wins (keeps score and outcome consistent)
            _, _, g = score_matrix(M, h, aw, neutral, host_scale)
            cells = [(i, j) for i in range(K + 1) for j in range(K + 1)
                     if (i > j) == (m["winner"] == h) and i != j]
            m["hg"], m["ag"] = max(cells, key=lambda c: g[c[0]][c[1]])
        m["decided"] = "90min" if m["hg"] != m["ag"] else "et_pens"
        m["id"] = mid
        credit(M, h, m["lh"], xg, xa)
        credit(M, aw, m["la"], xg, xa)
        conceded[h] += m["ag"]
        conceded[aw] += m["hg"]
        winners[mid] = m["winner"]
        return m

    for mid, sa, sb in R32:
        rounds["r32"].append(ko_match(mid, *slots[mid]))
    for rnd, tpl in LATER.items():
        rounds[rnd] = []
        if rnd == "final":                                     # third-place match first (M103)
            l1 = next(x for x in slots["M101"] if x != winners["M101"])
            l2 = next(x for x in slots["M102"] if x != winners["M102"])
            rounds["third_place"] = [ko_match("M103", l1, l2)]
        for mid, pa, pb in tpl:
            slots[mid] = (winners[pa], winners[pb])
            rounds[rnd].append(ko_match(mid, *slots[mid]))
    rounds["champion"] = winners["M104"]
    return rounds, annex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="api/model.json")
    ap.add_argument("--host-scale", type=float, default=HOST_ADV_SCALE)
    ap.add_argument("--out", default="public/tournament.json")
    args = ap.parse_args()
    M = json.load(open(args.model))
    groups = defaultdict(list)
    for t, g in M["meta"]["groups"].items():
        groups[g.replace("Group", "").strip()[:1]].append(t)   # "Group A" -> "A"
    groups = dict(sorted(groups.items()))

    xg, xa = defaultdict(float), defaultdict(float)
    conceded = defaultdict(int)
    stage = play_group_stage(M, groups, args.host_scale, xg, xa, conceded)

    # ---- thirds: rank per Art. 13 (pts, GD, GF; then expected-points stand-in) ----
    thirds = [stage[g]["table"][2] | {"group": g} for g in groups]
    thirds.sort(key=lambda r: (r["pts"], r["gd"], r["gf"], r["xpts"]), reverse=True)
    advanced = thirds[:8]
    key = "".join(sorted(t["group"] for t in advanced))
    annex = json.load(open("configs/annex_c.json"))
    assign = dict(zip(annex["hosts"], annex["table"][key]))    # winner-group -> third's group
    third_team = {t["group"]: t["team"] for t in advanced}

    slots = {}
    pos = {f"{i}{g}": stage[g]["table"][i - 1]["team"] for g in groups for i in (1, 2)}
    for mid, sa, sb in R32:
        if sb == "3rd":
            wg = sa[1]                                          # e.g. "1E" -> group E
            slots[mid] = (pos[sa], third_team[assign[wg]])
        else:
            slots[mid] = (pos[sa], pos[sb])
    bracket, _ = play_knockout(M, slots, args.host_scale, xg, xa, conceded)

    # ---- honors along the modal path ----
    info = M.get("player_info", {})
    played = defaultdict(int)                                   # matches per team on the path
    for g in stage.values():
        for m in g["matches"]:
            played[m["home"]] += 1
            played[m["away"]] += 1
    for rnd in ("r32", "r16", "qf", "sf", "third_place", "final"):
        for m in bracket.get(rnd, []):
            played[m["home"]] += 1
            played[m["away"]] += 1

    def board(tab, k=25):
        rows = sorted(tab.items(), key=lambda x: -x[1])[:k]
        return [{"player": p, "team": info.get(p, {}).get("team", ""),
                 "pos": info.get(p, {}).get("pos", ""), "exp": round(v, 2),
                 "matches": played[info.get(p, {}).get("team", "")]} for p, v in rows]

    deep = [t for t in played if played[t] >= 8]                # semifinalists play 3 group + 5 KO
    glove = None
    if deep:
        team = min(deep, key=lambda t: conceded[t] / played[t])
        gk = next((p for p in M["squads"][team][:11]
                   if info.get(p, {}).get("pos") == "GK"), M["squads"][team][0])
        glove = {"player": gk, "team": team, "conceded": conceded[team],
                 "matches": played[team], "per_match": round(conceded[team] / played[team], 2)}

    total_goals = sum(m["hg"] + m["ag"] for g in stage.values() for m in g["matches"])
    total_goals += sum(m["hg"] + m["ag"] for r in ("r32", "r16", "qf", "sf", "third_place", "final")
                       for m in bracket.get(r, []))

    out = {"meta": {"host_scale": args.host_scale, "annex_c_key": key,
                    "note": "Deterministic most-likely path; conduct/FIFA-ranking tiebreakers "
                            "approximated by expected points."},
           "groups": stage,
           "thirds": {"ranking": [{k: t[k] for k in ("team", "group", "pts", "gd", "gf")}
                                  for t in thirds],
                      "advanced": [t["team"] for t in advanced]},
           "bracket": bracket,
           "honors": {"golden_boot": board(xg), "playmaker": board(xa),
                      "golden_glove": glove, "total_goals": total_goals}}
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=0)

    print(f"champion: {bracket['champion']}")
    fm = bracket["final"][0]
    print(f"final (M104): {fm['home']} {fm['hg']}-{fm['ag']} {fm['away']}"
          f" -> {fm['winner']} ({fm['decided']}, p_win {fm['p_win']})")
    print(f"total goals on modal path: {total_goals}")
    print("golden boot:", ", ".join(f"{r['player']} {r['exp']}" for r in board(xg, 5)))
    print("playmaker  :", ", ".join(f"{r['player']} {r['exp']}" for r in board(xa, 5)))
    if glove:
        print(f"golden glove: {glove['player']} ({glove['team']}, {glove['per_match']}/match)")
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()
