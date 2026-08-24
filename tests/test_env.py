"""Tests for rlvr.env — the verifiers-style task/rollout/reward interface (docs/07 Phase A).

Tests use real HumanEval/MBPP tasks (no model, deterministic, small). HumanEval/0
(has_close_elements) is the cheap workhorse task used for most of these; HumanEval/2
(truncate_number, atol=1e-6), HumanEval/8 (sum_product, tuple-VALUED-output), and Mbpp/106
(tuple-TYPED-input) cover comparison/argument-passing semantics HumanEval/0 doesn't exercise.
"""

from __future__ import annotations

import dataclasses
import time

import pytest

import rlvr.env as env
from rlvr.data import load_tasks
from rlvr.env import (
    ReferenceExecutionError,
    _values_equal,
    default_timeout_s,
    evaluate_code,
    reward,
)
from rlvr.sandbox import ExecResult

HUMANEVAL = load_tasks("humaneval")
MBPP = load_tasks("mbpp")

# A different (O(n^2), unsorted) but CORRECT implementation of has_close_elements — not a
# copy of the reference (which sorts first) — so passing here demonstrates real execution and
# comparison, not object-identity with the reference solution.
CORRECT_CODE = """

    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            if abs(numbers[i] - numbers[j]) < threshold:
                return True
    return False
"""

# Subtly wrong: only checks ADJACENT pairs in the given (unsorted) order, missing close pairs
# that are non-adjacent in input order — fails on real HumanEval/0 base inputs (verified below).
WRONG_CODE = """

    for i in range(len(numbers) - 1):
        if abs(numbers[i] - numbers[i + 1]) < threshold:
            return True
    return False
"""

# RED DEMONSTRATION (A2): hardcodes the exact answer for each of HumanEval/0's 7 base inputs
# via literal lookup, then returns a constant garbage default for anything else. This must
# pass base (all 7 memorized) and fail plus (the garbage default is wrong on most of the 999
# extended inputs) — the measured verifier gap docs/07 Phase B quantifies.
HARDCODE_TO_VISIBLE_CODE = """

    if numbers == [1.0, 2.0, 3.9, 4.0, 5.0, 2.2] and threshold == 0.3:
        return True
    if numbers == [1.0, 2.0, 3.9, 4.0, 5.0, 2.2] and threshold == 0.05:
        return False
    if numbers == [1.0, 2.0, 5.9, 4.0, 5.0] and threshold == 0.95:
        return True
    if numbers == [1.0, 2.0, 5.9, 4.0, 5.0] and threshold == 0.8:
        return False
    if numbers == [1.0, 2.0, 3.0, 4.0, 5.0, 2.0] and threshold == 0.1:
        return True
    if numbers == [1.1, 2.2, 3.1, 4.1, 5.1] and threshold == 1.0:
        return True
    if numbers == [1.1, 2.2, 3.1, 4.1, 5.1] and threshold == 0.5:
        return False
    return True
"""

# Raises for exactly the first base input (threshold == 0.3), correct algorithm otherwise —
# used to prove a single input's exception doesn't crash the whole suite's scoring.
PARTIAL_RAISE_CODE = """

    if threshold == 0.3:
        raise ValueError("boom")
    sorted_numbers = sorted(numbers)
    for i in range(len(sorted_numbers) - 1):
        if sorted_numbers[i + 1] - sorted_numbers[i] < threshold:
            return True
    return False
"""

HANG_CODE = """

    while True:
        pass
"""

# CORRECT algorithm (same as CORRECT_CODE) but writes a stray partial line to stdout with NO
# trailing newline before returning — pass-2 DEFECT 1 reproduction. Pre-fix, this glues onto the
# front of the driver's next protocol line and _parse_driver_stdout drops every record via
# `except json.JSONDecodeError: continue`, scoring a genuinely correct solution 0/7 with the
# factually wrong "timeout, crash, or process killed" message (verified by hand against the
# pre-fix parser: 0/1006 on "both", error message exactly that string). Post-fix, the
# nonce-framed leading-newline protocol isolates the record regardless.
CORRECT_CODE_WITH_STRAY_PARTIAL_STDOUT = """

    import sys as _stray_sys
    _stray_sys.stdout.write("x")
    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            if abs(numbers[i] - numbers[j]) < threshold:
                return True
    return False
"""

# Forges fake protocol-shaped lines claiming ok=True for every input, then returns an answer
# that is wrong for most real inputs — must NOT get credit for indices its real function fails,
# because it cannot know the per-run nonce that frames genuine protocol lines.
FORGED_PROTOCOL_CODE = """

    import json as _forge_json
    for _forge_i in range(20):
        print(_forge_json.dumps({"i": _forge_i, "ok": True, "out": True}))
    return False
"""

# Kills the process outright (os._exit, no exception, no timeout) on the FIRST base input
# (threshold == 0.3 — same input PARTIAL_RAISE_CODE targets). No protocol record is ever
# written for this or any later input, and the process exits with returncode 0 — neither a
# timeout nor an OOM. Used to reach the "no protocol record" diagnostic branch, which the
# nonce-framing fix for DEFECT 1 otherwise leaves unexercised (stray partial-line stdout no
# longer loses records at all).
KILL_MID_BATCH_CODE = """

    import os as _os_kill
    if threshold == 0.3:
        _os_kill._exit(0)
    sorted_numbers = sorted(numbers)
    for i in range(len(sorted_numbers) - 1):
        if sorted_numbers[i + 1] - sorted_numbers[i] < threshold:
            return True
    return False
"""


def test_known_correct_solution_passes_base_and_plus():
    task = HUMANEVAL["HumanEval/0"]
    result = evaluate_code(
        task, CORRECT_CODE, "both", timeout_s=default_timeout_s(task.n_base + task.n_plus)
    )
    assert result.passed is True
    assert result.n_passed == result.n_total == task.n_base + task.n_plus
    assert result.timed_out is False
    assert result.oom is False


def test_known_wrong_solution_fails():
    task = HUMANEVAL["HumanEval/0"]
    result = evaluate_code(task, WRONG_CODE, "base", timeout_s=default_timeout_s(task.n_base))
    assert result.passed is False
    assert result.n_passed < result.n_total
    # Non-adjacent-in-input-order close pairs are the specific bug — confirm at least one
    # concrete failing index carries a real diagnostic, not a silent False.
    assert result.errors
    assert all("mismatch" in msg for msg in result.errors.values())


def test_reward_matches_evaluate_code_passed():
    task = HUMANEVAL["HumanEval/0"]
    assert reward(task, CORRECT_CODE, "base", timeout_s=default_timeout_s(task.n_base)) == 1.0
    assert reward(task, WRONG_CODE, "base", timeout_s=default_timeout_s(task.n_base)) == 0.0


def test_red_demonstration_hardcode_passes_base_fails_plus():
    """The verifier-gap mechanism docs/07 measures: a solution that memorizes the visible
    (base) tests and returns garbage otherwise passes base 100% while failing plus badly.
    Base-only evaluation would report this candidate as correct — that IS the gap."""
    task = HUMANEVAL["HumanEval/0"]
    base_result = evaluate_code(
        task, HARDCODE_TO_VISIBLE_CODE, "base", timeout_s=default_timeout_s(task.n_base)
    )
    plus_result = evaluate_code(
        task, HARDCODE_TO_VISIBLE_CODE, "plus", timeout_s=default_timeout_s(task.n_plus)
    )

    assert base_result.passed is True
    assert base_result.n_passed == base_result.n_total == task.n_base

    assert plus_result.passed is False
    assert plus_result.n_passed < plus_result.n_total
    # A discriminating gap, not a one-off: garbage-default should miss a substantial share of
    # the 999 extended inputs.
    assert plus_result.n_passed / plus_result.n_total < 0.95


def test_float_atol_respected():
    """HumanEval/2 (truncate_number) carries atol=1e-6. An output within atol of the reference
    passes; the same magnitude of error just outside atol fails."""
    task = HUMANEVAL["HumanEval/2"]
    assert task.atol == pytest.approx(1e-6)

    within_atol = "\n\n    return number - int(number) + 5e-7\n"
    outside_atol = "\n\n    return number - int(number) + 5e-5\n"

    within_result = evaluate_code(
        task, within_atol, "base", timeout_s=default_timeout_s(task.n_base)
    )
    outside_result = evaluate_code(
        task, outside_atol, "base", timeout_s=default_timeout_s(task.n_base)
    )

    assert within_result.passed is True
    assert outside_result.passed is False
    assert outside_result.n_passed == 0


def test_atol_comparison_handles_equal_infinities_and_huge_ints():
    """Regression test (found by the calibration verification run against real MBPP tasks,
    2026-08-14): with atol > 0, the naive `abs(fa - fb) <= atol` breaks on two IDENTICAL
    infinities (`inf - inf == nan`, so `nan <= atol` is False — Mbpp/137's `zero_count`
    legitimately returns `float('inf')`) and on Python ints outside float's range (`float(a)`
    raises `OverflowError`, uncaught, crashing the whole comparison). Exact equality is now
    checked first, before any float() conversion."""
    inf = float("inf")
    assert _values_equal(inf, inf, atol=1e-4) is True
    assert _values_equal(inf, inf, atol=0) is True
    assert _values_equal(inf, 5.0, atol=1e-4) is False
    assert _values_equal(inf, -inf, atol=1e-4) is False

    huge = 10**400  # far outside float's representable range
    assert _values_equal(huge, huge, atol=0) is True
    assert _values_equal(huge, huge + 1, atol=0) is False
    assert _values_equal(huge, huge + 1, atol=1e-4) is False  # must not raise OverflowError


def test_nan_equals_nan():
    """nan == nan is treated as a pass (both-NaN is a legitimate agreement, not a mismatch) —
    checked directly on the comparator plus an end-to-end discriminating control."""
    nan = float("nan")
    assert _values_equal(nan, nan, atol=0) is True
    assert _values_equal(nan, 1.0, atol=0) is False

    task = HUMANEVAL["HumanEval/2"]
    nan_code = "\n\n    return float('nan')\n"
    result = evaluate_code(task, nan_code, "base", timeout_s=default_timeout_s(task.n_base))
    # Discriminating control: reference truncate_number never produces nan for these real
    # inputs, so an always-nan candidate must NOT pass end-to-end — nan==nan isn't a blanket
    # free pass, it only fires when the reference itself is genuinely nan.
    assert result.passed is False


def test_tuple_vs_list_equivalence():
    """HumanEval/8 (sum_product) returns a tuple. A candidate returning the equivalent LIST
    must be scored as equal — the JSON round trip normalizes both sides to lists."""
    task = HUMANEVAL["HumanEval/8"]
    list_return_code = """

    s, p = 0, 1
    for number in numbers:
        s += number
        p *= number
    return [s, p]
"""
    result = evaluate_code(
        task, list_return_code, "base", timeout_s=default_timeout_s(task.n_base)
    )
    assert result.passed is True
    assert result.n_passed == result.n_total == task.n_base


def test_tuple_typed_input_arg_reaches_user_code_as_a_real_tuple():
    """Regression test (found by the calibration smoke run against real MBPP tasks,
    2026-08-14): Mbpp/106's reference solution is ``test_tup + tuple(test_list)`` and is
    called with an actual ``tuple`` positional argument (base_inputs mixes list- and
    tuple-typed args in the same call). A JSON round trip on INPUTS (the driver's first
    implementation) silently coerces every tuple argument to a list, so
    ``tuple + list`` raises ``TypeError`` and even the reference solution fails against its
    own environment. Inputs are now embedded via ``repr()``/``eval()`` specifically to
    preserve this. Reverting `_build_driver_script` to `json.dumps`/`json.loads` for inputs
    turns this test RED with 'candidate raised: can only concatenate list (not "tuple") to
    list' on every input — verified by hand while writing this guard."""
    task = MBPP["Mbpp/106"]
    result = evaluate_code(
        task, task.reference_solution, "base", timeout_s=default_timeout_s(task.n_base)
    )
    assert result.passed is True, result.errors


def test_zero_input_suite_is_vacuously_passed_and_visible():
    """Mbpp/793 (per rlvr/data.py) has zero plus inputs. A suite with n_total == 0 is
    vacuously `passed=True` — but that must stay DISTINGUISHABLE from "verified": n_total==0
    is the caller-visible signal that nothing was actually checked, not a certification."""
    task = MBPP["Mbpp/793"]
    assert task.n_plus == 0
    result = evaluate_code(
        task, task.reference_solution, "plus", timeout_s=default_timeout_s(task.n_plus)
    )
    assert result.n_total == 0
    assert result.n_passed == 0
    assert result.passed is True


def test_exception_in_one_input_does_not_crash_whole_suite():
    """An input that raises in user code fails only that input; the rest are still scored."""
    task = HUMANEVAL["HumanEval/0"]
    result = evaluate_code(
        task, PARTIAL_RAISE_CODE, "base", timeout_s=default_timeout_s(task.n_base)
    )
    assert result.passed is False
    assert result.n_total == task.n_base
    # Exactly the first input (threshold == 0.3) raised; the other 6 (correct algorithm)
    # scored normally and passed.
    assert result.per_input[0] is False
    assert all(result.per_input[1:])
    assert result.n_passed == task.n_base - 1
    assert "boom" in result.errors[0]


def test_timeout_reports_diagnostics_honestly_and_does_not_hang():
    task = HUMANEVAL["HumanEval/0"]
    start = time.monotonic()
    result = evaluate_code(task, HANG_CODE, "base", timeout_s=2.0)
    wallclock = time.monotonic() - start

    assert result.timed_out is True
    assert result.passed is False
    # The other side of "only claim timeout/oom when ExecResult actually says so": when it DID
    # actually time out, the diagnostic must say so.
    assert result.errors and all("timed out" in msg for msg in result.errors.values())
    assert reward(task, HANG_CODE, "base", timeout_s=2.0) == 0.0
    # Bounded by the timeout (plus generous slack for process teardown), not left hanging.
    assert wallclock < 10.0


# --------------------------------------------------------------------------
# pass-2 DEFECT 1 — protocol corruption by candidate partial-line stdout
# --------------------------------------------------------------------------


def test_stray_partial_line_stdout_does_not_corrupt_protocol():
    """RED (pre-fix, verified by hand against the parser before the nonce-framing fix): a
    genuinely correct solution that leaves an unterminated ``sys.stdout.write("x")`` on stdout
    scored 0/1006 on suite="both", with every failure's message asserting "timeout, crash, or
    process killed" — a factually wrong diagnosis, since the process neither timed out nor
    crashed; ``_parse_driver_stdout`` was silently dropping every JSON line because the stray
    "x" glued onto the front of each record and broke ``json.loads``.

    GREEN (this test, post-fix): the nonce-framed leading-newline protocol isolates each record
    from a candidate's partial-line stdout, so the SAME correct algorithm now scores 7/7 (both
    suites concatenated: task.n_base + task.n_plus)."""
    task = HUMANEVAL["HumanEval/0"]
    result = evaluate_code(
        task,
        CORRECT_CODE_WITH_STRAY_PARTIAL_STDOUT,
        "both",
        timeout_s=default_timeout_s(task.n_base + task.n_plus),
    )
    assert result.passed is True
    assert result.n_passed == result.n_total == task.n_base + task.n_plus


def test_forged_protocol_line_gets_no_credit():
    """A candidate that prints fake protocol-shaped lines claiming ok=True for every index, then
    returns False from its real function body (correct only where the reference is also False),
    must be scored on the REAL function's output — not the forged lines — because it cannot know
    the per-run nonce.

    RED (pre-fix, verified by hand by loading the pre-pass-2 ``env.py`` from git and running this
    exact candidate against it): un-nonce-framed parsing accepts the forged lines as real
    records, and because both real and forged lines are keyed by the same dict key "i", later
    writes for a given index win — net result 5/7 with per_input
    [True, False, True, False, True, True, True] (index 6 forged-then-overwritten by the one
    real record that lands after the forgery loop finishes). A "no discriminating signal at all"
    forgery (7/7) doesn't occur here only because dict-overwrite order happens to leave one real
    record standing; the mechanism is still forged credit for indices 0, 2, 4, 5.

    GREEN (this test, post-fix): forged lines are never even parsed as records (wrong nonce
    prefix), so the candidate is scored purely on its real (always-False) return value: correct
    only at the 3 indices (1, 3, 6) where the reference answer is also False, wrong at the 4
    indices (0, 2, 4, 5) where the reference is True and the forgery claimed (falsely) to match.
    """
    task = HUMANEVAL["HumanEval/0"]
    result = evaluate_code(
        task, FORGED_PROTOCOL_CODE, "base", timeout_s=default_timeout_s(task.n_base)
    )
    assert result.passed is False
    assert result.n_passed == 3
    failing_indices = {i for i, ok in enumerate(result.per_input) if not ok}
    assert failing_indices == {0, 2, 4, 5}
    assert all("output mismatch" in msg for msg in result.errors.values())


def test_missing_candidate_record_without_timeout_reports_honest_diagnosis():
    """A candidate that dies mid-batch via ``os._exit`` (no exception, no timeout, no OOM —
    returncode 0) leaves every input from the killed one onward with no protocol record at all.
    The diagnostic for this case must say so honestly ("no protocol record ... wrote over/
    crashed before reporting") and must NOT claim a timeout that ExecResult does not report —
    the exact defect this module's diagnostics were factually wrong about pre-fix (DEFECT 1)."""
    task = HUMANEVAL["HumanEval/0"]
    result = evaluate_code(
        task, KILL_MID_BATCH_CODE, "base", timeout_s=default_timeout_s(task.n_base)
    )
    assert result.passed is False
    assert result.timed_out is False
    assert result.oom is False
    assert result.n_passed == 0
    assert all(
        msg == "no protocol record (candidate wrote over/crashed before reporting)"
        for msg in result.errors.values()
    )


# --------------------------------------------------------------------------
# pass-2 DEFECT 2 — reference-cache poisoning
# --------------------------------------------------------------------------


def test_incomplete_reference_raises_and_does_not_poison_cache():
    """RED (pre-fix, verified by hand): monkeypatching ``run_untrusted`` to truncate the
    reference driver's stdout to a partial protocol run caused ``_reference_records`` to cache
    the truncated 3-of-7 record set unconditionally; a subsequent CORRECT candidate was then
    permanently scored 3/7 with reward 0.0 — a false failure caused by the environment, not the
    candidate.

    GREEN (this test, post-fix): the same truncated reference run now raises
    ``ReferenceExecutionError`` instead of caching, the cache key is NOT populated, and a
    subsequent normal (untruncated) call succeeds cleanly."""
    task = HUMANEVAL["HumanEval/0"]
    cache_key = (task.task_id, "base")

    real_run_untrusted = env.run_untrusted

    def truncated_run_untrusted(*args, **kwargs):
        result = real_run_untrusted(*args, **kwargs)
        lines = result.stdout.splitlines()
        truncated_stdout = "\n".join(lines[:3]) + "\n"
        # forward-compatible with ExecResult's full diagnostics field set
        return dataclasses.replace(
            result, stdout=truncated_stdout, timed_out=False, oom=False
        )

    env._reference_cache.clear()
    try:
        env.run_untrusted = truncated_run_untrusted
        with pytest.raises(ReferenceExecutionError):
            env._reference_records(
                task, "base", timeout_s=default_timeout_s(task.n_base), memory_mb=512
            )
        assert cache_key not in env._reference_cache
    finally:
        env.run_untrusted = real_run_untrusted

    # A subsequent, untruncated call succeeds and is not poisoned by the aborted attempt.
    result = evaluate_code(task, CORRECT_CODE, "base", timeout_s=default_timeout_s(task.n_base))
    assert result.passed is True
    assert result.n_passed == result.n_total == task.n_base
    assert reward(task, CORRECT_CODE, "base", timeout_s=default_timeout_s(task.n_base)) == 1.0


def _synthetic_task(entry_point: str, prompt: str, solution_body: str, inputs: list) -> "Task":
    from rlvr.data import Task

    return Task(
        task_id=f"synthetic/{entry_point}",
        prompt=prompt,
        entry_point=entry_point,
        reference_solution=solution_body,
        base_inputs=inputs,
        plus_inputs=[],
        n_base=len(inputs),
        n_plus=0,
        atol=0,
    )


def test_huge_int_outputs_survive_driver_serialization():
    """Calibration finding (2026-08-14, HumanEval/83 & /139): CPython's 4300-digit
    int->str guard fired inside the DRIVER's json.dumps and misattributed the failure
    to the candidate. The driver now lifts the limit before running inputs."""
    env._reference_cache.clear()
    task = _synthetic_task(
        "big_int",
        "def big_int(n):\n",
        "    return 10 ** n\n",
        [[5000]],
    )
    result = evaluate_code(task, task.reference_solution, "base", timeout_s=30.0)
    assert result.passed, f"errors: {result.errors}"


def test_large_outputs_travel_as_hashes_and_still_discriminate():
    """Calibration finding (2026-08-14, HumanEval/15/130): >64 MiB of honest
    output blew every fixed pipe cap, so outputs whose serialization exceeds
    64 KiB now travel as sha256 digests. Two pins: (1) a correct candidate
    with huge outputs passes (records round-trip as hashes, pipe stays tiny);
    (2) a candidate returning a DIFFERENT huge output fails — hash comparison
    discriminates, it does not rubber-stamp."""
    task = _synthetic_task(
        "big_out",
        "def big_out(i):\n",
        "    return 'x' * 200_000\n",
        [[i] for i in range(10)],
    )

    env._reference_cache.clear()
    result = evaluate_code(task, task.reference_solution, "base", timeout_s=60.0)
    assert result.passed and result.n_passed == 10

    wrong = "    return 'x' * 199_999\n"  # differs only in length — hashes must catch it
    result_wrong = evaluate_code(task, wrong, "base", timeout_s=60.0)
    assert not result_wrong.passed and result_wrong.n_passed == 0
    env._reference_cache.clear()
