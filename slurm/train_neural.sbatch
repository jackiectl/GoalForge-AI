#!/bin/bash
# Great Lakes GPU job: leave-one-tournament-out eval of the lineup-aware neural Dixon-Coles
# (Phase 3). Owned NEDA L40S nodes = account nmasoud_owned1 + partition spgpu2 + qos arph.
#   sbatch slurm/train_neural.sbatch
#SBATCH --job-name=goalforge-neural
#SBATCH --account=drjieliu99
#SBATCH --partition=gpu-rtx6000,spgpu    # Blackwell RTX 6000 preferred; A40 (spgpu) fallback
#SBATCH --qos=normal
# NEDA-owned alternative (often full at the shared 10-GPU cap):
#   --account=nmasoud_owned1  --partition=spgpu2  --qos=arph
#SBATCH --gpus=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=00:15:00                   # short -> backfills easily into a free GPU slot
#SBATCH --output=slurm/logs/%x-%j.out    # %x=job name, %j=job id
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=ctlang@umich.edu

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-/home/ctlang/GoalForge_AI}"
mkdir -p slurm/logs

# Big/regenerable caches (the StatsBomb lineup dataset) live on NEDA scratch.
export GOALFORGE_DATA_DIR="${GOALFORGE_DATA_DIR:-/scratch/nmasoud_owned_root/nmasoud_owned1/ctlang/gf_cache/data}"

# torch env (built separately: torch 2.5.1+cu121; goalforge installed editable, --no-deps).
# The pip CUDA wheel bundles its own CUDA runtime, so no `module load cuda` is needed.
GPUPY=/home/ctlang/envs/goalforge-gpu/bin/python

nvidia-smi || true
"$GPUPY" -c "import torch; print('cuda available:', torch.cuda.is_available(),
             '| device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
echo "========== Phase 3: lineup-aware neural Dixon-Coles (LOTO) =========="
"$GPUPY" scripts/train_neural.py --device cuda
echo "========== Phase 3 follow-up (1): strong DC prior + lineup deltas =========="
"$GPUPY" scripts/train_neural_v2.py --device cuda
