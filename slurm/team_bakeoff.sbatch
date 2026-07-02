#!/bin/bash
#SBATCH --job-name=gf-bakeoff
#SBATCH --account=drjieliu99
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=03:00:00
#SBATCH --output=slurm/logs/%x-%j.log

# Team-layer bake-off (DC vs GBM vs GBM-Poisson vs MLP vs ensembles), walk-forward over
# 11 major tournaments. CPU only: tabular models this small gain nothing from a GPU.
cd "${SLURM_SUBMIT_DIR:-/home/ctlang/GoalForge_AI}"
mkdir -p slurm/logs
export GOALFORGE_DATA_DIR="${GOALFORGE_DATA_DIR:-/scratch/nmasoud_owned_root/nmasoud_owned1/ctlang/gf_cache/data}"
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=8

# goalforge-gpu env has torch+lightgbm+sklearn and goalforge installed editable
/home/ctlang/envs/goalforge-gpu/bin/python scripts/team_bakeoff.py
