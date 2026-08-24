#!/usr/bin/env python3
"""Calibration runner: score the REFERENCE solution against its own environment.

docs/07 Phase A requires a one-command reproducible base-model baseline; before any model
prediction can mean anything, the environment itself must be checked against the one solution
that is supposed to always pass. For every task in the frozen split (train + heldout — i.e.
ALL tasks, per docs/07), this runs ``task.reference_solution`` through
:func:`rlvr.env.evaluate_code` and expects ~100% pass. Any reference failure is either a bug in
this environment (report it) or a known dataset quirk (report it loudly, per task_id) — never
silently ignored.

Design note (verdict_base / verdict_plus on one record): when ``--suite both`` is selected,
this runs the reference through the base suite AND the plus suite SEPARATELY (two
`evaluate_code` calls, not one concatenated "both" call) and records both verdicts on a single
`TrajectoryRecord`. `--suite base` or `--suite plus` alone populates only that verdict, leaving
the other `None`. This is what lets one record carry the visible-vs-extended comparison per
problem that Phase B needs — the concatenated single-call "both" mode inside
`evaluate_code` is a different, coarser thing (one combined pass/fail over base+plus pooled
together) and is not what this script uses.

Usage:
    python scripts/run_calibration.py --dataset humaneval --limit 15 --suite both \\
        --out runs/humaneval-smoke15/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rlvr.data import Task, load_split, load_tasks
from rlvr.env import ReferenceExecutionError, default_timeout_s, evaluate_code
from rlvr.manifest import RunManifest, capture_package_versions, sha256_file, write_manifest
from rlvr.trajectory import TrajectoryRecord, append_records

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPLIT_PATH = REPO_ROOT / "data" / "splits" / "split_v1.json"


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _errors_as_list(errors: dict) -> list:
    """JSONL-safe: dict[int, str] keys stringify silently under json.dumps (and can't be
    read back as ints), so store failures as a list of records instead."""
    return [{"input_index": i, "error": msg} for i, msg in sorted(errors.items())]


def _task_sort_key(task_id: str):
    """Sort by the NUMERIC task suffix, not lexicographically.

    ``sorted(task_ids)`` puts "HumanEval/10" before "HumanEval/2" (string comparison), so a
    plain lexicographic sort followed by ``[:limit]`` silently skips numerically-early tasks
    once a dataset has 10+ tasks. Split on "/" and int the tail; a non-numeric tail (not
    expected for HumanEval/MBPP task_ids, but not assumed) falls back to lexicographic
    ordering, ranked after every numeric-tail id so the two orderings never need to be compared
    against each other (tuple comparison short-circuits on the second element).
    """
    prefix, _, tail = task_id.partition("/")
    try:
        return (prefix, 0, int(tail))
    except ValueError:
        return (prefix, 1, tail)


def _select_task_ids(task_ids: list, limit: int | None) -> list:
    """Numerically sort ``task_ids`` then cap to ``limit`` (None = no cap)."""
    ordered = sorted(task_ids, key=_task_sort_key)
    return ordered if limit is None else ordered[:limit]


def _score_task(task: Task, suite_arg: str, *, memory_mb: int, timeout_scale: float) -> dict:
    """Score task.reference_solution against the requested suite(s).

    Returns a dict with verdict_base/verdict_plus (bool | None), n_total_base/n_total_plus
    (int | None — None if that suite wasn't run; 0 is a real, distinct "suite has zero
    inputs" case, e.g. Mbpp/793's plus suite), duration_s, extra (JSONL-safe diagnostics), and
    env_failures (list of {"suite": ..., "what": ...} — reference-side environment defects,
    distinct from candidate/reference test failures: caught here rather than left to crash the
    whole run, because a single task's broken reference environment shouldn't abort scoring the
    rest of the split).
    """
    verdict_base = None
    verdict_plus = None
    n_total_base = None
    n_total_plus = None
    duration_s = 0.0
    extra: dict = {}
    env_failures: list = []

    if suite_arg in ("base", "both"):
        try:
            result = evaluate_code(
                task,
                task.reference_solution,
                "base",
                timeout_s=default_timeout_s(task.n_base) * timeout_scale,
                memory_mb=memory_mb,
            )
        except ReferenceExecutionError as e:
            env_failures.append({"suite": "base", "what": str(e)})
        else:
            verdict_base = result.passed
            n_total_base = result.n_total
            duration_s += result.duration_s
            if not result.passed:
                extra["base_errors"] = _errors_as_list(result.errors)
                extra["base_timed_out"] = result.timed_out
                extra["base_oom"] = result.oom

    if suite_arg in ("plus", "both"):
        try:
            result = evaluate_code(
                task,
                task.reference_solution,
                "plus",
                timeout_s=default_timeout_s(task.n_plus) * timeout_scale,
                memory_mb=memory_mb,
            )
        except ReferenceExecutionError as e:
            env_failures.append({"suite": "plus", "what": str(e)})
        else:
            verdict_plus = result.passed
            n_total_plus = result.n_total
            duration_s += result.duration_s
            if not result.passed:
                extra["plus_errors"] = _errors_as_list(result.errors)
                extra["plus_timed_out"] = result.timed_out
                extra["plus_oom"] = result.oom

    return {
        "verdict_base": verdict_base,
        "verdict_plus": verdict_plus,
        "n_total_base": n_total_base,
        "n_total_plus": n_total_plus,
        "duration_s": duration_s,
        "extra": extra,
        "env_failures": env_failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", choices=["humaneval", "mbpp"], required=True)
    parser.add_argument("--limit", type=int, default=None, help="cap the number of tasks (default: all)")
    parser.add_argument("--suite", choices=["base", "plus", "both"], default="both")
    parser.add_argument("--out", type=Path, required=True, help="output directory, e.g. runs/<run_id>/")
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT_PATH)
    parser.add_argument(
        "--timeout-scale",
        type=float,
        default=4.0,
        help="candidate-timeout multiplier; calibration scores the REFERENCE as the candidate, "
        "so it earns the same generosity the reference path gets (HumanEval/139's factorial "
        "chain timed out at the ordinary candidate budget — calibration finding, 2026-08-14)",
    )
    parser.add_argument("--memory-mb", type=int, default=512)
    args = parser.parse_args()

    split = load_split(args.split)
    all_tasks = load_tasks(args.dataset)
    task_ids = _select_task_ids(
        list(split.train[args.dataset]) + list(split.heldout[args.dataset]), args.limit
    )

    args.out.mkdir(parents=True, exist_ok=True)
    trajectory_path = args.out / "trajectory.jsonl"
    if trajectory_path.exists():
        trajectory_path.unlink()  # fresh run, not an append onto stale data

    base_failures: list[str] = []
    plus_failures: list[str] = []
    n_base_scored = 0
    n_plus_scored = 0
    # "Scored" above counts every suite that ran, including zero-input ones (vacuously
    # passed=True — see rlvr.env.evaluate_code). That is NOT the same as "verified something",
    # so zero-input suites are tracked separately and must stay visible in the manifest
    # (docs/07 / rlvr/data.py flag Mbpp/793 as exactly this case).
    zero_input_base: list[str] = []
    zero_input_plus: list[str] = []
    # Environment-caused failures (reference execution incomplete — see
    # rlvr.env.ReferenceExecutionError), distinct from candidate/reference test-verdict
    # failures above: kept at the manifest metrics level so a Phase B reader sees these without
    # cross-referencing individual trajectory JSONL rows.
    env_failures: list[dict] = []
    predictions: dict = {}

    print(f"run_calibration: dataset={args.dataset} suite={args.suite} n_tasks={len(task_ids)}")

    for task_id in task_ids:
        task = all_tasks[task_id]
        scored = _score_task(task, args.suite, memory_mb=args.memory_mb, timeout_scale=args.timeout_scale)
        verdict_base = scored["verdict_base"]
        verdict_plus = scored["verdict_plus"]

        record_extra = dict(scored["extra"])
        if scored["env_failures"]:
            record_extra["env_failures"] = scored["env_failures"]
        record = TrajectoryRecord(
            task_id=task_id,
            sample_idx=0,
            code=task.reference_solution,
            verdict_base=verdict_base,
            verdict_plus=verdict_plus,
            duration_s=scored["duration_s"],
            extra=record_extra,
        )
        append_records(trajectory_path, [record])
        predictions[task_id] = {"verdict_base": verdict_base, "verdict_plus": verdict_plus}

        for ef in scored["env_failures"]:
            env_failures.append({"task_id": task_id, "suite": ef["suite"], "what": ef["what"]})
            print(f"  ENV FAILURE {ef['suite']}  {task_id}: {ef['what']}")

        if verdict_base is not None:
            n_base_scored += 1
            if scored["n_total_base"] == 0:
                zero_input_base.append(task_id)
            if not verdict_base:
                base_failures.append(task_id)
                print(f"  FAIL base  {task_id}: {scored['extra'].get('base_errors')}")
        if verdict_plus is not None:
            n_plus_scored += 1
            if scored["n_total_plus"] == 0:
                zero_input_plus.append(task_id)
            if not verdict_plus:
                plus_failures.append(task_id)
                print(f"  FAIL plus  {task_id}: {scored['extra'].get('plus_errors')}")

    base_pass_fraction = (
        (n_base_scored - len(base_failures)) / n_base_scored if n_base_scored else None
    )
    plus_pass_fraction = (
        (n_plus_scored - len(plus_failures)) / n_plus_scored if n_plus_scored else None
    )

    metrics = {
        "n_tasks": len(task_ids),
        "n_base_scored": n_base_scored,
        "n_plus_scored": n_plus_scored,
        "base_pass_fraction": base_pass_fraction,
        "plus_pass_fraction": plus_pass_fraction,
        "base_failures": base_failures,
        "plus_failures": plus_failures,
        "zero_input_base_tasks": zero_input_base,
        "zero_input_plus_tasks": zero_input_plus,
        "env_failures": env_failures,
    }

    run_id = args.out.name or args.out.resolve().name
    try:
        split_file_str = str(args.split.resolve().relative_to(REPO_ROOT))
    except ValueError:
        split_file_str = str(args.split)  # outside the repo — record as given
    manifest = RunManifest(
        run_id=run_id,
        created_at=datetime.now(timezone.utc),
        git_sha=_git_sha(),
        package_versions=capture_package_versions(),
        split_file=split_file_str,
        split_sha256=sha256_file(args.split),
        config={
            "dataset": args.dataset,
            "limit": args.limit,
            "suite": args.suite,
            "memory_mb": args.memory_mb,
        },
        metrics=metrics,
        # code is identical for every row (task.reference_solution) — the trajectory JSONL is
        # the code-level record; predictions here is the compact per-task verdict lookup.
        predictions=predictions,
    )
    write_manifest(args.out / "manifest.json", manifest)

    print()
    print(f"summary: base_pass_fraction={base_pass_fraction} ({n_base_scored - len(base_failures)}/{n_base_scored})")
    print(f"summary: plus_pass_fraction={plus_pass_fraction} ({n_plus_scored - len(plus_failures)}/{n_plus_scored})")
    if base_failures:
        print(f"BASE FAILURES ({len(base_failures)}): {base_failures}")
    if plus_failures:
        print(f"PLUS FAILURES ({len(plus_failures)}): {plus_failures}")
    if env_failures:
        print(f"ENV FAILURES ({len(env_failures)}): {[ef['task_id'] for ef in env_failures]}")
    print(f"wrote {trajectory_path}")
    print(f"wrote {args.out / 'manifest.json'}")

    if base_failures or plus_failures or env_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
