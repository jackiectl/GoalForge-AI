# Deploying GoalForge on Vercel

The current (statistical) model is tiny (`model.json` ≈ 100 KB) and inference is pure NumPy, so
the whole app — static frontend **and** the prediction API — runs on Vercel serverless.

## What's here
- `web/` — static frontend (served at `/`).
- `api/index.py` — Vercel Python function exposing the FastAPI app; serves `/api/*` and `web/`.
  NumPy-only inference from `model.json` (no SciPy / Pandas / pickle / torch).
- `model.json` — the exported model (regenerate with `python scripts/export_model.py`).
- `vercel.json` — routes all requests to the function; bundles `src/`, `web/`, `model.json`.
- `requirements.txt` — minimal runtime deps (numpy, fastapi, uvicorn). Full dev deps are in
  `requirements-dev.txt` / `environment.yml`.

## Connect (do this on Vercel — you handle the GitHub↔Vercel link)
1. Push this repo to GitHub (done).
2. vercel.com → **New Project** → import the `GoalForge-AI` repo.
3. Framework preset: **Other**; root directory: repo root; no build/output overrides (the
   `vercel.json` handles routing). Vercel installs `requirements.txt` and builds the function.
4. **Deploy** → public URL (e.g. `goalforge-ai.vercel.app`). Every `git push` auto-redeploys.

If the build complains about missing modules/files, check `vercel.json`'s `includeFiles` and the
Python version — tell me the build log and I'll adjust.

## Updating the model
Retrain on Great Lakes, re-export, commit:
```bash
python scripts/train.py
python scripts/export_model.py     # writes model.json
git add model.json && git commit -m "update model" && git push
```
Vercel redeploys with the new `model.json`.

## Endgame (after Phase 3)
Once neural models arrive, the heavy model moves to a **Hugging Face Space** (runs torch + GPU);
Vercel keeps serving the frontend, calling the HF backend. See docs/workflow.md.
