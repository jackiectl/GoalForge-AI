# GoalForge web app (Streamlit)

Interactive UI over the `goalforge` package: choose a data source, pick two teams, edit the
starting XIs, and see the predicted scoreline, win/draw/win probabilities, and per-player
anytime-scorer / assist probabilities.

## Run
```bash
source slurm/env_setup.sh                       # streamlit 1.30 ships with the anaconda module
python -m streamlit run app/streamlit_app.py
```
> Use **`python -m streamlit run`**, not the bare `streamlit` console script — the anaconda
> launcher's entry point is stale and errors with `No module named 'streamlit.cli'`.

On Great Lakes (headless login node) run it on a port and tunnel from your laptop:
```bash
# on Great Lakes
python -m streamlit run app/streamlit_app.py --server.headless true --server.port 8501
# on your laptop
ssh -N -L 8501:localhost:8501 <uniqname>@greatlakes.arc-ts.umich.edu
# then open http://localhost:8501
```
The **StatsBomb World Cup 2022** source pulls ~64 matches on first load (cached afterwards);
the **Synthetic demo** source is instant and offline.

> Roadmap: this Streamlit app is the first UI. A FastAPI backend + web frontend is planned
> next for a more polished, deployable version (see [docs/workflow.md](../docs/workflow.md)).
