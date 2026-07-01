"""GoalForge Streamlit app — predict a match from two starting lineups.

    streamlit run app/streamlit_app.py

Pick a data source (synthetic demo or real StatsBomb World Cup 2022), choose two teams and
edit their XIs, then see the predicted scoreline, win/draw/win probabilities, and per-player
anytime-scorer / assist probabilities. Thin UI over the ``goalforge`` package.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from goalforge.models.player import PlayerRatings
from goalforge.models.scoreline import DixonColesModel
from goalforge.prediction.predict_match import predict_match

SYNTHETIC = "Synthetic demo"
WORLDCUP = "StatsBomb World Cup 2022"


def _load_and_fit(source: str):
    """Load data and fit the scoreline + player models (no Streamlit calls -> unit-testable)."""
    if source == SYNTHETIC:
        from goalforge.data.synthetic import generate_dataset
        data = generate_dataset()
        dc = DixonColesModel().fit(data.matches, half_life_days=180)
        positions = {p.name: p.position for r in data.rosters.values() for p in r}
        ratings = PlayerRatings().fit(data.appearances, data.goals, positions=positions)
        return data, dc, ratings, False
    from goalforge.data.statsbomb import WORLD_CUP_2022, load_competition
    data = load_competition(*WORLD_CUP_2022, verbose=False)
    dc = DixonColesModel().fit(data.matches)
    ratings = PlayerRatings(prior_strength=3.0).fit(data.appearances, data.goals)
    return data, dc, ratings, True


@st.cache_resource(show_spinner=False)
def load_and_fit(source: str):
    return _load_and_fit(source)


def squad(data, team: str) -> list[str]:
    """Players who appeared for a team, most-used first (default 'likely XI' = top 11)."""
    sub = data.appearances[data.appearances.team == team]
    return list(sub.groupby("player").minutes.sum().sort_values(ascending=False).index)


def _prob_table(pairs, label: str) -> pd.DataFrame:
    return pd.DataFrame([(n, 100.0 * p) for n, p in pairs[:8]], columns=[label, "P(≥1)"])


def _prob_cfg():
    if hasattr(st, "column_config"):
        return {"P(≥1)": st.column_config.ProgressColumn("P(≥1)", format="%.0f%%",
                                                         min_value=0, max_value=100)}
    return None


def render(pred) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{pred.home_team} win", f"{pred.prob_home:.0%}")
    c2.metric("Draw", f"{pred.prob_draw:.0%}")
    c3.metric(f"{pred.away_team} win", f"{pred.prob_away:.0%}")
    (h, a), p = pred.top_scores[0]
    c1.metric("Most likely score", f"{h}–{a}", f"{p:.1%}")
    c2.metric(f"{pred.home_team} exp. goals", f"{pred.exp_home_goals:.2f}")
    c3.metric(f"{pred.away_team} exp. goals", f"{pred.exp_away_goals:.2f}")

    st.subheader("Scoreline probabilities")
    K = 6
    M = pred.score_matrix[:K, :K]
    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(M, cmap="Greens", origin="upper")
    ax.set_xlabel(f"{pred.away_team} goals")
    ax.set_ylabel(f"{pred.home_team} goals")
    ax.set_xticks(range(K))
    ax.set_yticks(range(K))
    for i in range(K):
        for j in range(K):
            ax.text(j, i, f"{M[i, j]:.0%}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, fraction=0.046)
    st.pyplot(fig)

    cfg = _prob_cfg()
    left, right = st.columns(2)
    left.subheader(f"{pred.home_team} — scorers")
    left.dataframe(_prob_table(pred.home_scorers, "Player"), column_config=cfg, hide_index=True)
    right.subheader(f"{pred.away_team} — scorers")
    right.dataframe(_prob_table(pred.away_scorers, "Player"), column_config=cfg, hide_index=True)
    left.subheader(f"{pred.home_team} — assisters")
    left.dataframe(_prob_table(pred.home_assisters, "Player"), column_config=cfg, hide_index=True)
    right.subheader(f"{pred.away_team} — assisters")
    right.dataframe(_prob_table(pred.away_assisters, "Player"), column_config=cfg, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="GoalForge", page_icon="⚽", layout="wide")
    st.title("⚽ GoalForge — match predictor")
    st.caption("Scoreline, scorers and assisters from two starting lineups. "
               "Real data: StatsBomb open data (attribution: StatsBomb).")

    source = st.sidebar.selectbox("Data source", [SYNTHETIC, WORLDCUP])
    n_sims = st.sidebar.select_slider("Simulations", [10_000, 20_000, 50_000, 100_000],
                                      value=50_000)
    with st.spinner("Loading data & fitting models… (World Cup pulls ~64 matches on first run)"):
        data, dc, ratings, neutral_default = load_and_fit(source)
    neutral = st.sidebar.checkbox("Neutral venue", value=neutral_default)

    teams = data.teams
    c1, c2 = st.columns(2)
    home = c1.selectbox("Home team", teams, index=0)
    away = c2.selectbox("Away team", teams, index=min(1, len(teams) - 1))
    home_xi = c1.multiselect(f"{home} starting XI", squad(data, home), default=squad(data, home)[:11])
    away_xi = c2.multiselect(f"{away} starting XI", squad(data, away), default=squad(data, away)[:11])

    if st.button("Predict", type="primary"):
        if home == away:
            st.error("Pick two different teams.")
            return
        if not home_xi or not away_xi:
            st.error("Each team needs at least one player.")
            return
        hpen = max(home_xi, key=lambda n: ratings.rate(n, "scoring"))
        apen = max(away_xi, key=lambda n: ratings.rate(n, "scoring"))
        hl = ratings.build_lineup(home, home_xi, pen_taker=hpen)
        al = ratings.build_lineup(away, away_xi, pen_taker=apen)
        pred = predict_match(hl, al, dc, neutral=neutral, n_sims=int(n_sims),
                             rng=np.random.default_rng(0))
        render(pred)


if __name__ == "__main__":
    main()
