from goalforge.data.synthetic import generate_dataset
from goalforge.evaluation.split import temporal_split


def test_temporal_split_sizes_and_chronology():
    d = generate_dataset(n_teams=10, seed=0)
    tr, va, te = temporal_split(d.matches, 0.15, 0.15)
    assert len(tr) + len(va) + len(te) == len(d.matches)
    assert len(tr) > len(va) and len(tr) > len(te)
    # strictly chronological: train <= val <= test in time (no leakage)
    assert tr.date.max() <= va.date.min()
    assert va.date.max() <= te.date.min()
