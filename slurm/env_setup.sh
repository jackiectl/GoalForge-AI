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

# 3) Storage: artifacts default to the repo under $HOME (data/, models/) — all small for now.
# Nothing is stored under drjieliu (Turbo/Scratch) or Lighthouse. If big regenerable caches
# are ever needed, the nmasoud scratch (10 TB, owned by you) is available — set e.g.:
# export GOALFORGE_DATA_DIR=/scratch/nmasoud_owned_root/nmasoud_owned1/ctlang/gf_cache
# (Scratch is fast but auto-purged ~60d and not backed up; keep checkpoints in $HOME.)

# 4) (GPU jobs) load a CUDA toolkit matching your framework build, e.g.:
# module load cuda/12.6.3
