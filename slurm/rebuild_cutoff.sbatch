#!/bin/bash
#SBATCH --job-name=gf-rebuild
#SBATCH --account=drjieliu99
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=slurm/logs/%x-%j.log

# Rebuild the whole deployed model chain with every layer cut off at the 2026 World Cup
# kick-off (2026-06-11), so the published forecast is a genuine PRE-tournament prediction —
# the martj42 cache now contains real 2026 WC results, which must not leak into training.
#   DC checkpoint -> api/model.json -> ensemble table -> 20k Monte-Carlo -> tournament walk
set -e
cd "${SLURM_SUBMIT_DIR:-/home/ctlang/GoalForge_AI}"
mkdir -p slurm/logs
export GOALFORGE_DATA_DIR="${GOALFORGE_DATA_DIR:-/scratch/nmasoud_owned_root/nmasoud_owned1/ctlang/gf_cache/data}"
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=8

CUTOFF=2026-06-11
VENVPY=.venv/bin/python                                # scipy+statsbombpy+pyarrow
GPUPY=/home/ctlang/envs/goalforge-gpu/bin/python       # lightgbm+sklearn

module load python3.11-anaconda/2024.02 2>/dev/null || true

echo "===== [1/8] refit DC checkpoint (cutoff $CUTOFF) ====="
$VENVPY scripts/train.py --cutoff $CUTOFF

echo "===== [2/8] rebuild api/model.json (48 squads + player layer) ====="
$VENVPY scripts/build_wc2026_model.py

echo "===== [3/8] ensemble outcome table (GBM, cutoff $CUTOFF) ====="
$GPUPY scripts/build_ens_layer.py --cutoff $CUTOFF

echo "===== [4/8] public odds table for the Prediction Game (-> public/odds.json) ====="
$VENVPY scripts/build_odds_public.py

echo "===== [5/8] 20k Monte-Carlo forecast ====="
$VENVPY scripts/simulate_wc2026.py --sims 20000 --host-scale 0.5
cp reports/wc2026_forecast.json public/forecast.json

echo "===== [6/8] deterministic tournament walk ====="
$VENVPY scripts/build_tournament.py

echo "===== [7/8] real-results comparison (prediction vs actual) ====="
$VENVPY scripts/build_actual.py

echo "===== [8/8] live re-forecast (refit incl. 2026 results, re-walk real bracket) ====="
$VENVPY scripts/build_live.py

echo "===== rebuild complete ====="
ls -la api/model.json public/forecast.json public/tournament.json public/actual.json public/live.json public/odds.json
