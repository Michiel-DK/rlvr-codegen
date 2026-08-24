"""Tests for scripts/run_calibration.py's task-selection logic (pass-2 Fix 3).

``scripts/`` is not an installed package, so the module is loaded directly by file path.
"""

from __future__ import annotations

import importlib.util
import dataclasses
import json
import sys
from pathlib import Path

import pytest

import rlvr.env as env

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_calibration.py"


def _load_run_calibration():
    spec = importlib.util.spec_from_file_location("run_calibration", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_calibration"] = module
    spec.loader.exec_module(module)
    return module


run_calibration = _load_run_calibration()


def test_limit_selects_numerically_first_tasks_not_lexicographically_first():
    """RED (pre-fix): ``sorted(task_ids)[:limit]`` is a plain string sort, so
    "HumanEval/10" < "HumanEval/2" and --limit 15 over HumanEval/0..19 kept
    0,1,10,11,...,18,19,2,3,4 (string order) instead of 0..14 — silently dropping
    numerically-early tasks 5,6,7,8,9. Verified by hand: ``sorted(...)[:15]`` on the same
    20 ids includes "HumanEval/15".."HumanEval/19" and excludes "HumanEval/5".."HumanEval/9".

    GREEN: ``_select_task_ids`` sorts by the int suffix, so --limit 15 picks exactly
    HumanEval/0..14."""
    task_ids = [f"HumanEval/{i}" for i in range(20)]

    # Demonstrate the RED behavior directly (the old, now-replaced expression) as a control.
    lexicographic_first_15 = sorted(task_ids)[:15]
    assert "HumanEval/5" not in lexicographic_first_15  # the bug, preserved as evidence
    assert "HumanEval/15" in lexicographic_first_15

    selected = run_calibration._select_task_ids(task_ids, 15)
    assert selected == [f"HumanEval/{i}" for i in range(15)]


def test_select_task_ids_no_limit_returns_all_numerically_sorted():
    task_ids = [f"Mbpp/{i}" for i in [20, 3, 100, 1]]
    assert run_calibration._select_task_ids(task_ids, None) == [
        "Mbpp/1",
        "Mbpp/3",
        "Mbpp/20",
        "Mbpp/100",
    ]


def test_task_sort_key_falls_back_to_lexicographic_on_non_numeric_tail():
    task_ids = ["HumanEval/abc", "HumanEval/2", "HumanEval/10"]
    # Numeric-tail ids sort numerically and come before the non-numeric fallback.
    assert run_calibration._select_task_ids(task_ids, None) == [
        "HumanEval/2",
        "HumanEval/10",
        "HumanEval/abc",
    ]


def test_env_failure_surfaces_at_manifest_level_and_run_does_not_crash(tmp_path, monkeypatch):
    """pass-2 Fix 4: an environment-caused failure (ReferenceExecutionError) for ONE task must
    not crash the whole calibration run, and must be visible at the manifest metrics level
    (``env_failures``) distinct from candidate/reference test failures — a Phase B reader
    shouldn't have to cross-reference individual trajectory JSONL rows to find it.

    This exercises the REAL join, not a synthetic stand-in: it truncates the actual sandbox
    stdout for HumanEval/1's REFERENCE run (via ``rlvr.env.run_untrusted``, the same technique
    as the DEFECT-2 unit test), so the ``ReferenceExecutionError`` is genuinely raised by
    ``_reference_records``'s completeness gate inside ``evaluate_code`` — not injected at
    ``run_calibration``'s call site. This proves the whole chain: env.py's gate ->
    evaluate_code's raise -> _score_task's catch -> manifest['metrics']['env_failures'] ->
    trajectory row `extra`.

    In run_calibration's calibration usage, code == task.reference_solution, so the candidate
    run and the reference run share byte-identical driver source; they're told apart by
    ordering (the candidate run happens first inside ``evaluate_code``, then the reference run)
    — truncation targets the SECOND sandbox call whose driver invokes HumanEval/1's entry point
    (``separate_paren_groups``), i.e. the reference run.
    """
    env._reference_cache.clear()
    real_run_untrusted = env.run_untrusted
    target_marker = "separate_paren_groups(*_rlvr_args)"  # HumanEval/1's entry point
    call_counts = {"n": 0}

    def selectively_truncating_run_untrusted(code, **kwargs):
        is_target = target_marker in code
        if is_target:
            call_counts["n"] += 1
        result = real_run_untrusted(code, **kwargs)
        # Truncate EVERY reference attempt (call 2 onward), not just the first:
        # the env layer retries an incomplete reference once at 4x budget, so a
        # single truncated attempt no longer produces an env failure — which also
        # pins that the retry is bounded (a persistent defect still surfaces).
        if is_target and call_counts["n"] >= 2:  # the reference run(s), not the candidate run
            lines = result.stdout.splitlines()
            truncated_stdout = "\n".join(lines[:3]) + "\n"
            # dataclasses.replace keeps this forward-compatible with whatever
            # diagnostics fields ExecResult grows (integration fix: the direct
            # constructor broke when sandbox pass 2 added five fields).
            return dataclasses.replace(
                result, stdout=truncated_stdout, timed_out=False, oom=False
            )
        return result

    monkeypatch.setattr(env, "run_untrusted", selectively_truncating_run_untrusted)

    out_dir = tmp_path / "run"
    argv = [
        "run_calibration.py",
        "--dataset",
        "humaneval",
        "--limit",
        "3",
        "--suite",
        "base",
        "--out",
        str(out_dir),
    ]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exc_info:
        run_calibration.main()
    # Non-zero exit: an env failure must be loud, not silently swallowed into a green run.
    assert exc_info.value.code == 1
    # Confirms the truncation actually fired (not a no-op that happened to still pass).
    # candidate run + reference attempts at 1x, 4x and 16x budget (bounded ladder)
    assert call_counts["n"] == 4

    manifest = json.loads((out_dir / "manifest.json").read_text())
    env_failures = manifest["metrics"]["env_failures"]
    assert len(env_failures) == 1
    assert env_failures[0]["task_id"] == "HumanEval/1"
    assert env_failures[0]["suite"] == "base"
    assert "reference execution incomplete" in env_failures[0]["what"]
    assert "HumanEval/1" in env_failures[0]["what"]
    # The other two (unaffected) tasks still scored normally — one bad task doesn't poison the
    # whole run's metrics.
    assert manifest["metrics"]["n_tasks"] == 3
    assert manifest["metrics"]["n_base_scored"] == 2
    assert manifest["metrics"]["base_failures"] == []

    # The trajectory row for the failed task is still written and readable, and carries the
    # env-failure detail in its `extra` field (not silently dropped).
    lines = (out_dir / "trajectory.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines]
    assert len(rows) == 3
    failed_row = next(r for r in rows if r["task_id"] == "HumanEval/1")
    assert failed_row["verdict_base"] is None
    assert failed_row["extra"]["env_failures"][0]["suite"] == "base"
    assert "reference execution incomplete" in failed_row["extra"]["env_failures"][0]["what"]
    healthy_row = next(r for r in rows if r["task_id"] == "HumanEval/0")
    assert healthy_row["verdict_base"] is True
    assert healthy_row["extra"].get("env_failures") is None
