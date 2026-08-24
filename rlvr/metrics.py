"""The reused ruler (docs/07-rescope-verifier-adequacy.md, Phase A).

Pure stdlib + numpy. No repo-specific assumptions: these functions operate on
plain (n, c) sample counts and float sequences so they compose across every
later phase (pass@k on the base model, pass@k under RL, mutation-catch-rate
CIs in Phase B, ...).
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Sequence

import numpy as np

__all__ = [
    "pass_at_k",
    "mean_pass_at_k",
    "bootstrap_ci",
    "wilson_interval",
]


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k estimator (Chen et al. 2107.03374, eq. 1).

    pass@k = 1 - C(n-c, k) / C(n, k)

    Computed via the standard numerically stable product form (as in the
    HumanEval reference implementation) rather than naive factorials, which
    overflow / lose precision for even moderate n.
    """
    if not (0 <= c <= n):
        raise ValueError(f"require 0 <= c <= n, got c={c}, n={n}")
    if not (1 <= k <= n):
        raise ValueError(f"require 1 <= k <= n, got k={k}, n={n}")

    if c == 0:
        return 0.0
    if n - c < k:
        # Fewer than k incorrect samples exist, so every k-subset contains
        # at least one correct sample: C(n-c, k) == 0.
        return 1.0

    # 1 - prod_{i=n-c+1}^{n} (1 - k / i)
    return 1.0 - math.prod(1.0 - k / i for i in range(n - c + 1, n + 1))


def mean_pass_at_k(samples: Sequence[tuple[int, int]], k: int) -> float:
    """Mean of pass_at_k(n_i, c_i, k) over a sequence of (n, c) problems."""
    values = [pass_at_k(n, c, k) for n, c in samples]
    if not values:
        raise ValueError("samples must be non-empty")
    return sum(values) / len(values)


def bootstrap_ci(
    per_problem_values: Sequence[float],
    *,
    n_boot: int = 10_000,
    alpha: float = 0.05,
    seed: int,
) -> tuple[float, float]:
    """Percentile bootstrap CI over per-problem values.

    Resamples problems (rows) with replacement, n_boot times, and returns the
    [alpha/2, 1 - alpha/2] percentiles of the resampled means. Deterministic
    for a given seed (numpy.random.default_rng(seed)).
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    values = np.asarray(per_problem_values, dtype=float)
    if values.size == 0:
        raise ValueError("per_problem_values must be non-empty")

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, values.size, size=(n_boot, values.size))
    boot_means = values[idx].mean(axis=1)

    lo = float(np.percentile(boot_means, 100 * alpha / 2))
    hi = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return lo, hi


def wilson_interval(
    successes: int, trials: int, *, alpha: float = 0.05
) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used as the CI for mutation catch-rates in Phase B. Closed-form interval
    from Wilson (1927), "Probable Inference, the Law of Succession, and
    Statistical Inference", JASA 22(158). Reference value (successes=8,
    trials=10, alpha=0.05 -> approx (0.490, 0.943)) derived from this closed
    form by hand and cross-checked against the implementation in
    tests/test_metrics.py::TestWilsonInterval::test_known_published_value
    (not independently sourced from a third-party worked example).
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if trials <= 0:
        raise ValueError(f"trials must be > 0, got {trials}")
    if not (0 <= successes <= trials):
        raise ValueError(f"require 0 <= successes <= trials, got {successes}, {trials}")

    z = NormalDist().inv_cdf(1 - alpha / 2)
    z2 = z * z
    phat = successes / trials

    denom = 1 + z2 / trials
    center = phat + z2 / (2 * trials)
    half_width = z * math.sqrt(phat * (1 - phat) / trials + z2 / (4 * trials**2))

    lo = (center - half_width) / denom
    hi = (center + half_width) / denom
    return max(0.0, lo), min(1.0, hi)
