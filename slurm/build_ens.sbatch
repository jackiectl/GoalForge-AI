#!/bin/bash
#SBATCH --job-name=gf-ens
#SBATCH --account=drjieliu99
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=slurm/logs/%x-%j.log

# Fit the production GBM outcome model on full history and precompute the 48x47x2 ensemble
# probability table into api/model.json (see scripts/build_ens_layer.py). CPU only.
cd "${SLURM_SUBMIT_DIR:-/home/ctlang/GoalForge_AI}"
mkdir -p slurm/logs
export GOALFORGE_DATA_DIR="${GOALFORGE_DATA_DIR:-/scratch/nmasoud_owned_root/nmasoud_owned1/ctlang/gf_cache/data}"
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=8

/home/ctlang/envs/goalforge-gpu/bin/python scripts/build_ens_layer.py
