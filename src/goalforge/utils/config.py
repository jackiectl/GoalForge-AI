"""Config loading and reproducible RNG helpers."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

# repo root = .../src/goalforge/utils/config.py -> parents[3]
DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "default.yaml"


def load_config(path: str | Path | None = None) -> dict:
    """Load a YAML config; returns {} if the file is missing."""
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.exists():
        return {}
    with open(p) as f:
        return yaml.safe_load(f) or {}


def get_rng(seed: int = 42) -> np.random.Generator:
    """Return a seeded NumPy Generator for reproducible sampling."""
    return np.random.default_rng(seed)
