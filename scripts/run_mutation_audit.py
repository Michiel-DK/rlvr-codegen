#!/usr/bin/env python3
"""Mutation-score audit: docs/07 Phase B's headline deliverable.

No model, no training. For every task in the (limited) split, generates deterministic mutants
of ``task.reference_solution`` (``rlvr.mutation.generate_mutants``) and measures what fraction
the VISIBLE (base) test suite catches vs what the EXTENDED (base ∪ plus) suite catches. The
delta is a measured number for "how much the test-pass reward fails to certify" — see
docs/07-rescope-verifier-adequacy.md, Phase B.

KEY OPTIMIZATION (docs/07's own instruction, see also rlvr.mutation.categorize's docstring):
EvalPlus's ``plus_inputs`` are ADDITIONAL inputs on top of ``base_inputs``, not a replacement —
so "the extended suite" for scoring purposes is base ∪ plus, and a mutant that already fails the
base suite (``killed_by_visible``) is *necessarily* also killed by the extended suite (a superset
of failing inputs can only add more ways to fail, never fewer). Only mutants that SURVIVE the
base suite need a plus-suite run at all to tell ``killed_by_extended_only`` apart from
``survived_both``. This roughly halves-to-more sandbox calls versus running both suites on every
mutant unconditionally, and is implemented directly in ``_score_mutant`` below: the plus-suite
``evaluate_code`` call only happens inside the ``if base_result.passed:`` branch.

Categories (see ``rlvr.mutation.categorize``): ``killed_by_visible``, ``killed_by_extended_only``,
``survived_both``. A fourth, non-scoring bucket, ``env_error``, covers a mutant whose evaluation
hit :class:`rlvr.env.ReferenceExecutionError` (the reference solution's own sandbox run for that
task+suite was incomplete — an environment defect, not a verdict on the mutant) or
``ExecResult.sandbox_error`` (the candidate's own sandbox-exec launch failed to start) on either
suite call. ``env_error`` mutants are EXCLUDED from every score's denominator and reported loudly
(counted, and every occurrence printed) rather than silently dropped — docs/07 discipline.

Zero-plus-input tasks (e.g. Mbpp/793 — see rlvr/data.py's module docstring) are not special-cased
in the scoring code: ``evaluate_code(..., "plus", ...)`` is vacuously ``passed=True`` for a
zero-input suite (see rlvr/env.py), so every mutant that survives base at such a task
automatically resolves to ``survived_both`` — i.e. its extended score equals its visible score,
exactly as docs/07 requires. Such tasks ARE flagged explicitly in the per-task table (a task
whose plus-suite literally cannot report anything different from its base-suite result is worth
knowing about at a glance, not just inferring from the numbers matching).

Usage:
    python scripts/run_mutation_audit.py --dataset humaneval --limit 8 \\
        --max-mutants-per-task 6 --out runs/mutation-smoke8/
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from rlvr.data import Task, load_split, load_tasks
from rlvr.env import ReferenceExecutionError, default_timeout_s, evaluate_code
from rlvr.manifest import RunManifest, capture_package_versions, sha256_file, write_manifest
from rlvr.metrics import bootstrap_ci, wilson_interval
from rlvr.mutation import (
    CATEGORY_KILLED_BY_EXTENDED_ONLY,
    CATEGORY_KILLED_BY_VISIBLE,
    CATEGORY_SURVIVED_BOTH,
    Mutant,
    categorize,
    generate_mutants,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPLIT_PATH = REPO_ROOT / "data" / "splits" / "split_v1.json"

CATEGORY_ENV_ERROR = "env_error"
_SCORING_CATEGORIES = (CATEGORY_KILLED_BY_VISIBLE, CATEGORY_KILLED_BY_EXTENDED_ONLY, CATEGORY_SURVIVED_BOTH)


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _task_sort_key(task_id: str):
    """Sort by the NUMERIC task suffix, not lexicographically — see the identical helper (and
    its rationale) in scripts/run_calibration.py; duplicated here rather than imported so this
    script stays independent of that one (neither owns the other)."""
    prefix, _, tail = task_id.partition("/")
    try:
        return (prefix, 0, int(tail))
    except ValueError:
        return (prefix, 1, tail)


def _select_task_ids(task_ids: list, limit: int | None) -> list:
    ordered = sorted(task_ids, key=_task_sort_key)
    return ordered if limit is None else ordered[:limit]


# --------------------------------------------------------------------------
# per-mutant scoring
# --------------------------------------------------------------------------


def _score_mutant(task: Task, mutant: Mutant, *, memory_mb: int) -> dict:
    """Score one mutant. Returns a JSONL-ready dict (see module docstring for category meanings
    and the KEY OPTIMIZATION this implements)."""
    row = {
        "task_id": task.task_id,
        "mutant_id": mutant.mutant_id,
        "operator": mutant.operator,
        "line": mutant.line,
        "col": mutant.col,
        "base_n_passed": None,
        "base_n_total": None,
        "plus_n_passed": None,
        "plus_n_total": None,
        "env_error_detail": None,
    }

    try:
        base_result = evaluate_code(
            task, mutant.source, "base", timeout_s=default_timeout_s(task.n_base), memory_mb=memory_mb
        )
    except ReferenceExecutionError as e:
        row["category"] = CATEGORY_ENV_ERROR
        row["env_error_detail"] = f"base: {e}"
        return row

    row["base_n_passed"] = base_result.n_passed
    row["base_n_total"] = base_result.n_total

    if base_result.exec_result.sandbox_error:
        row["category"] = CATEGORY_ENV_ERROR
        row["env_error_detail"] = "base: sandbox_error (candidate sandbox-exec failed to launch)"
        return row

    if not base_result.passed:
        # KEY OPTIMIZATION: already killed by the visible suite — the plus suite cannot un-kill
        # it (base ⊆ extended), so it is not run at all for this mutant.
        row["category"] = CATEGORY_KILLED_BY_VISIBLE
        return row

    try:
        plus_result = evaluate_code(
            task, mutant.source, "plus", timeout_s=default_timeout_s(task.n_plus), memory_mb=memory_mb
        )
    except ReferenceExecutionError as e:
        row["category"] = CATEGORY_ENV_ERROR
        row["env_error_detail"] = f"plus: {e}"
        return row

    row["plus_n_passed"] = plus_result.n_passed
    row["plus_n_total"] = plus_result.n_total

    if plus_result.exec_result.sandbox_error:
        row["category"] = CATEGORY_ENV_ERROR
        row["env_error_detail"] = "plus: sandbox_error (candidate sandbox-exec failed to launch)"
        return row

    row["category"] = categorize(passed_base=base_result.passed, passed_plus=plus_result.passed)
    return row


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------


def _wilson_pct(successes: int, trials: int) -> dict:
    if trials == 0:
        return {"point": None, "ci_lo": None, "ci_hi": None, "n": 0}
    lo, hi = wilson_interval(successes, trials)
    return {"point": successes / trials, "ci_lo": lo, "ci_hi": hi, "n": trials}


def _per_task_summary(task_id: str, rows: list[dict], zero_plus_inputs: bool) -> dict:
    by_cat = {c: 0 for c in _SCORING_CATEGORIES}
    by_cat[CATEGORY_ENV_ERROR] = 0
    for r in rows:
        by_cat[r["category"]] += 1

    n_valid = sum(by_cat[c] for c in _SCORING_CATEGORIES)
    killed_visible = by_cat[CATEGORY_KILLED_BY_VISIBLE]
    killed_extended_only = by_cat[CATEGORY_KILLED_BY_EXTENDED_ONLY]
    survived_both = by_cat[CATEGORY_SURVIVED_BOTH]

    visible_score = killed_visible / n_valid if n_valid else None
    extended_score = (killed_visible + killed_extended_only) / n_valid if n_valid else None
    gap = (extended_score - visible_score) if n_valid else None

    return {
        "task_id": task_id,
        "n_mutants_total": len(rows),
        "n_valid": n_valid,
        "killed_by_visible": killed_visible,
        "killed_by_extended_only": killed_extended_only,
        "survived_both": survived_both,
        "env_error": by_cat[CATEGORY_ENV_ERROR],
        "visible_score": visible_score,
        "extended_score": extended_score,
        "gap": gap,
        "zero_plus_inputs": zero_plus_inputs,
    }


def _render_results_md(
    *,
    dataset: str,
    n_tasks: int,
    n_mutants_total: int,
    n_valid: int,
    n_env_error: int,
    n_survived_both: int,
    visible: dict,
    extended: dict,
    gap_point: float | None,
    gap_ci: tuple[float, float] | None,
    per_task: list[dict],
    seed: int,
) -> str:
    def _fmt_pct(stat: dict) -> str:
        if stat["point"] is None:
            return "n/a"
        return f"{stat['point']:.1%} (95% CI {stat['ci_lo']:.1%}–{stat['ci_hi']:.1%}, n={stat['n']})"

    gap_str = "n/a"
    if gap_point is not None and gap_ci is not None:
        gap_str = f"{gap_point:+.1%} (95% CI {gap_ci[0]:+.1%}–{gap_ci[1]:+.1%})"

    pooled_gap_str = "n/a"
    if visible["point"] is not None and extended["point"] is not None:
        pooled_gap_str = f"{extended['point'] - visible['point']:+.1%}"

    lines = [
        f"# Mutation-score audit — {dataset}",
        "",
        "docs/07 Phase B: mutation score visible vs extended, over reference-solution mutants.",
        f"Seed: {seed}. N tasks: {n_tasks}. N mutants attempted: {n_mutants_total} "
        f"(N valid, env_error excluded: {n_valid}; env_error: {n_env_error}).",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Mutation score — visible (base) suite | {_fmt_pct(visible)} ¹ |",
        f"| Mutation score — extended (base ∪ plus) suite | {_fmt_pct(extended)} ¹ |",
        f"| GAP, pooled (extended − visible, = row 2 − row 1) | {pooled_gap_str} |",
        f"| GAP, mean per-task (extended − visible) ² | {gap_str} |",
        f"| N mutants (valid / attempted) | {n_valid} / {n_mutants_total} |",
        f"| N tasks | {n_tasks} |",
        f"| env_error count | {n_env_error} |",
        f"| survived_both count | {n_survived_both} |",
        "",
        "¹ Pooled-mutant Wilson interval: treats all valid mutants as independent Bernoulli "
        "trials, which they are not (mutants cluster within tasks) — read these CIs as "
        "anti-conservative. ² The task-mean GAP weights every task equally regardless of its "
        "mutant count, so it need not equal the pooled row-2 − row-1 difference; both are "
        "reported to keep the arithmetic honest (review finding, PR #13).",
        "",
        "`survived_both` is **not** equivalence and the extended suite is **not** ground truth "
        "(docs/07 forbids both claims) — it means the mutant is not distinguishable by either "
        "suite: possibly the mutation is behaviorally equivalent, possibly both suites simply "
        "miss it. GAP's point estimate is the mean, over tasks with at least one valid mutant, "
        "of that task's own (extended_score − visible_score); its 95% CI is a percentile "
        f"bootstrap (n_boot=10000, seed={seed}) over those same per-task gap values — a "
        "task-resampled CI, not a mutant-resampled one, since a mutant's fate is not "
        "independent of which task it came from.",
        "",
        "## Per-task",
        "",
        "| task_id | n_valid | killed_visible | killed_ext_only | survived_both | env_error "
        "| visible | extended | gap | flags |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in per_task:
        flags = "zero-plus-inputs" if t["zero_plus_inputs"] else ""
        if t["n_valid"] == 0:
            flags = (flags + "; " if flags else "") + "no valid mutants (excluded from headline)"
        vis = f"{t['visible_score']:.1%}" if t["visible_score"] is not None else "n/a"
        ext = f"{t['extended_score']:.1%}" if t["extended_score"] is not None else "n/a"
        gp = f"{t['gap']:+.1%}" if t["gap"] is not None else "n/a"
        lines.append(
            f"| {t['task_id']} | {t['n_valid']} | {t['killed_by_visible']} | "
            f"{t['killed_by_extended_only']} | {t['survived_both']} | {t['env_error']} | "
            f"{vis} | {ext} | {gp} | {flags} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", choices=["humaneval", "mbpp"], required=True)
    parser.add_argument("--limit", type=int, default=None, help="cap the number of tasks (default: all)")
    parser.add_argument("--max-mutants-per-task", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--out", type=Path, required=True, help="output directory, e.g. runs/<run_id>/")
    parser.add_argument("--workers", type=int, default=4, help="ThreadPoolExecutor size (sandbox calls are subprocess-bound)")
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT_PATH)
    parser.add_argument("--memory-mb", type=int, default=512)
    parser.add_argument(
        "--exclude-tasks",
        default="",
        help="comma-separated task_ids excluded as env-limited (their reference needs budgets "
        "candidates don't get, so mutant verdicts there measure the budget, not the suite — "
        "e.g. HumanEval/83, Mbpp/255 per calibration v4, 2026-08-14). Recorded in the manifest.",
    )
    args = parser.parse_args()

    split = load_split(args.split)
    all_tasks = load_tasks(args.dataset)
    task_ids = _select_task_ids(
        list(split.train[args.dataset]) + list(split.heldout[args.dataset]), args.limit
    )
    excluded = [t.strip() for t in args.exclude_tasks.split(",") if t.strip()]
    unknown_excluded = [t for t in excluded if t not in task_ids]
    if unknown_excluded:
        raise SystemExit(f"--exclude-tasks names unknown/unselected task ids: {unknown_excluded}")
    if excluded:
        task_ids = [t for t in task_ids if t not in excluded]
        print(f"  EXCLUDED (env-limited, declared): {excluded}")

    args.out.mkdir(parents=True, exist_ok=True)
    mutants_path = args.out / "mutants.jsonl"
    if mutants_path.exists():
        mutants_path.unlink()  # fresh run, not an append onto stale data

    print(
        f"run_mutation_audit: dataset={args.dataset} n_tasks={len(task_ids)} "
        f"max_mutants_per_task={args.max_mutants_per_task} seed={args.seed} workers={args.workers}"
    )

    # Build the flat work list up front: (task, mutant) pairs across ALL selected tasks, so the
    # ThreadPoolExecutor pool is shared across tasks rather than one pool per task (a single
    # task's mutants finishing early lets the pool immediately start the next task's work).
    work: list[tuple[Task, Mutant]] = []
    task_mutant_counts: dict[str, int] = {}
    for task_id in task_ids:
        task = all_tasks[task_id]
        mutants = generate_mutants(task.reference_solution, seed=args.seed, max_mutants=args.max_mutants_per_task)
        task_mutant_counts[task_id] = len(mutants)
        for m in mutants:
            work.append((task, m))
        if not mutants:
            print(f"  NOTE {task_id}: generate_mutants produced 0 mutants (no supported operator sites found)")

    rows_by_task: dict[str, list[dict]] = {task_id: [] for task_id in task_ids}
    n_done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_score_mutant, task, mutant, memory_mb=args.memory_mb): (task, mutant) for task, mutant in work}
        for fut in as_completed(futures):
            task, mutant = futures[fut]
            try:
                row = fut.result()
            except Exception as exc:  # noqa: BLE001 — a single unexpected exception must not
                # discard the whole sweep's output (review finding, PR #13); it lands in
                # env_error, loudly, and the sweep completes.
                row = {
                    "task_id": task.task_id,
                    "mutant_id": mutant.mutant_id,
                    "operator": mutant.operator,
                    "category": CATEGORY_ENV_ERROR,
                    "env_error_detail": f"unexpected {type(exc).__name__}: {exc}",
                    "base_n_passed": None,
                    "base_n_total": None,
                    "plus_n_passed": None,
                    "plus_n_total": None,
                }
            rows_by_task[task.task_id].append(row)
            if row["category"] == CATEGORY_ENV_ERROR:
                print(f"  ENV ERROR {task.task_id} mutant={mutant.mutant_id} op={mutant.operator}: {row['env_error_detail']}")
            n_done += 1
            if n_done % 25 == 0 or n_done == len(work):
                print(f"  scored {n_done}/{len(work)} mutants")

    # Deterministic row order in the JSONL output: (task_id numeric, mutant_id) — NOT completion
    # order, which depends on thread scheduling and would make the file non-reproducible byte
    # for byte across runs even though the underlying scores are deterministic.
    with open(mutants_path, "a") as f:
        for task_id in task_ids:
            for row in sorted(rows_by_task[task_id], key=lambda r: r["mutant_id"]):
                f.write(json.dumps(row, sort_keys=True) + "\n")

    per_task = []
    for task_id in task_ids:
        task = all_tasks[task_id]
        per_task.append(_per_task_summary(task_id, rows_by_task[task_id], zero_plus_inputs=(task.n_plus == 0)))

    n_mutants_total = sum(t["n_mutants_total"] for t in per_task)
    n_valid = sum(t["n_valid"] for t in per_task)
    n_env_error = sum(t["env_error"] for t in per_task)
    n_survived_both = sum(t["survived_both"] for t in per_task)
    killed_visible_total = sum(t["killed_by_visible"] for t in per_task)
    killed_extended_only_total = sum(t["killed_by_extended_only"] for t in per_task)

    visible = _wilson_pct(killed_visible_total, n_valid)
    extended = _wilson_pct(killed_visible_total + killed_extended_only_total, n_valid)

    per_task_gaps = [t["gap"] for t in per_task if t["gap"] is not None]
    gap_point = sum(per_task_gaps) / len(per_task_gaps) if per_task_gaps else None
    gap_ci = bootstrap_ci(per_task_gaps, seed=args.seed) if len(per_task_gaps) > 0 else None

    results_md = _render_results_md(
        dataset=args.dataset,
        n_tasks=len(task_ids),
        n_mutants_total=n_mutants_total,
        n_valid=n_valid,
        n_env_error=n_env_error,
        n_survived_both=n_survived_both,
        visible=visible,
        extended=extended,
        gap_point=gap_point,
        gap_ci=gap_ci,
        per_task=per_task,
        seed=args.seed,
    )
    (args.out / "results.md").write_text(results_md)

    run_id = args.out.name or args.out.resolve().name
    try:
        split_file_str = str(args.split.resolve().relative_to(REPO_ROOT))
    except ValueError:
        split_file_str = str(args.split)
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
            "max_mutants_per_task": args.max_mutants_per_task,
            "seed": args.seed,
            "workers": args.workers,
            "memory_mb": args.memory_mb,
            "excluded_tasks_env_limited": excluded,
        },
        metrics={
            "n_tasks": len(task_ids),
            "n_mutants_total": n_mutants_total,
            "n_valid": n_valid,
            "n_env_error": n_env_error,
            "n_survived_both": n_survived_both,
            "mutation_score_visible": visible,
            "mutation_score_extended": extended,
            "gap_pooled": (
                extended["point"] - visible["point"]
                if visible["point"] is not None and extended["point"] is not None
                else None
            ),
            "gap_point": gap_point,
            "gap_ci": list(gap_ci) if gap_ci is not None else None,
            "task_mutant_counts": task_mutant_counts,
        },
        predictions={t["task_id"]: t for t in per_task},
    )
    write_manifest(args.out / "manifest.json", manifest)

    print()
    print(results_md)
    print(f"wrote {mutants_path}")
    print(f"wrote {args.out / 'results.md'}")
    print(f"wrote {args.out / 'manifest.json'}")

    if n_env_error:
        print(f"ENV ERRORS: {n_env_error} mutant(s) hit an environment defect — see above and mutants.jsonl")


if __name__ == "__main__":
    main()
