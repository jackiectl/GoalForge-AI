#!/usr/bin/env bash
# Activate the GoalForge environment on Great Lakes:
#   source slurm/env_setup.sh
# Uses the anaconda module (numpy/scipy/pandas/... scientific stack) plus a project-local
# .venv created with --system-site-packages that reuses it. (Sourced -> no `set -e`.)

# 1) Scientific Python from Lmod.
module load python3.11-anaconda/2024.02 2>/dev/null || module load python 2>/dev/null || true

# 2) Project virtualenv (see README for one-time creation).
_root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
VENV="${GOALFORGE_VENV:-$_root/.venv}"
if [ -f "$VENV/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  echo "[env_setup] goalforge ready: $(python --version 2>&1)"
else
  echo "[env_setup] no venv at $VENV — create it once with:" >&2
  echo "  module load python3.11-anaconda/2024.02" >&2
  echo "  python -m venv --system-site-packages \"$VENV\" && source \"$VENV/bin/activate\"" >&2
  echo "  pip install -e . && pip install statsbombpy" >&2
  return 1 2>/dev/null || exit 1
fi

# 3) Storage: keep GoalForge's $HOME footprint < 5 GB ($HOME is Turbo-backed, shared with
# other projects). Big/regenerable data caches -> NEDA scratch (10 TB, owned; fast, but
# auto-purged ~60d and not backed up). Small checkpoints stay in $HOME/models (persistent).
# Never store project files under drjieliu (Turbo/Scratch) or Lighthouse.
export GOALFORGE_DATA_DIR="${GOALFORGE_DATA_DIR:-/scratch/nmasoud_owned_root/nmasoud_owned1/ctlang/gf_cache/data}"
mkdir -p "$GOALFORGE_DATA_DIR" 2>/dev/null || true
# export GOALFORGE_MODELS_DIR=...   # keep default $HOME/models unless checkpoints get large

# 4) (GPU jobs) load a CUDA toolkit matching your framework build, e.g.:
# module load cuda/12.6.3
