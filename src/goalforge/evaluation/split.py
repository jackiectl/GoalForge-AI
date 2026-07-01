"""Temporal train/validation/test splitting (chronological, never random).

Random splits leak future team form into the past. Everything here splits by date so the
protocol mirrors deployment: fit on the past, predict the future.
"""
from __future__ import annotations

import pandas as pd


def temporal_split(matches: pd.DataFrame, val_frac: float = 0.15, test_frac: float = 0.15):
    """Split matches chronologically into (train, val, test) DataFrames."""
    df = matches.sort_values("date").reset_index(drop=True)
    n = len(df)
    n_test = int(n * test_frac)
    n_val = int(n * val_frac)
    n_train = n - n_val - n_test
    return df.iloc[:n_train], df.iloc[n_train:n_train + n_val], df.iloc[n_train + n_val:]
