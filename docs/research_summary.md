# GoalForge — research summary (honest findings)

Predicting a soccer match's **scoreline, scorers, and assisters** from the two starting XIs,
first target the 2026 World Cup. What follows is what actually held up under honest evaluation —
including the things that *didn't* work, which are the more useful half.

## Evaluation methodology (the measuring stick)
- **Leave-one-tournament-out (LOTO)** over 6 modern international tournaments (WC 2018/2022,
  Euro 2020/2024, Copa 2024, AFCON 2023): train on five, predict the sixth. This is the regime
  that matters for a World Cup — a fresh tournament with squad turnover.
- Scoreline: **RPS / log-loss / ECE** vs Elo and base-rate. Player layer: **recall@k** (is the
  real scorer/assister in the team's top-k?) + calibration, vs position / rate baselines.
- Every model's player rates / team strengths are fit **leakage-free** (the held-out tournament
  is excluded, martj42 by date+teams). No in-sample or leaky numbers are reported as performance.

## What's deployed (and why)
| Layer | Method | Data |
|---|---|---|
| Scoreline | Dixon-Coles (attack/defence, home adv, ρ) | martj42 international results, ~16k matches |
| Scorer | goals/caps blended with **club xG**, shrunk to a position prior | Wikipedia caps/goals + Understat |
| Assister | **club xA/90** (chance creation) where available, else position prior | Understat (5 leagues, 2018-2025) |
| Squads / XI | official 26-man rosters; default XI = most-capped per position (4-3-3) | Wikipedia 2026 |
Venue: neutral by default; hosts USA/Canada/Mexico get home advantage. Served on Vercel as a
230 KB JSON with pure-stdlib analytic inference (no torch/GPU at serve time).

## Findings — what worked
1. **Team-strength Dixon-Coles is the right scoreline model.** With the full martj42 history
   (leakage-free) it reaches **RPS 0.2004 on LOTO, beating Elo (0.2029)** and the base rate, and
   is already **well-calibrated (ECE 0.057)** — no calibration fix needed.
2. **Expected assists (xA) beat sparse actual-assist counts** for ranking assisters
   (r@3 45.4% vs 38.9%): chance creation is ~10× denser signal. This is the one clear methodological win.
3. **Position-aware shrinkage** of player rates beats shrinking to a global mean (and beats a
   plain position prior at r@1). Individual history helps *at the top of the ranking*.
4. **Free data engineering lifted coverage.** FBref/Understat block the cluster's datacenter IP,
   but headless-Chromium (Playwright) runs on the cluster and reads Understat's JS-loaded data;
   this raised club xG/xA coverage of the 2026 squads from 33% → 54% and added current form
   (young stars, latest clubs).

## Findings — what did NOT work (equally important)
1. **A lineup-aware neural scoreline model does not beat Dixon-Coles** (LOTO RPS ≈ 0.201 either
   way), even with a strong team prior and 3× more lineup data (club matches). The actual XI adds
   no signal to the *score* beyond team strength.
2. **Gradient boosting, learning-to-rank (LGBMRanker), and neural MLPs on rich player features
   all lose to the simple rate/position baselines** for ranking scorers/assisters — even after
   adding xGChain/xGBuildup and correcting the objective. Scoring/assisting is fundamentally a
   *rate*; a classifier on the rare per-match binary (~9% base rate) overfits the thin data.

## The overarching, honest theme
International-tournament outcomes are **high-variance and low-signal on small samples**. Across
every layer, **well-chosen simple models + good features beat added model capacity.** More data
helped by improving *coverage of the simple model*, not by making complex models win. The value
of this project is not a fancy model — it is a **rigorous, honest evaluation harness** and a set
of **reproducible findings** (including negative ones) about where signal does and doesn't exist.

## Honest limitations / where AI *could* eventually help
- Club data covers ~54% of 2026 players (top-5 leagues only); non-top-5-league players fall back
  to internationals + position. Comprehensive multi-league event data would extend the wins.
- The genuine "structure" opportunity is **who-assists-whom** (passing networks), but for the
  *who-assists* ranking metric that structure is already captured by xA.
- A calibrated Bayesian layer / richer player representations may pay off **only** with materially
  more and cleaner event data than is freely available at a datacenter IP today.

Reproduce: `docs/evaluation.md` §1-12; scripts `train.py`, `train_neural{,_v2,_v3}.py`,
`evaluate_players.py`, `evaluate_assists.py`, `player_ml.py`, `fetch_understat_pw.py`,
`build_player_form.py`, `build_wc2026_model.py`.
