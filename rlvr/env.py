"""rlvr.env — verifiers-style task-in / rollout / reward-out interface (docs/07 Phase A).

``evaluate_code`` runs a candidate solution through :func:`rlvr.sandbox.run_untrusted` against
one of a task's test suites and reports pass/fail per input. ``reward`` is the trivial binary
wrapper docs/07 measures the adequacy OF (Phase B). This module owns none of the sandbox's
security properties — see ``rlvr/sandbox.py``'s DECLARED SCOPE for that — it only owns how a
:class:`~rlvr.data.Task` and a candidate solution get turned into pass/fail verdicts.

Prompt/solution concatenation (A4 — verified 2026-08-14 against both datasets)
--------------------------------------------------------------------------------
``Task.reference_solution`` is ``evalplus``'s ``canonical_solution`` field, and its shape
differs by dataset in a way that still composes uniformly:

- **HumanEval**: ``prompt`` ends with an open ``def ...:`` and docstring; ``reference_solution``
  is the function *body only* (its indentation continues the ``def`` in the prompt).
- **MBPP**: ``prompt`` is a comment/docstring with no ``def`` line at all;
  ``reference_solution`` is the *entire* ``def ...:`` block, ``def`` line included.

In both cases ``task.prompt + task.reference_solution`` is valid, directly-executable Python
that defines a callable named ``task.entry_point`` — this is evalplus's own design so one
concatenation rule works for both benchmarks. Example (``HumanEval/0``, docstring elided)::

    prompt              = "from typing import List\\n\\n\\n" \\
                          "def has_close_elements(numbers, threshold) -> bool:\\n" \\
                          "    <docstring>\\n"
    reference_solution  = "\\n\\n    sorted_numbers = sorted(numbers)\\n" \\
                          "    for i in range(len(sorted_numbers) - 1):\\n" \\
                          "        if ...: return True\\n    return False\\n\\n"
    # prompt + reference_solution execs cleanly and defines has_close_elements(...)

``evaluate_code``'s ``code`` argument follows the *same* shape as ``reference_solution`` (a
completion, not a full standalone program) — this is what lets
``scripts/run_calibration.py`` pass ``task.reference_solution`` itself as ``code`` unmodified.

Execution model
----------------
All of a suite's inputs are batched into ONE sandbox call (some EvalPlus "plus" suites carry
~1000 inputs; per-input subprocesses would be ~1000x slower). The driver script is: the
program source, followed by a loop that applies each input's argument list to
``task.entry_point`` and prints one JSON line per input, flushed immediately (so a
mid-batch timeout still yields partial results for the inputs that finished first). Reference
outputs are computed by running ``task.reference_solution`` through the identical path (A4: the
measurement goes through the real entry point, not a shortcut), cached in-process by a plain
dict keyed on ``(task_id, suite)`` — ``functools.lru_cache`` is not used because ``Task`` holds
list fields and is therefore unhashable. The cache is gated on completeness (see
``ReferenceExecutionError`` below) and protected by a lock for parallel mutation sweeps.

Protocol framing — declared scope (pass-2 hardening)
------------------------------------------------------
Each driver run is given a fresh per-run nonce (``secrets.token_hex(8)``), generated in the
PARENT process and embedded as a literal into the driver source — the child never sees it as a
variable it could read, guess, or overwrite. Every protocol line is written as
``"\n" + nonce + json_line``: the leading newline forces the record onto the start of its own
line even if the candidate's function body left a partial, unterminated line on stdout (e.g.
``sys.stdout.write("x")`` with no trailing newline) — without it, that stray partial write would
glue onto the front of the next protocol line and make it fail to parse. The parent only accepts
lines that start with the exact nonce; everything else (candidate stdout, forged JSON objects
that happen to look like ``{"i": ..., "ok": ...}``) is ignored. Because the nonce is per-run and
unguessable, a candidate cannot forge a protocol line to claim credit for inputs its real
function fails — this closes the JSON-line-forgery gap this module previously declared as an
undefended limitation.

Output comparison — declared scope
------------------------------------
Both the candidate's and the reference's per-input outputs are JSON round-tripped by the
driver (``json.dumps`` in the child, ``json.loads`` in the parent). That round trip already
normalizes tuples to lists on both sides identically, so no separate tuple/list normalization
step is needed downstream. Numeric comparison is atol-tolerant when ``task.atol > 0``, and
``nan == nan`` is treated as equal (both-NaN is a real pass in these tasks, not a mismatch).

**Non-JSON-serializable outputs** (e.g. containing sets, complex numbers): the driver falls
back to ``repr(out)`` and tags the record ``out_repr`` instead of ``out``. Two repr-fallback
outputs are compared as exact strings, which is weaker than structural equality and is a known,
declared limitation (a reference and candidate producing "the same value" via differently
constructed objects with different reprs would show as a mismatch). A record with ``out`` on
one side and ``out_repr`` on the other is always scored as a mismatch — comparable
representations were not available on both sides.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import math
import secrets
import threading
from dataclasses import dataclass, field
from typing import Literal

from rlvr.data import Task
from rlvr.sandbox import ExecResult, run_untrusted

__all__ = [
    "SuiteResult",
    "SuiteName",
    "ReferenceExecutionError",
    "evaluate_code",
    "reward",
    "default_timeout_s",
]

SuiteName = Literal["base", "plus", "both"]


@dataclass(frozen=True)
class SuiteResult:
    """Outcome of scoring one candidate solution against one suite of one task."""

    task_id: str
    suite: str
    n_total: int
    n_passed: int
    passed: bool
    per_input: list  # list[bool], one entry per input, in suite order
    errors: dict  # dict[int, str] — diagnostic message per FAILED input index
    timed_out: bool
    oom: bool
    duration_s: float
    exec_result: ExecResult = field(repr=False)


def default_timeout_s(n_inputs: int) -> float:
    """Timeout budget that scales with suite size — some 'plus' suites carry ~1000 inputs.

    Expose, don't hardcode: callers running large suites should pass this (or their own
    budget) rather than a fixed magic number.
    """
    return max(10.0, 0.02 * n_inputs)


# --------------------------------------------------------------------------
# suite input selection
# --------------------------------------------------------------------------


def _suite_inputs(task: Task, suite: SuiteName) -> list:
    if suite == "base":
        return list(task.base_inputs)
    if suite == "plus":
        return list(task.plus_inputs)
    if suite == "both":
        return list(task.base_inputs) + list(task.plus_inputs)
    raise ValueError(f"unknown suite {suite!r}; expected one of 'base', 'plus', 'both'")


# --------------------------------------------------------------------------
# driver script construction
# --------------------------------------------------------------------------


#: Output cap for driver runs. Big plus suites produce >1 MiB of honest
#: protocol output (HumanEval/14: 351/903 records survived the 1 MiB default
#: before this — calibration finding, 2026-08-14); still bounded so a runaway
#: candidate can't OOM the parent.
_DRIVER_OUTPUT_CAP_BYTES = 64 * 1024 * 1024


def _build_driver_script(program_source: str, entry_point: str, inputs: list, nonce: str) -> str:
    """Program source + a loop that prints one nonce-framed JSON line per input.

    ``nonce`` is generated by the PARENT (``secrets.token_hex(8)``) and embedded here as a
    literal string baked directly into each print's format string — not assigned to a driver
    module variable the candidate's function body could read back or shadow. Every protocol
    line is written as ``"\\n" + nonce + json_line``: the leading ``"\\n"`` guarantees the
    record starts a fresh line even if the candidate left an unterminated partial write on
    stdout (``sys.stdout.write("x")`` with no newline) — otherwise that stray "x" would glue
    onto the front of the marker and the line would fail to parse. See the module docstring's
    "Protocol framing" section.

    ``inputs`` is embedded via ``repr()`` and re-materialized with ``eval()`` in the child,
    NOT round-tripped through JSON. This matters: EvalPlus base/plus inputs are real Python
    objects and are sometimes type-sensitive at the argument level — e.g. Mbpp/106's reference
    solution is ``test_tup + tuple(test_list)``, called with an actual ``tuple`` positional
    argument (found and fixed during this module's own calibration smoke test: MBPP inputs can
    mix ``list`` and ``tuple`` args in the same call, and ``test_tup`` must arrive as a real
    tuple or ``tuple + list`` raises ``TypeError``). JSON has no tuple type, so a JSON round
    trip on INPUTS would silently coerce every tuple argument to a list and break exactly this
    kind of reference code — a real driver bug, not a sandbox limitation, caught by running
    calibration against real MBPP tasks. OUTPUTS are a different case and stay on the JSON
    path deliberately: comparing a returned tuple and a returned list as equal (both go through
    the same JSON round trip on both the candidate and reference side) is the declared,
    intended scope for output comparison — see the module docstring.

    ``eval()`` runs with an explicit ``nan``/``inf`` in its globals so ``repr()`` of a float
    NaN/inf value (which renders as the bare tokens ``nan``/``inf``, not valid Python on their
    own) still evaluates, without polluting the driver's own module namespace where the
    candidate function runs.
    """
    inputs_repr = repr(inputs)
    nonce_repr = repr(nonce)
    lines = [
        program_source,
        "",
        "import json as _rlvr_json",
        "import hashlib as _rlvr_hashlib",
        "import sys as _rlvr_sys",
        "",
        "# Some reference solutions legitimately return huge ints (HumanEval/83,",
        "# /139); CPython's 4300-digit int->str guard would make the DRIVER's",
        "# serialization raise and misattribute the failure to the candidate",
        "# (calibration finding, 2026-08-14). 0 = unlimited.",
        "if hasattr(_rlvr_sys, 'set_int_max_str_digits'):",
        "    _rlvr_sys.set_int_max_str_digits(0)",
        "del _rlvr_sys",
        "",
        f"_rlvr_inputs = eval({inputs_repr!r}, "
        "{'nan': float('nan'), 'inf': float('inf')})",
        "",
        "for _rlvr_i, _rlvr_args in enumerate(_rlvr_inputs):",
        "    try:",
        f"        _rlvr_out = {entry_point}(*_rlvr_args)",
        "        try:",
        "            _rlvr_out_ser = _rlvr_json.dumps(_rlvr_out)",
        "            if len(_rlvr_out_ser) > 65536:",
        "                # Oversized outputs travel as a hash of their canonical",
        "                # serialization, not the bytes: HumanEval/15's plus suite",
        "                # emits ~7 MB per record of honest output and blew every",
        "                # fixed pipe cap (calibration finding, 2026-08-14). The",
        "                # parent hashes the other side identically, so equality",
        "                # comparison is preserved; atol does not apply to hashed",
        "                # records (declared in the module docstring).",
        '                _rlvr_line = _rlvr_json.dumps({"i": _rlvr_i, "ok": True,'
        ' "out_sha256": _rlvr_hashlib.sha256(_rlvr_out_ser.encode("utf-8")).hexdigest(),'
        ' "out_len": len(_rlvr_out_ser)})',
        "            else:",
        '                _rlvr_line = _rlvr_json.dumps({"i": _rlvr_i, "ok": True, "out": _rlvr_out})',
        "        except TypeError:",
        "            _rlvr_out_repr = repr(_rlvr_out)",
        "            if len(_rlvr_out_repr) > 65536:",
        '                _rlvr_line = _rlvr_json.dumps({"i": _rlvr_i, "ok": True,'
        ' "repr_sha256": _rlvr_hashlib.sha256(_rlvr_out_repr.encode("utf-8")).hexdigest(),'
        ' "repr_len": len(_rlvr_out_repr)})',
        "            else:",
        '                _rlvr_line = _rlvr_json.dumps('
        '{"i": _rlvr_i, "ok": True, "out_repr": _rlvr_out_repr})',
        f"        print('\\n' + {nonce_repr} + _rlvr_line, flush=True)",
        "    except Exception as _rlvr_e:",
        '        _rlvr_line = _rlvr_json.dumps('
        '{"i": _rlvr_i, "ok": False, "err": str(_rlvr_e)})',
        f"        print('\\n' + {nonce_repr} + _rlvr_line, flush=True)",
    ]
    return "\n".join(lines)


@contextlib.contextmanager
def _unlimited_int_str_digits():
    """Lift CPython's 4300-digit int<->str guard while decoding protocol lines.

    The driver already lifts it in the CHILD so huge-int returns serialize;
    the same guard fires in the PARENT's json.loads on the way back in
    (calibration finding, 2026-08-14: HumanEval/83's 5001-digit values).
    Scoped, not global: restored on exit so host-process behavior is
    unchanged outside protocol parsing."""
    if not hasattr(sys, "set_int_max_str_digits"):
        yield
        return
    prev = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(prev)


def _parse_driver_stdout(stdout: str, nonce: str) -> dict:
    """Parse driver stdout into {input_index: record}, trusting only nonce-framed lines.

    Only lines that start with the exact per-run ``nonce`` (see ``_build_driver_script``) are
    considered protocol lines; everything else — stray candidate ``print()``/``stdout.write()``
    output, and any JSON object a candidate forges to *look like* a driver record (``{"i": ...,
    "ok": ...}``) — is ignored, because the candidate cannot know the nonce. This closes the two
    failure modes pass-1 declared as undefended: protocol corruption from partial-line candidate
    stdout (the record is glued to a stray write only if that write itself started with the
    nonce, which requires guessing it), and JSON-line forgery for credit the candidate's real
    function didn't earn.
    """
    records: dict = {}
    for line in stdout.splitlines():
        if not line.startswith(nonce):
            continue
        payload = line[len(nonce) :].strip()
        if not payload:
            continue
        try:
            with _unlimited_int_str_digits():
                rec = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and "i" in rec and "ok" in rec:
            records[rec["i"]] = rec
    return records


# --------------------------------------------------------------------------
# reference-output cache
# --------------------------------------------------------------------------

class ReferenceExecutionError(RuntimeError):
    """The reference solution's own sandbox run was incomplete — an environment defect, not a
    candidate defect. Raised instead of silently caching a partial oracle: docs/07 discipline is
    that an env defect must be LOUD, because a truncated reference would permanently mis-score
    every later candidate scored against the same (task_id, suite) cache key.
    """


# Keyed on (task_id, suite) per the spec. Not functools.lru_cache: Task carries list fields
# (base_inputs/plus_inputs) and is therefore unhashable, so a plain dict is used instead.
# Protected by _reference_cache_lock because mutation sweeps parallelize; the lock is NOT held
# during the sandbox run itself (compute-then-store), only around the dict read/write.
_reference_cache: dict = {}
_reference_cache_lock = threading.Lock()


def _describe_incomplete_reference(exec_result: ExecResult, n_records: int, n_total: int) -> str:
    if exec_result.timed_out:
        return f"reference run timed out ({n_records}/{n_total} protocol records received)"
    if exec_result.oom:
        return f"reference run hit the memory limit ({n_records}/{n_total} protocol records received)"
    if exec_result.returncode != 0:
        return (
            f"reference run exited with returncode={exec_result.returncode} "
            f"({n_records}/{n_total} protocol records received)"
        )
    return f"only {n_records}/{n_total} protocol records were received (sandbox error, not a timeout)"


def _reference_records(task: Task, suite: SuiteName, *, timeout_s: float, memory_mb: int) -> dict:
    key = (task.task_id, suite)
    with _reference_cache_lock:
        cached = _reference_cache.get(key)
    if cached is not None:
        return cached

    inputs = _suite_inputs(task, suite)
    n_total = len(inputs)
    program_source = task.prompt + task.reference_solution
    nonce = secrets.token_hex(8)
    driver = _build_driver_script(program_source, task.entry_point, inputs, nonce)
    # The reference must not be shortchanged by a candidate-sized timeout: use the larger of
    # the caller's budget and this module's own size-scaled default, so a tight timeout picked
    # for an adversarial/hanging candidate can't also starve the (well-behaved) reference run
    # and turn a healthy reference into a spurious ReferenceExecutionError.
    ref_timeout_s = max(timeout_s, default_timeout_s(n_total))

    # A reference run must never fail for BUDGET reasons — full-calibration
    # finding (2026-08-14): heavy plus suites (HumanEval/83's bigint math,
    # Mbpp/255/599's individually expensive inputs) got killed by the
    # CPU/wall budget sized for ordinary candidates (SIGXCPU rc=-24,
    # partial record sets). Candidates keep tight budgets; the reference
    # alone gets ONE bounded retry at 4x wall/CPU and 2x memory before the
    # incompleteness is declared an environment defect.
    last_exec_result, last_records = None, {}
    for attempt_timeout_s, attempt_memory_mb in (
        (ref_timeout_s, memory_mb),
        (ref_timeout_s * 4, memory_mb * 2),
        # Final tier for legitimately expensive references (HumanEval/83's
        # bigint loop survived the 4x tier — calibration finding, 2026-08-14).
        (ref_timeout_s * 16, memory_mb * 4),
    ):
        exec_result = run_untrusted(
            driver,
            timeout_s=attempt_timeout_s,
            memory_mb=attempt_memory_mb,
            output_cap_bytes=_DRIVER_OUTPUT_CAP_BYTES,
        )
        records = _parse_driver_stdout(exec_result.stdout, nonce)
        complete = (
            set(records) == set(range(n_total))
            and not exec_result.timed_out
            and not exec_result.oom
            and exec_result.returncode == 0
        )
        if complete:
            break
        last_exec_result, last_records = exec_result, records
    if not complete:
        reason = _describe_incomplete_reference(last_exec_result, len(last_records), n_total)
        raise ReferenceExecutionError(
            f"reference execution incomplete for task_id={task.task_id!r} suite={suite!r}: "
            f"{reason} (persisted after 4x-budget retry)"
        )

    with _reference_cache_lock:
        _reference_cache[key] = records
    return records


# --------------------------------------------------------------------------
# output comparison
# --------------------------------------------------------------------------


def _values_equal(a, b, atol: float) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        # Exact equality first, on the ORIGINAL values, before any float() conversion:
        #   - handles equal +inf/+inf (or -inf/-inf) without going through `inf - inf`, which
        #     is `nan` and would otherwise make the atol branch below reject two IDENTICAL
        #     infinities as a "mismatch" (found via calibration smoke run on Mbpp/137's
        #     zero_count, which legitimately returns float('inf')).
        #   - handles arbitrary-precision Python ints too large for float() without raising.
        if a == b:
            return True
        try:
            fa, fb = float(a), float(b)
        except OverflowError:
            # An int outside float's range on at least one side, and not exactly equal (the
            # `a == b` check above already caught the equal case) — not representable as a
            # finite-precision "close enough" comparison either; report a mismatch rather
            # than crash (found via calibration smoke run on real MBPP tasks with huge
            # integer outputs).
            return False
        if math.isnan(fa) and math.isnan(fb):
            return True
        if atol > 0:
            diff = fa - fb
            return not math.isnan(diff) and abs(diff) <= atol
        return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_values_equal(x, y, atol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_values_equal(a[k], b[k], atol) for k in a)
    return a == b


def _record_out_hash(rec) -> str | None:
    """sha256 of the record's canonical output serialization (json family).

    A hashed record carries the digest directly; a small record's digest is
    computed here over the SAME serialization the driver would have hashed
    (plain json.dumps of the loaded value — equal Python values serialize to
    identical bytes on both sides). Returns None if the record is in the
    repr family instead."""
    if "out_sha256" in rec:
        return rec["out_sha256"]
    if "out" in rec:
        with _unlimited_int_str_digits():
            ser = json.dumps(rec["out"])
        return hashlib.sha256(ser.encode("utf-8")).hexdigest()
    return None


def _record_repr_hash(rec) -> str | None:
    """repr-family counterpart of _record_out_hash."""
    if "repr_sha256" in rec:
        return rec["repr_sha256"]
    if "out_repr" in rec:
        return hashlib.sha256(rec["out_repr"].encode("utf-8")).hexdigest()
    return None


def _input_passes(cand, ref, atol: float) -> bool:
    if cand is None or ref is None:
        return False
    if not cand.get("ok") or not ref.get("ok"):
        return False
    if "out_sha256" in cand or "out_sha256" in ref:
        # Hashed comparison is EXACT — atol is not applied (declared scope).
        h_cand, h_ref = _record_out_hash(cand), _record_out_hash(ref)
        return h_cand is not None and h_cand == h_ref
    if "repr_sha256" in cand or "repr_sha256" in ref:
        h_cand, h_ref = _record_repr_hash(cand), _record_repr_hash(ref)
        return h_cand is not None and h_cand == h_ref
    if "out" in cand and "out" in ref:
        return _values_equal(cand["out"], ref["out"], atol)
    if "out_repr" in cand and "out_repr" in ref:
        return cand["out_repr"] == ref["out_repr"]
    return False


def _describe_failure(cand, ref, *, cand_timed_out: bool, cand_oom: bool) -> str:
    """Diagnostic message for one failed input.

    Only claims timeout/oom when the candidate's ExecResult actually reports one — a missing
    protocol record with neither flag set means the candidate's own process wrote over or
    crashed before reporting that input, which is a different, more common cause than a timeout
    and must not be misreported as one.
    """
    if cand is None:
        if cand_timed_out:
            return "candidate produced no result for this input (timed out)"
        if cand_oom:
            return "candidate produced no result for this input (out of memory)"
        return "no protocol record (candidate wrote over/crashed before reporting)"
    if ref is None:
        # Should not happen post-gating: _reference_records only caches/returns a complete
        # record set (see ReferenceExecutionError). Kept as a defensive, honestly-worded
        # fallback for an internal-invariant violation rather than a claimed timeout.
        return (
            "internal invariant violation: reference has no record for this input despite "
            "gated caching — this is an environment bug, not a timeout"
        )
    if not cand.get("ok"):
        return f"candidate raised: {cand.get('err')}"
    if not ref.get("ok"):
        return f"reference raised: {ref.get('err')} (environment defect, not the candidate's fault)"
    cand_repr = cand.get("out", cand.get("out_repr", cand.get("out_sha256", cand.get("repr_sha256"))))
    ref_repr = ref.get("out", ref.get("out_repr", ref.get("out_sha256", ref.get("repr_sha256"))))
    return f"output mismatch: candidate={cand_repr!r} reference={ref_repr!r}"


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------


def evaluate_code(
    task: Task,
    code: str,
    suite: SuiteName,
    *,
    timeout_s: float,
    memory_mb: int = 512,
) -> SuiteResult:
    """Run ``code`` (a completion, see module docstring's A4 note) once against ``suite``.

    ``suite="both"`` concatenates base_inputs + plus_inputs into a single batched sandbox call
    (not two calls combined) — one pass/fail list covering both. A suite with zero inputs
    (e.g. Mbpp/793 has zero plus inputs — see rlvr/data.py) is vacuously ``passed=True``:
    ``n_passed == n_total == 0``.

    Raises :class:`ReferenceExecutionError` if the reference solution's own sandbox run for
    this ``(task_id, suite)`` is incomplete (and not already cached from a prior complete run)
    — this is an environment defect, not a verdict on ``code``, and is deliberately not
    swallowed (docs/07 discipline: an env defect must be LOUD).
    """
    inputs = _suite_inputs(task, suite)
    n_total = len(inputs)

    nonce = secrets.token_hex(8)
    program_source = task.prompt + code
    driver = _build_driver_script(program_source, task.entry_point, inputs, nonce)
    exec_result = run_untrusted(
        driver,
        timeout_s=timeout_s,
        memory_mb=memory_mb,
        output_cap_bytes=_DRIVER_OUTPUT_CAP_BYTES,
    )
    candidate_records = _parse_driver_stdout(exec_result.stdout, nonce)

    reference_records = _reference_records(
        task, suite, timeout_s=timeout_s, memory_mb=memory_mb
    )

    per_input = []
    errors = {}
    for i in range(n_total):
        cand = candidate_records.get(i)
        ref = reference_records.get(i)
        ok = _input_passes(cand, ref, task.atol)
        per_input.append(ok)
        if not ok:
            errors[i] = _describe_failure(
                cand, ref, cand_timed_out=exec_result.timed_out, cand_oom=exec_result.oom
            )

    n_passed = sum(per_input)
    return SuiteResult(
        task_id=task.task_id,
        suite=suite,
        n_total=n_total,
        n_passed=n_passed,
        passed=(n_passed == n_total),
        per_input=per_input,
        errors=errors,
        timed_out=exec_result.timed_out,
        oom=exec_result.oom,
        duration_s=exec_result.duration_s,
        exec_result=exec_result,
    )


def reward(
    task: Task,
    code: str,
    suite: SuiteName,
    *,
    timeout_s: float,
    memory_mb: int = 512,
) -> float:
    """Binary test-pass reward: 1.0 if every input in ``suite`` passes, else 0.0.

    A trivial wrapper around :func:`evaluate_code` — but it IS the interface docs/07 Phase B
    measures the adequacy of.
    """
    result = evaluate_code(task, code, suite, timeout_s=timeout_s, memory_mb=memory_mb)
    return 1.0 if result.passed else 0.0
