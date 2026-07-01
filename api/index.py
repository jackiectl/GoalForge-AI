"""Vercel serverless entry — exposes the FastAPI app (ASGI) for Vercel's Python runtime.

Adds ``src/`` to the path and points the app at the committed ``model.json``, then re-exports
the FastAPI ``app``. The whole prediction path is NumPy-only, so this function stays well under
Vercel's serverless size limit.
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
os.environ.setdefault("GOALFORGE_MODEL_JSON", str(_ROOT / "model.json"))

from goalforge.api.app import app  # noqa: E402

__all__ = ["app"]
