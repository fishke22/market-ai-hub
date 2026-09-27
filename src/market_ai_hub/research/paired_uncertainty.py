"""Paired uncertainty helpers for same-origin model comparisons."""
from __future__ import annotations

import numpy as np

PAIRWISE_BOOTSTRAP_REPLICATES = 1000
PAIRWISE_BOOTSTRAP_CONFIDENCE = 0.95
PAIRWISE_MIN_CI_SAMPLES = 5
PAIRWISE_STABLE_SAMPLE = 30
PAIRWISE_BOOTSTRAP_SEED = 20260927


def overlap_block_length(origins: list[int], steps: int) -> int:
    if not origins:
        return 1
    ordered = sorted(int(x) for x in origins)
    horizon = max(1, int(steps))
    best = 1
    right = 0
    for left, origin in enumerate(ordered):
        if right < left:
            right = left
        while right + 1 < len(ordered) and ordered[right + 1] < origin + horizon:
            right += 1
        best = max(best, right - left + 1)
    return min(best, len(ordered))


def paired_block_bootstrap_ci(
    deltas: np.ndarray,
    origins: list[int],
    steps: int,
    *,
    replicates: int = PAIRWISE_BOOTSTRAP_REPLICATES,
    confidence: float = PAIRWISE_BOOTSTRAP_CONFIDENCE,
    seed: int = PAIRWISE_BOOTSTRAP_SEED,
) -> dict:
    values = np.asarray(deltas, dtype=float)
    n = int(values.size)
    block_length = overlap_block_length(origins, steps)
    status = (
        "INSUFFICIENT_PAIRED_SAMPLE" if n < PAIRWISE_MIN_CI_SAMPLES
        else "EXPLORATORY_ONLY" if n < PAIRWISE_STABLE_SAMPLE
        else "ESTIMATED"
    )
    out = {
        "bootstrap_replicates": int(replicates),
        "bootstrap_block_length": int(block_length),
        "delta_ci_confidence": float(confidence),
        "uncertainty_status": status,
        "delta_ci_lower": None,
        "delta_ci_upper": None,
    }
    if n < PAIRWISE_MIN_CI_SAMPLES or not np.isfinite(values).all():
        return out
    blocks = int(np.ceil(n / block_length))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(replicates, blocks))
    offsets = np.arange(block_length, dtype=int)
    sample_idx = (starts[:, :, None] + offsets[None, None, :]) % n
    sample_idx = sample_idx.reshape(replicates, -1)[:, :n]
    means = values[sample_idx].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lo = float(np.quantile(means, alpha))
    hi = float(np.quantile(means, 1.0 - alpha))
    out["delta_ci_lower"] = lo if np.isfinite(lo) else None
    out["delta_ci_upper"] = hi if np.isfinite(hi) else None
    return out
