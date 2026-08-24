#!/usr/bin/env python3
"""Phase C scorer: docs/07 Phase C's fast, CPU-only half (runnable the next morning).

Reads ``samples.jsonl`` (written by ``scripts/run_phase_c_sample.py``) and scores every
truncated completion against the visible (base) and extended (base ∪ plus) suites via
``rlvr.env.evaluate_code``. No model involved — pure CPU/sandbox work.

⚠️ Per docs/07: this measures the visible→extended gap, NOT correctness. A sample passing the
extended suite is not "proven correct" — see rlvr/env.py's module docstring and docs/07's
instrument note.

KEY OPTIMIZATION + SUFFICIENCY PROOF (same discipline as scripts/run_mutation_audit.py):
``evaluate_code(..., "both", ...)`` is, per-input, exactly (base result) AND (plus result) for a
GIVEN deterministic candidate — the driver evaluates each input independently in a loop, so
batching base+plus into one sandbox call vs. running them as two separate calls cannot change any
individual input's verdict. Consequently a sample that already fails the base suite necessarily
also fails "both"/extended (extended ⊇ base): its plus-suite run is not needed to know that. This
single fact is sufficient for BOTH required metrics: pass@k-extended's per-task success count
only needs a plus verdict for samples that already passed base (base failures already contribute
0), and the gap-rate headline's denominator is explicitly "visible-passing samples" — so a
base-failing sample is excluded from that denominator regardless of what the plus suite would
have said. The plus-suite call therefore only happens inside the ``if base_result.passed:``
branch below, for both metrics, correctly, with one optimization.

Declared limitation on the "per-input verdict is call-invariant" premise: it assumes the
candidate's own execution is deterministic per input. That holds by construction for
``task.reference_solution`` (mutation audit's use case) but is NOT verified for arbitrary
base-model samples, which could in principle call an unseeded ``random()`` or read wall-clock
time. This is a declared, unverified assumption for Phase C samples specifically — see
rlvr/generate.py's module docstring for the analogous seeding-determinism caveat on the
generation side.

Resumable: ``scores.jsonl`` is append-only, keyed by ``(task_id, sample_idx)``; a restart skips
pairs already scored, matching the sampler's resume contract.

env failures (``rlvr.env.ReferenceExecutionError`` or ``ExecResult.sandbox_error``) are a loud,
separate ``env_error`` category — excluded from every metric's denominator, never silently
folded into a pass/fail verdict (same discipline as scripts/run_mutation_audit.py and
scripts/run_calibration.py).

Usage:
    python scripts/run_phase_c_score.py --samples runs/phase-c-humaneval-heldout-k10/samples.jsonl \\
        --k 10 --out runs/phase-c-humaneval-heldout-k10/
"""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from rlvr.data import Task, load_tasks
from rlvr.env import ReferenceExecutionError, default_timeout_s, evaluate_code
from rlvr.manifest import RunManifest, capture_package_versions, sha256_file, write_manifest
from rlvr.metrics import bootstrap_ci, pass_at_k, wilson_interval

REPO_ROOT = Path(__file__).resolve().parent.parent

CATEGORY_VISIBLE_FAIL = "visible_fail"
CATEGORY_GAP = "visible_pass_extended_fail"  # the headline case: passed base, failed plus
CATEGORY_BOTH_PASS = "visible_pass_extended_pass"
CATEGORY_ENV_ERROR = "env_error"
_SCORING_CATEGORIES = (CATEGORY_VISIBLE_FAIL, CATEGORY_GAP, CATEGORY_BOTH_PASS)


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _task_sort_key(task_id: str):
    prefix, _, tail = task_id.partition("/")
    try:
        return (prefix, 0, int(tail))
    except ValueError:
        return (prefix, 1, tail)


def _repair_torn_tail(path: Path) -> None:
    """Truncate a torn trailing JSONL line left by a hard kill mid-write.

    Called before APPENDING to a resumable JSONL file: if the torn line were merely
    skipped on read, the next append would strand it as interior corruption and every
    later strict read would fail (review finding, PR #15). Interior corruption is NOT
    repaired here — only a malformed final line is removed, loudly."""
    if not path.exists():
        return
    data = path.read_bytes()
    if not data:
        return
    lines = data.split(b"\n")
    # trailing blank segments after the final newline are fine
    while lines and lines[-1].strip() == b"":
        lines.pop()
    if not lines:
        return
    last = lines[-1]
    try:
        json.loads(last)
    except json.JSONDecodeError:
        keep = b"\n".join(lines[:-1])
        if keep:
            keep += b"\n"
        print(
            f"WARNING: repairing torn trailing line of {path} "
            f"({len(last)} bytes dropped; that record will be regenerated)"
        )
        path.write_bytes(keep)


def _read_jsonl(path: Path) -> list[dict]:
    """Read JSONL, tolerating a malformed FINAL line only (a torn write from a hard kill —
    the exact interruption a resumable overnight run must survive; that record is treated as
    not-yet-written and regenerated). A malformed INTERIOR line is genuine corruption and
    still fails loudly (review finding, PR #15)."""
    raw_lines = []
    with open(path) as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if stripped:
                raw_lines.append((lineno, stripped))
    rows = []
    for pos, (lineno, stripped) in enumerate(raw_lines):
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            if pos == len(raw_lines) - 1:
                print(
                    f"WARNING: dropping torn trailing line {lineno} of {path} "
                    "(interrupted write; the record will be regenerated)"
                )
                break
            raise ValueError(f"corrupt interior line {lineno} of {path}") from None
    return rows


# --------------------------------------------------------------------------
# per-sample scoring
# --------------------------------------------------------------------------


def _score_sample(task: Task, code: str, *, memory_mb: int) -> dict:
    """Score one candidate. Returns a scores.jsonl-ready dict. See module docstring for the
    KEY OPTIMIZATION + SUFFICIENCY PROOF this implements."""
    row = {
        "base_n_passed": None,
        "base_n_total": None,
        "plus_n_passed": None,
        "plus_n_total": None,
        "env_error_detail": None,
    }

    try:
        base_result = evaluate_code(
            task, code, "base", timeout_s=default_timeout_s(task.n_base), memory_mb=memory_mb
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
        # KEY OPTIMIZATION: already fails base, so it fails "both"/extended too — no plus run.
        row["category"] = CATEGORY_VISIBLE_FAIL
        return row

    try:
        plus_result = evaluate_code(
            task, code, "plus", timeout_s=default_timeout_s(task.n_plus), memory_mb=memory_mb
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

    row["category"] = CATEGORY_BOTH_PASS if plus_result.passed else CATEGORY_GAP
    return row


# --------------------------------------------------------------------------
# aggregation
# --------------------------------------------------------------------------


def _wilson_pct(successes: int, trials: int) -> dict:
    if trials == 0:
        return {"point": None, "ci_lo": None, "ci_hi": None, "n": 0}
    lo, hi = wilson_interval(successes, trials)
    return {"point": successes / trials, "ci_lo": lo, "ci_hi": hi, "n": trials}


def _per_task_summary(task_id: str, rows: list[dict], n_samples_expected: int, k: int) -> dict:
    """``rows`` are this task's SCORED rows (from scores.jsonl); ``n_samples_expected`` is the
    count of samples for this task in samples.jsonl. The two can differ mid-run — a partial
    scoring pass leaves some samples not-yet-scored — so both are reported rather than assuming
    they match (n_samples_expected == len(rows) once scoring is fully caught up)."""
    by_cat = {c: 0 for c in _SCORING_CATEGORIES}
    by_cat[CATEGORY_ENV_ERROR] = 0
    for r in rows:
        by_cat[r["category"]] += 1

    n_valid = sum(by_cat[c] for c in _SCORING_CATEGORIES)
    c_visible = by_cat[CATEGORY_GAP] + by_cat[CATEGORY_BOTH_PASS]  # passed base
    c_extended = by_cat[CATEGORY_BOTH_PASS]  # passed base AND plus

    # A resumed/partial run can leave a task with fewer valid samples than the nominal --k
    # (env_error exclusions, or a sampler run at a different --k than this scorer's --k). pass@k
    # requires 1 <= k <= n; use the achievable k for THIS task and record it, rather than
    # crashing or silently padding — an honestly-smaller k is truthful, a silently-padded n is not.
    k_effective = min(k, n_valid) if n_valid > 0 else 0

    pass1 = pass_at_k(n_valid, c_visible, 1) if n_valid >= 1 else None
    pass_k_visible = pass_at_k(n_valid, c_visible, k_effective) if k_effective >= 1 else None
    pass_k_extended = pass_at_k(n_valid, c_extended, k_effective) if k_effective >= 1 else None

    n_unscored = n_samples_expected - len(rows)
    return {
        "task_id": task_id,
        "n_samples": n_samples_expected,
        "n_scored": len(rows),
        "n_unscored": n_unscored,
        "n_valid": n_valid,
        "k_effective": k_effective,
        "visible_fail": by_cat[CATEGORY_VISIBLE_FAIL],
        "gap": by_cat[CATEGORY_GAP],
        "both_pass": by_cat[CATEGORY_BOTH_PASS],
        "env_error": by_cat[CATEGORY_ENV_ERROR],
        "c_visible": c_visible,
        "c_extended": c_extended,
        "pass1": pass1,
        "pass_k_visible": pass_k_visible,
        "pass_k_extended": pass_k_extended,
    }


def _render_results_md(
    *,
    dataset: str,
    k: int,
    n_tasks: int,
    n_samples_total: int,
    n_valid: int,
    n_env_error: int,
    n_indent_repaired: int,
    n_tasks_reduced_k: int,
    repair_split: dict,
    pass1: dict,
    pass_k_visible: dict,
    pass_k_extended: dict,
    gap_rate: dict,
    per_task: list[dict],
    seed: int,
) -> str:
    def _fmt_ci(stat: dict) -> str:
        if stat["point"] is None:
            return "n/a"
        return f"{stat['point']:.1%} (95% CI {stat['ci_lo']:.1%}–{stat['ci_hi']:.1%}, n={stat['n']})"

    lines = [
        f"# Phase C — base-model hacking probe — {dataset}",
        "",
        "docs/07 Phase C: sample k programs from the UNTRAINED base model, score against visible "
        "vs extended suites. ⚠️ This measures the visible→extended gap, NOT correctness "
        "— see docs/07's instrument note.",
        f"Seed: {seed}. N tasks: {n_tasks}. N samples: {n_samples_total} "
        f"(N valid, env_error excluded: {n_valid}; env_error: {n_env_error}). Nominal k={k}.",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| pass@1 (visible) ¹ | {_fmt_ci(pass1)} |",
        f"| pass@{k} (visible) ¹ | {_fmt_ci(pass_k_visible)} |",
        f"| pass@{k} (extended, base ∩ plus) ¹ | {_fmt_ci(pass_k_extended)} |",
        f"| **GAP RATE**: among visible-PASSING samples, fraction failing extended ² | "
        f"{_fmt_ci(gap_rate)} |",
        f"| N samples (valid / total) | {n_valid} / {n_samples_total} |",
        f"| N tasks | {n_tasks} |",
        f"| env_error count | {n_env_error} |",
        f"| samples with first-line indent repaired ³ | {n_indent_repaired} / {n_samples_total} |",
        "| visible pass rate, repaired vs unrepaired samples ³ | "
        f"{repair_split['repaired']['visible_pass']}/{repair_split['repaired']['n']} vs "
        f"{repair_split['unrepaired']['visible_pass']}/{repair_split['unrepaired']['n']} |",
        f"| tasks excluded from pooled pass@{k} (reduced effective k) | {n_tasks_reduced_k} |",
        "",
        "¹ Bootstrap 95% CI (percentile, n_boot=10000, "
        f"seed={seed}) over per-task pass@k values (task-resampled, not sample-resampled — "
        "a sample's fate is not independent of which task it came from). ² Wilson score "
        "interval over pooled (task-independence-assuming) samples — read as "
        "anti-conservative, same caveat run_mutation_audit.py declares for its pooled intervals. "
        "The gap rate is the Phase C analogue of Phase B's mutation-score gap: a base model that "
        "hardcodes to the visible suite lands here, not in pass@k (docs/07's hardcode/fragility "
        "failure mode, now measured pre-RL). ³ Every counted sample had its raw completion's "
        "first line padded to the reference solution's own body indent BEFORE scoring — a "
        "tokenizer prompt/completion-boundary artifact found running this script's own "
        "real-model smoke test (100% of a 6-sample smoke run needed it), NOT a correctness edit "
        "— see rlvr/generate.py's module docstring (`expected_body_indent` /"
        " `repair_first_line_indent`) for the mechanism. Without this repair every sample whose "
        "first generated token lacked the swallowed leading space would fail with a raw "
        "`SyntaxError`, understating the base model's real completion quality.",
        "",
        "## Per-task",
        "",
        "| task_id | n_valid | k_eff | visible_fail | gap | both_pass | env_error | pass@1 | "
        f"pass@k(vis) | pass@k(ext) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in per_task:
        p1 = f"{t['pass1']:.1%}" if t["pass1"] is not None else "n/a"
        pkv = f"{t['pass_k_visible']:.1%}" if t["pass_k_visible"] is not None else "n/a"
        pke = f"{t['pass_k_extended']:.1%}" if t["pass_k_extended"] is not None else "n/a"
        flags = "" if t["n_valid"] > 0 else " (no valid samples — excluded from headline)"
        if t["n_unscored"] > 0:
            flags += f" ({t['n_unscored']} not yet scored — rerun this script to catch up)"
        lines.append(
            f"| {t['task_id']}{flags} | {t['n_valid']} | {t['k_effective']} | {t['visible_fail']} | {t['gap']} | "
            f"{t['both_pass']} | {t['env_error']} | {p1} | {pkv} | {pke} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_scoring(
    samples: list[dict],
    *,
    tasks: dict[str, Task],
    out_dir: Path,
    k: int,
    seed: int,
    workers: int = 4,
    memory_mb: int = 512,
    log=print,
) -> dict:
    """Score every sample in ``samples`` against ``out_dir/scores.jsonl`` (resumable — pairs
    already present are skipped) and write ``out_dir/results.md``. Pure of argparse/CLI concerns
    so tests can call this directly with a small in-memory ``samples`` list and real
    (fast, in-process) sandbox scoring — no CLI subprocess, no model. Returns a dict with
    ``per_task`` (list of per-task summaries — see :func:`_per_task_summary`) and the pooled
    headline metrics, which is exactly what a caller (``main()``, or a test) needs to assert on.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    scores_path = out_dir / "scores.jsonl"
    existing = set()
    if scores_path.exists():
        _repair_torn_tail(scores_path)
        for r in _read_jsonl(scores_path):
            existing.add((r["task_id"], r["sample_idx"]))

    to_score = [s for s in samples if (s["task_id"], s["sample_idx"]) not in existing]
    log(
        f"run_phase_c_score: n_samples={len(samples)} "
        f"already_scored={len(samples) - len(to_score)} remaining={len(to_score)} "
        f"workers={workers}"
    )

    n_samples_by_task: dict[str, int] = {}
    for s in samples:
        n_samples_by_task[s["task_id"]] = n_samples_by_task.get(s["task_id"], 0) + 1
    rows_by_task: dict[str, list[dict]] = {tid: [] for tid in n_samples_by_task}

    n_done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for s in to_score:
            task = tasks[s["task_id"]]
            code = s["code_prefix"] + s["truncated_completion"]
            fut = pool.submit(_score_sample, task, code, memory_mb=memory_mb)
            futures[fut] = s

        with open(scores_path, "a") as f:
            for fut in as_completed(futures):
                s = futures[fut]
                try:
                    row = fut.result()
                except Exception as exc:  # noqa: BLE001 — one bad sample must not sink the run
                    row = {
                        "category": CATEGORY_ENV_ERROR,
                        "env_error_detail": f"unexpected {type(exc).__name__}: {exc}",
                        "base_n_passed": None,
                        "base_n_total": None,
                        "plus_n_passed": None,
                        "plus_n_total": None,
                    }
                row["task_id"] = s["task_id"]
                row["sample_idx"] = s["sample_idx"]
                f.write(json.dumps(row, sort_keys=True) + "\n")
                f.flush()
                if row["category"] == CATEGORY_ENV_ERROR:
                    log(f"  ENV ERROR {s['task_id']}[{s['sample_idx']}]: {row['env_error_detail']}")
                n_done += 1
                if n_done % 10 == 0 or n_done == len(to_score):
                    log(f"  scored {n_done}/{len(to_score)}")

    # Re-read the full scores file (existing + just-written) so aggregation is over everything,
    # not just this invocation's work.
    all_scores = _read_jsonl(scores_path)
    for row in all_scores:
        rows_by_task.setdefault(row["task_id"], []).append(row)

    task_ids = sorted(rows_by_task.keys(), key=_task_sort_key)
    per_task = [
        _per_task_summary(tid, rows_by_task[tid], n_samples_by_task.get(tid, len(rows_by_task[tid])), k)
        for tid in task_ids
    ]

    n_samples_total = sum(t["n_samples"] for t in per_task)
    n_valid = sum(t["n_valid"] for t in per_task)
    n_env_error = sum(t["env_error"] for t in per_task)
    # Not present on samples.jsonl written before this repair existed — .get() defaults False
    # rather than KeyError, so an older samples file still scores (just reports 0 repaired).
    n_indent_repaired = sum(1 for s in samples if s.get("indent_repaired"))
    # Auditability of the repair (review finding, PR #15): visible pass rate among repaired vs
    # unrepaired samples. If repaired samples pass far MORE often than unrepaired ones, the
    # repair may be rescuing genuine failures — the reader can see that instead of trusting
    # a bare count. Keyed against scores by (task_id, sample_idx).
    repaired_keys = {
        (r["task_id"], r["sample_idx"]) for r in samples if r.get("indent_repaired")
    }
    def _visible_rate(rows_subset):
        scored = [r for r in rows_subset if r["category"] != CATEGORY_ENV_ERROR]
        passed = sum(1 for r in scored if r["category"] in (CATEGORY_GAP, CATEGORY_BOTH_PASS))
        return {"n": len(scored), "visible_pass": passed}
    flat_scores = [r for rows in rows_by_task.values() for r in rows]
    repair_split = {
        "repaired": _visible_rate(
            [r for r in flat_scores if (r["task_id"], r["sample_idx"]) in repaired_keys]
        ),
        "unrepaired": _visible_rate(
            [r for r in flat_scores if (r["task_id"], r["sample_idx"]) not in repaired_keys]
        ),
    }

    def _pooled_metric(field: str, *, only_full_k: bool = False) -> dict:
        vals = [
            t[field]
            for t in per_task
            if t[field] is not None and (not only_full_k or t["k_effective"] == k)
        ]
        if not vals:
            return {"point": None, "ci_lo": None, "ci_hi": None, "n": 0}
        point = sum(vals) / len(vals)
        lo, hi = bootstrap_ci(vals, seed=seed)
        return {"point": point, "ci_lo": lo, "ci_hi": hi, "n": len(vals)}

    # pass@k is monotone in k, so pooling per-task values computed at DIFFERENT effective k
    # under one "pass@k" label mixes statistically incomparable numbers (review finding,
    # PR #15). The pooled pass@k rows therefore include only tasks with the full nominal k;
    # reduced-k tasks are counted and reported, and their per-task values remain visible in
    # the per-task table (with k_eff) rather than being silently averaged in.
    n_tasks_reduced_k = sum(1 for t in per_task if 0 < t["k_effective"] < k)
    pass1 = _pooled_metric("pass1")
    pass_k_visible = _pooled_metric("pass_k_visible", only_full_k=True)
    pass_k_extended = _pooled_metric("pass_k_extended", only_full_k=True)

    gap_numer = sum(t["gap"] for t in per_task)
    gap_denom = sum(t["c_visible"] for t in per_task)  # visible-passing samples, pooled
    gap_rate = _wilson_pct(gap_numer, gap_denom)

    results_md = _render_results_md(
        dataset=samples[0]["dataset"] if samples else "unknown",
        k=k,
        n_tasks=len(task_ids),
        n_samples_total=n_samples_total,
        n_valid=n_valid,
        n_env_error=n_env_error,
        n_indent_repaired=n_indent_repaired,
        n_tasks_reduced_k=n_tasks_reduced_k,
        repair_split=repair_split,
        pass1=pass1,
        pass_k_visible=pass_k_visible,
        pass_k_extended=pass_k_extended,
        gap_rate=gap_rate,
        per_task=per_task,
        seed=seed,
    )
    (out_dir / "results.md").write_text(results_md)

    return {
        "task_ids": task_ids,
        "per_task": per_task,
        "n_samples_total": n_samples_total,
        "n_valid": n_valid,
        "n_env_error": n_env_error,
        "n_indent_repaired": n_indent_repaired,
        "n_tasks_reduced_k": n_tasks_reduced_k,
        "indent_repair_split": repair_split,
        "pass1": pass1,
        "pass_k_visible": pass_k_visible,
        "pass_k_extended": pass_k_extended,
        "gap_rate": gap_rate,
        "gap_numer": gap_numer,
        "gap_denom": gap_denom,
        "results_md": results_md,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, required=True, help="path to samples.jsonl written by run_phase_c_sample.py")
    parser.add_argument("--dataset", choices=["humaneval", "mbpp"], default=None, help="default: inferred from samples.jsonl's 'dataset' field")
    parser.add_argument("--k", type=int, default=10, help="nominal samples-per-task for pass@k (see per-task k_effective if fewer valid samples exist)")
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--out", type=Path, required=True, help="output directory, e.g. runs/<run_id>/")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--memory-mb", type=int, default=512)
    args = parser.parse_args()

    samples = _read_jsonl(args.samples)
    if not samples:
        raise SystemExit(f"no samples found in {args.samples}")

    dataset = args.dataset or samples[0]["dataset"]
    inconsistent = {s["dataset"] for s in samples} - {dataset}
    if inconsistent:
        raise SystemExit(
            f"samples.jsonl mixes datasets ({dataset!r} and {sorted(inconsistent)}) — "
            "score one dataset per run"
        )

    all_tasks = load_tasks(dataset)  # type: ignore[arg-type]

    result = run_scoring(
        samples,
        tasks=all_tasks,
        out_dir=args.out,
        k=args.k,
        seed=args.seed,
        workers=args.workers,
        memory_mb=args.memory_mb,
    )
    per_task = result["per_task"]
    n_samples_total = result["n_samples_total"]
    n_valid = result["n_valid"]
    n_env_error = result["n_env_error"]

    run_id = args.out.name or args.out.resolve().name
    manifest = RunManifest(
        run_id=run_id,
        created_at=datetime.now(timezone.utc),
        git_sha=_git_sha(),
        package_versions=capture_package_versions(),
        split_file=str(args.samples),
        split_sha256=sha256_file(args.samples),
        config={
            "dataset": dataset,
            "k": args.k,
            "seed": args.seed,
            "workers": args.workers,
            "memory_mb": args.memory_mb,
            "samples_path": str(args.samples),
        },
        metrics={
            "n_tasks": len(result["task_ids"]),
            "n_samples_total": n_samples_total,
            "n_valid": n_valid,
            "n_env_error": n_env_error,
            "n_indent_repaired": result["n_indent_repaired"],
            "n_tasks_reduced_k": result["n_tasks_reduced_k"],
            "indent_repair_split": result["indent_repair_split"],
            "pass1": result["pass1"],
            "pass_k_visible": result["pass_k_visible"],
            "pass_k_extended": result["pass_k_extended"],
            "gap_rate": result["gap_rate"],
            "gap_numer": result["gap_numer"],
            "gap_denom": result["gap_denom"],
        },
        predictions={t["task_id"]: t for t in per_task},
    )
    write_manifest(args.out / "manifest.json", manifest)

    print()
    print(result["results_md"])
    print(f"wrote {args.out / 'scores.jsonl'}")
    print(f"wrote {args.out / 'results.md'}")
    print(f"wrote {args.out / 'manifest.json'}")
    if n_env_error:
        print(f"ENV ERRORS: {n_env_error} sample(s) hit an environment defect — see above and scores.jsonl")


if __name__ == "__main__":
    main()
