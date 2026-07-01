"""Run the full Phase-0 pipeline on synthetic data end-to-end.

    python scripts/run_pipeline.py

generate synthetic competition -> backtest the scoreline model -> fit player ratings ->
predict a sample match (scoreline + scorers + assisters).
"""
from goalforge.data.synthetic import generate_dataset
from goalforge.evaluation.backtest import walk_forward_backtest
from goalforge.models.player import PlayerRatings
from goalforge.models.scoreline import DixonColesModel
from goalforge.prediction.predict_match import predict_match
from goalforge.utils import get_rng


def main() -> None:
    data = generate_dataset()
    print(f"[data] {len(data.matches)} matches | {len(data.teams)} teams | "
          f"{len(data.goals)} goals | {len(data.appearances)} appearances")

    bt = walk_forward_backtest(data.matches, n_splits=4)
    print(f"[backtest] RPS: model {bt['model_rps']:.4f} vs baseline {bt['baseline_rps']:.4f} "
          f"(n={bt['n']})  -> {'model better' if bt['model_rps'] < bt['baseline_rps'] else 'baseline better'}")

    dc = DixonColesModel().fit(data.matches, half_life_days=180)
    positions = {p.name: p.position for roster in data.rosters.values() for p in roster}
    ratings = PlayerRatings().fit(data.appearances, data.goals, positions=positions)

    def make(team):
        names = ratings.most_used_xi(data.appearances, team)
        pen = max(names, key=lambda nm: ratings.rate(nm, "scoring"))
        return ratings.build_lineup(team, names, pen_taker=pen)

    pred = predict_match(make(data.teams[0]), make(data.teams[1]), dc,
                         n_sims=50_000, rng=get_rng(0))
    print("[prediction]")
    print(pred.summary())


if __name__ == "__main__":
    main()
