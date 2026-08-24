#!/usr/bin/env python3
"""Phase C sampler: docs/07 Phase C's slow, overnight half.

Samples k programs per task from the UNTRAINED base model (:class:`rlvr.generate.MlxGenerator`
by default) and writes them to an append-only ``samples.jsonl``. No scoring here — see
``scripts/run_phase_c_score.py`` for the fast, CPU-only half that runs the next morning.

⚠️ Per docs/07: this measures the visible→extended gap, NOT correctness.

RESUMABLE (spec requirement): an interrupted overnight run must not lose progress or duplicate
work. ``samples.jsonl`` is append-only and keyed by ``(task_id, sample_idx)`` — on restart, every
pair already present in the file is skipped, and only the missing pairs are generated. This is
implemented as a pure function, ``run_sampling``, separate from ``main()``'s argparse/CLI
plumbing, specifically so tests can inject a fake :class:`rlvr.generate.Generator` and drive the
resume logic directly (no model download, no CLI subprocess — see tests/test_generate.py).

macOS sleep reminder: this script does NOT call ``caffeinate`` itself (a script should not
control the operator's power-management policy at import time) — the overnight invocation should
be wrapped in ``caffeinate -i`` by the operator. A reminder is printed at startup.

Usage (real overnight run, heldout HumanEval, k=10):
    caffeinate -i python scripts/run_phase_c_sample.py --dataset humaneval --split-side heldout \\
        --k 10 --out runs/phase-c-humaneval-heldout-k10/

Usage (fast smoke, 3 tasks, k=2):
    python scripts/run_phase_c_sample.py --dataset humaneval --split-side heldout --k 2 \\
        --limit 3 --out runs/phase-c-smoke/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rlvr.data import Task, load_split, load_tasks
from rlvr.generate import (
    Generator,
    MlxGenerator,
    build_prompt,
    derive_seed,
    expected_body_indent,
    repair_first_line_indent,
    truncate_completion,
)
from rlvr.manifest import RunManifest, capture_package_versions, sha256_file, write_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPLIT_PATH = REPO_ROOT / "data" / "splits" / "split_v1.json"
DEFAULT_MODEL = "mlx-community/Qwen2.5-Coder-1.5B-bf16"
DEFAULT_EXCLUDE_TASKS = "HumanEval/83,Mbpp/255"

_PROGRESS_EVERY = 5


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _task_sort_key(task_id: str):
    """Numeric task-suffix sort — see the identical helper (and its rationale) in
    scripts/run_mutation_audit.py / scripts/run_calibration.py; duplicated rather than imported
    so this script stays independent of either."""
    prefix, _, tail = task_id.partition("/")
    try:
        return (prefix, 0, int(tail))
    except ValueError:
        return (prefix, 1, tail)


def _select_task_ids(split, dataset: str, split_side: str, limit: int | None) -> list[str]:
    if split_side == "heldout":
        ids = list(split.heldout[dataset])
    elif split_side == "train":
        ids = list(split.train[dataset])
    elif split_side == "all":
        ids = list(split.train[dataset]) + list(split.heldout[dataset])
    else:
        raise ValueError(f"unknown --split-side {split_side!r}")
    ordered = sorted(ids, key=_task_sort_key)
    return ordered if limit is None else ordered[:limit]


def _resolve_excluded(task_ids: list[str], exclude_arg: str) -> tuple[list[str], list[str]]:
    """Split ``--exclude-tasks`` into (excluded, ignored_as_absent).

    Unlike run_mutation_audit.py's ``--exclude-tasks`` (which raises if a named id isn't in the
    current selection), this default carries BOTH HumanEval/83 and Mbpp/255 regardless of which
    single ``--dataset`` is selected — so a plain ``--dataset humaneval`` run must not crash just
    because ``Mbpp/255`` is never in a humaneval-only selection. Ids present in the selection are
    excluded and reported; ids absent from the selection are reported separately as
    ignored-as-absent, not silently dropped and not fatal.
    """
    requested = [t.strip() for t in exclude_arg.split(",") if t.strip()]
    present = [t for t in requested if t in task_ids]
    absent = [t for t in requested if t not in task_ids]
    return present, absent


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


def _read_existing_keys(samples_path: Path) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    if not samples_path.exists():
        return keys
    _repair_torn_tail(samples_path)
    with open(samples_path) as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError:
                # post-repair, any remaining bad line is interior corruption — fail loudly
                raise ValueError(
                    f"corrupt interior line {lineno} of {samples_path}"
                ) from None
            keys.add((rec["task_id"], rec["sample_idx"]))
    return keys


def run_sampling(
    generator: Generator,
    *,
    tasks: dict[str, Task],
    task_ids: list[str],
    dataset: str,
    k: int,
    seed: int,
    max_tokens: int,
    temperature: float,
    out_dir: Path,
    progress_every: int = _PROGRESS_EVERY,
    log=print,
) -> dict:
    """Generate the missing (task_id, sample_idx) pairs and append them to
    ``out_dir/samples.jsonl``. Pure of argparse/CLI concerns so tests can call this directly with
    a fake generator. Returns a small summary dict (counts) used to build the manifest.

    Tasks with no valid :func:`rlvr.generate.build_prompt` (MBPP edge case — see
    rlvr/generate.py) are skipped entirely and reported, not silently dropped.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    samples_path = out_dir / "samples.jsonl"
    existing = _read_existing_keys(samples_path)

    work: list[tuple[str, int]] = []
    unsupported_tasks: list[str] = []
    prompt_specs: dict[str, tuple] = {}
    for task_id in task_ids:
        spec = build_prompt(tasks[task_id], dataset)
        if spec is None:
            unsupported_tasks.append(task_id)
            continue
        prompt_specs[task_id] = spec
        for idx in range(k):
            if (task_id, idx) not in existing:
                work.append((task_id, idx))

    if unsupported_tasks:
        log(f"  SKIPPED (no completion prompt could be built): {unsupported_tasks}")

    n_total_pairs = sum(k for t in task_ids if t not in unsupported_tasks)
    n_skipped_resume = n_total_pairs - len(work)
    log(
        f"run_phase_c_sample: dataset={dataset} n_tasks={len(task_ids) - len(unsupported_tasks)} "
        f"k={k} n_total_pairs={n_total_pairs} already_present={n_skipped_resume} "
        f"remaining={len(work)}"
    )

    n_done = 0
    n_written = 0
    t_start = time.monotonic()
    with open(samples_path, "a") as f:
        for task_id, idx in work:
            task = tasks[task_id]
            spec = prompt_specs[task_id]
            sample_seed = derive_seed(seed, task_id, idx)

            t0 = time.monotonic()
            raw = generator.generate(
                spec.prompt, max_tokens=max_tokens, temperature=temperature, seed=sample_seed
            )
            duration_s = time.monotonic() - t0

            # Repair a documented tokenizer-boundary artifact (found running the real-model
            # smoke test — see rlvr/generate.py's module docstring) BEFORE truncating: a
            # completion whose first line is short by a few spaces of indentation must be fixed
            # ahead of truncate_completion's column-0 detection, not after.
            if spec.allow_indent_repair:
                target_indent = expected_body_indent(task, spec)
                repaired = repair_first_line_indent(raw, target_indent)
            else:
                # MBPP scaffold ends at column 0 — the artifact cannot occur; a short
                # indent there is a real model error (review finding, PR #15).
                repaired = raw
            indent_repaired = repaired != raw
            truncated = truncate_completion(repaired)

            record = {
                "task_id": task_id,
                "sample_idx": idx,
                "dataset": dataset,
                "prompt_sha256": hashlib.sha256(spec.prompt.encode()).hexdigest(),
                "code_prefix": spec.code_prefix,
                "raw_completion": raw,
                "truncated_completion": truncated,
                "indent_repaired": indent_repaired,
                "seed": sample_seed,
                "model_id": getattr(generator, "model_id", None),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "duration_s": duration_s,
            }
            f.write(json.dumps(record, sort_keys=True) + "\n")
            f.flush()  # survive interruption: every completed sample is durable immediately
            n_written += 1
            n_done += 1

            if n_done % progress_every == 0 or n_done == len(work):
                elapsed = time.monotonic() - t_start
                rate = n_done / elapsed if elapsed > 0 else 0.0
                remaining = len(work) - n_done
                eta_s = remaining / rate if rate > 0 else float("nan")
                log(
                    f"  sampled {n_done}/{len(work)}  elapsed={elapsed:.0f}s  "
                    f"rate={rate:.2f}/s  ETA={eta_s:.0f}s"
                )

    return {
        "n_tasks_selected": len(task_ids),
        "n_tasks_unsupported": len(unsupported_tasks),
        "unsupported_tasks": unsupported_tasks,
        "n_total_pairs": n_total_pairs,
        "n_already_present_at_start": n_skipped_resume,
        "n_written_this_run": n_written,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", choices=["humaneval", "mbpp"], required=True)
    parser.add_argument("--split-side", choices=["heldout", "train", "all"], default="heldout")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--max-tokens", type=int, default=384)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--out", type=Path, required=True, help="output directory, e.g. runs/<run_id>/")
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT_PATH)
    parser.add_argument("--limit", type=int, default=None, help="cap the number of tasks (default: all in split-side)")
    parser.add_argument(
        "--exclude-tasks",
        default=DEFAULT_EXCLUDE_TASKS,
        help="comma-separated task_ids excluded as env-limited (default matches "
        "run_mutation_audit.py's calibration finding). Only excluded when present in the "
        "current --dataset's selection; ids for the other dataset are reported as "
        "ignored-as-absent, not an error.",
    )
    args = parser.parse_args()

    print(
        "REMINDER: an overnight invocation of this script should be wrapped in "
        "`caffeinate -i` by the operator (this script does not call caffeinate itself) — "
        "e.g. `caffeinate -i python scripts/run_phase_c_sample.py ...`"
    )

    split = load_split(args.split)
    all_tasks = load_tasks(args.dataset)
    task_ids = _select_task_ids(split, args.dataset, args.split_side, args.limit)

    excluded, ignored_absent = _resolve_excluded(task_ids, args.exclude_tasks)
    if excluded:
        task_ids = [t for t in task_ids if t not in excluded]
        print(f"  EXCLUDED (env-limited, declared, present in selection): {excluded}")
    if ignored_absent:
        print(f"  --exclude-tasks named ids not in this selection (ignored, not an error): {ignored_absent}")

    generator = MlxGenerator(args.model)

    summary = run_sampling(
        generator,
        tasks=all_tasks,
        task_ids=task_ids,
        dataset=args.dataset,
        k=args.k,
        seed=args.seed,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        out_dir=args.out,
    )

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
            "split_side": args.split_side,
            "k": args.k,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "model": args.model,
            "seed": args.seed,
            "limit": args.limit,
            "excluded_tasks_env_limited": excluded,
            "exclude_tasks_ignored_absent": ignored_absent,
        },
        metrics=summary,
    )
    write_manifest(args.out / "manifest.json", manifest)

    print(f"wrote {args.out / 'samples.jsonl'}")
    print(f"wrote {args.out / 'manifest.json'}")
    print(f"summary: {summary}")


if __name__ == "__main__":
    main()
