"""Paired-seed summary helpers."""
import hashlib
import numpy as np

def rng_for(seed, label):
    number = int.from_bytes(hashlib.sha256(str(label).encode()).digest()[:8], "little")
    return np.random.default_rng(np.random.SeedSequence([seed, number]))

def ci_mean(values, rng, reps):
    a = np.asarray(values, float)
    a = a[np.isfinite(a)]
    if not len(a):
        return dict(n=0, mean=np.nan, std=np.nan, ci95_low=np.nan, ci95_high=np.nan)
    mean = float(a.mean())
    if len(a) < 2:
        return dict(n=len(a), mean=mean, std=np.nan, ci95_low=np.nan, ci95_high=np.nan)
    boots = a[rng.integers(0, len(a), size=(reps, len(a)))].mean(axis=1)
    lo, hi = np.quantile(boots, [.025, .975])
    return dict(n=len(a), mean=mean, std=float(a.std(ddof=1)), ci95_low=float(lo), ci95_high=float(hi))
