"""Tests for rlvr.metrics — the reused ruler (docs/07 Phase A)."""

from __future__ import annotations

import itertools
import math

import pytest
from hypothesis import given, settings, strategies as st

from rlvr.metrics import bootstrap_ci, mean_pass_at_k, pass_at_k, wilson_interval


# ---------------------------------------------------------------------------
# pass_at_k — exact values
# ---------------------------------------------------------------------------


class TestPassAtKExact:
    def test_all_correct_is_one(self):
        for n in range(1, 9):
            for k in range(1, n + 1):
                assert pass_at_k(n, n, k) == 1.0

    def test_none_correct_is_zero(self):
        for n in range(1, 9):
            for k in range(1, n + 1):
                assert pass_at_k(n, 0, k) == 0.0

    def test_hand_computed_case(self):
        # n=10, c=3, k=1: pass@1 with 3/10 correct samples reduces to c/n.
        assert pass_at_k(10, 3, 1) == pytest.approx(0.3, abs=1e-12)

    def test_k_equals_n_iff_c_ge_1(self):
        n = 7
        for c in range(0, n + 1):
            result = pass_at_k(n, c, n)
            if c >= 1:
                assert result == 1.0
            else:
                assert result == 0.0

    def test_red_demo_case_n5_c2_k3(self):
        # Unbiased: 1 - C(3,3)/C(5,3) = 1 - 1/10 = 0.9
        # Biased naive 1-(1-c/n)**k would give ~0.784 — see PR body for the
        # captured red-run output demonstrating this test fails against it.
        assert pass_at_k(5, 2, 3) == pytest.approx(0.9, abs=1e-12)

    def test_invalid_c_raises(self):
        with pytest.raises(ValueError):
            pass_at_k(5, -1, 1)
        with pytest.raises(ValueError):
            pass_at_k(5, 6, 1)

    def test_invalid_k_raises(self):
        with pytest.raises(ValueError):
            pass_at_k(5, 2, 0)
        with pytest.raises(ValueError):
            pass_at_k(5, 2, 6)


# ---------------------------------------------------------------------------
# pass_at_k — brute-force cross-check via exhaustive enumeration
# ---------------------------------------------------------------------------


def _brute_force_pass_at_k(n: int, c: int, k: int) -> float:
    """Exhaustively enumerate all C(n,k) k-subsets of range(n) and compute
    the fraction that contain at least one of the c "correct" indices
    (taken WLOG as indices 0..c-1)."""
    correct = set(range(c))
    subsets = list(itertools.combinations(range(n), k))
    hits = sum(1 for subset in subsets if correct.intersection(subset))
    return hits / len(subsets)


class TestPassAtKBruteForce:
    def test_matches_exhaustive_enumeration(self):
        cases = 0
        for n in range(1, 9):
            for c in range(0, n + 1):
                for k in range(1, n + 1):
                    expected = _brute_force_pass_at_k(n, c, k)
                    actual = pass_at_k(n, c, k)
                    assert actual == pytest.approx(expected, abs=1e-9), (
                        f"n={n}, c={c}, k={k}: expected {expected}, got {actual}"
                    )
                    cases += 1
        # Sanity: we actually exercised a non-trivial number of cases.
        assert cases > 100


# ---------------------------------------------------------------------------
# pass_at_k — hypothesis properties
# ---------------------------------------------------------------------------


@st.composite
def _n_c_k(draw, max_n: int = 60):
    n = draw(st.integers(min_value=1, max_value=max_n))
    c = draw(st.integers(min_value=0, max_value=n))
    k = draw(st.integers(min_value=1, max_value=n))
    return n, c, k


class TestPassAtKProperties:
    @settings(max_examples=200, deadline=None)
    @given(_n_c_k())
    def test_result_in_unit_interval(self, n_c_k):
        n, c, k = n_c_k
        result = pass_at_k(n, c, k)
        assert -1e-12 <= result <= 1 + 1e-12

    @settings(max_examples=200, deadline=None)
    @given(st.integers(min_value=1, max_value=40), st.integers(min_value=1, max_value=40))
    def test_monotone_nondecreasing_in_c(self, n, k):
        k = min(k, n)
        prev = -1.0
        for c in range(0, n + 1):
            result = pass_at_k(n, c, k)
            assert result >= prev - 1e-12
            prev = result

    @settings(max_examples=200, deadline=None)
    @given(st.integers(min_value=1, max_value=40), st.integers(min_value=0, max_value=40))
    def test_monotone_nondecreasing_in_k(self, n, c):
        c = min(c, n)
        prev = -1.0
        for k in range(1, n + 1):
            result = pass_at_k(n, c, k)
            assert result >= prev - 1e-12
            prev = result


# ---------------------------------------------------------------------------
# mean_pass_at_k
# ---------------------------------------------------------------------------


class TestMeanPassAtK:
    def test_mean_over_problems(self):
        samples = [(10, 3), (10, 3)]
        result = mean_pass_at_k(samples, k=1)
        assert result == pytest.approx(0.3, abs=1e-12)

    def test_mean_averages_distinct_problems(self):
        samples = [(10, 10), (10, 0)]  # pass@1 = 1.0 and 0.0
        result = mean_pass_at_k(samples, k=1)
        assert result == pytest.approx(0.5, abs=1e-12)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            mean_pass_at_k([], k=1)


# ---------------------------------------------------------------------------
# bootstrap_ci
# ---------------------------------------------------------------------------


class TestBootstrapCI:
    def test_same_seed_is_deterministic(self):
        values = [0.1, 0.5, 0.9, 0.3, 0.7, 0.0, 1.0, 0.4]
        ci1 = bootstrap_ci(values, seed=42, n_boot=2000)
        ci2 = bootstrap_ci(values, seed=42, n_boot=2000)
        assert ci1 == ci2

    def test_different_seed_can_differ(self):
        values = [0.1, 0.5, 0.9, 0.3, 0.7, 0.0, 1.0, 0.4]
        ci1 = bootstrap_ci(values, seed=1, n_boot=2000)
        ci2 = bootstrap_ci(values, seed=2, n_boot=2000)
        # Not a hard guarantee in general, but with 8 distinct values and
        # 2000 resamples the two seeds should not coincide exactly.
        assert ci1 != ci2

    def test_interval_brackets_point_estimate(self):
        values = [0.2, 0.4, 0.6, 0.8, 1.0, 0.0, 0.5, 0.3, 0.7, 0.9]
        point_estimate = sum(values) / len(values)
        lo, hi = bootstrap_ci(values, seed=7, n_boot=5000)
        assert lo <= point_estimate + 1e-9
        assert hi >= point_estimate - 1e-9

    def test_degenerate_all_equal_is_zero_width(self):
        values = [0.42] * 10
        lo, hi = bootstrap_ci(values, seed=0, n_boot=1000)
        assert lo == pytest.approx(0.42, abs=1e-12)
        assert hi == pytest.approx(0.42, abs=1e-12)
        assert hi - lo == pytest.approx(0.0, abs=1e-12)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            bootstrap_ci([], seed=0)


# ---------------------------------------------------------------------------
# wilson_interval
# ---------------------------------------------------------------------------


class TestWilsonInterval:
    def test_known_published_value(self):
        # successes=8, trials=10, alpha=0.05: computed by hand from the
        # Wilson (1927) closed form (see metrics.py docstring); not sourced
        # from a third-party worked example. Expect approx (0.490, 0.943).
        lo, hi = wilson_interval(8, 10, alpha=0.05)
        assert lo == pytest.approx(0.490, abs=1e-2)
        assert hi == pytest.approx(0.943, abs=1e-2)

    def test_contained_in_unit_interval(self):
        for successes in range(0, 11):
            lo, hi = wilson_interval(successes, 10)
            assert 0.0 <= lo <= hi <= 1.0

    def test_large_n_approaches_normal_approximation(self):
        # For large n, Wilson center collapses toward phat +/- z*sqrt(phat(1-phat)/n).
        successes, trials = 5000, 10000
        lo, hi = wilson_interval(successes, trials, alpha=0.05)
        phat = successes / trials
        z = 1.959963984540054
        normal_half_width = z * math.sqrt(phat * (1 - phat) / trials)
        normal_lo = phat - normal_half_width
        normal_hi = phat + normal_half_width
        assert lo == pytest.approx(normal_lo, abs=1e-3)
        assert hi == pytest.approx(normal_hi, abs=1e-3)

    def test_zero_trials_raises(self):
        with pytest.raises(ValueError):
            wilson_interval(0, 0)

    def test_invalid_successes_raises(self):
        with pytest.raises(ValueError):
            wilson_interval(-1, 10)
        with pytest.raises(ValueError):
            wilson_interval(11, 10)


class TestAlphaValidation:
    # Review finding (PR #9): alpha outside (0, 1) silently returned an
    # inverted interval (lo > hi) from bootstrap_ci instead of raising.
    def test_bootstrap_ci_rejects_out_of_range_alpha(self):
        for bad in (0.0, 1.0, 1.5, -0.1):
            with pytest.raises(ValueError):
                bootstrap_ci([0.1, 0.5, 0.9, 0.3], seed=1, alpha=bad, n_boot=100)

    def test_wilson_rejects_out_of_range_alpha(self):
        for bad in (0.0, 1.0, 1.5, -0.1):
            with pytest.raises(ValueError):
                wilson_interval(8, 10, alpha=bad)
