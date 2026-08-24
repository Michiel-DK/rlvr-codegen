"""Task access for the EvalPlus datasets (HumanEval+, MBPP+).

Loads tasks via ``evalplus.data.get_human_eval_plus`` / ``get_mbpp_plus`` and exposes them as
frozen :class:`Task` records. Expected outputs are deliberately NOT stored on the task: EvalPlus
computes them by *running the reference solution* at evaluation time (differential testing, per
EvalPlus's own design) — storing them here would duplicate that computation and risk a silently
stale oracle if the reference solution or inputs ever change upstream.

Record keys observed on 2026-08-14 (evalplus 0.3.1, HumanEvalPlus v0.1.10, MbppPlus v0.2.0):
  HumanEval+: task_id, prompt, entry_point, canonical_solution, test, contract, base_input,
              plus_input, atol
  MBPP+:      task_id, prompt, entry_point, canonical_solution, assertion, contract, base_input,
              plus_input, atol
Both datasets carry ``atol`` on every record (used for float-tolerant comparison). MBPP+ has an
extra ``assertion``/no ``test`` field difference from HumanEval+; both are read defensively via
``.get`` where a key isn't part of the Task contract, and by direct index where the key was
observed uniform across every record in both datasets.

At least one MBPP+ task (Mbpp/793, measured 2026-08-14) has zero extended ("plus") inputs. That
is surfaced via ``n_plus`` rather than hidden — Phase B needs to be able to flag such tasks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from evalplus.data import get_human_eval_plus, get_mbpp_plus
from evalplus.data.humaneval import HUMANEVAL_PLUS_VERSION
from evalplus.data.mbpp import MBPP_PLUS_VERSION

DatasetName = Literal["humaneval", "mbpp"]

# Dataset version strings as reported by evalplus itself, not hardcoded independently of it —
# these are what data/splits/split_v1.json's "dataset_versions" field must match.
DATASET_VERSIONS: dict[str, str] = {
    "humaneval": f"HumanEvalPlus {HUMANEVAL_PLUS_VERSION}",
    "mbpp": f"MbppPlus {MBPP_PLUS_VERSION}",
}

_LOADERS = {
    "humaneval": get_human_eval_plus,
    "mbpp": get_mbpp_plus,
}


@dataclass(frozen=True)
class Task:
    """One EvalPlus problem, inputs only — no expected outputs (see module docstring)."""

    task_id: str
    prompt: str
    entry_point: str
    reference_solution: str
    base_inputs: list
    plus_inputs: list
    n_base: int
    n_plus: int
    atol: float


def load_tasks(dataset: DatasetName) -> dict[str, Task]:
    """Load every task for ``dataset`` ("humaneval" or "mbpp") into a dict keyed by task_id."""
    if dataset not in _LOADERS:
        raise ValueError(f"unknown dataset {dataset!r}; expected one of {sorted(_LOADERS)}")

    raw = _LOADERS[dataset]()
    tasks: dict[str, Task] = {}
    for task_id, record in raw.items():
        base_inputs = record["base_input"]
        plus_inputs = record["plus_input"]
        tasks[task_id] = Task(
            task_id=task_id,
            prompt=record["prompt"],
            entry_point=record["entry_point"],
            reference_solution=record["canonical_solution"],
            base_inputs=base_inputs,
            plus_inputs=plus_inputs,
            n_base=len(base_inputs),
            n_plus=len(plus_inputs),
            atol=record.get("atol", 0),
        )
    return tasks


@dataclass(frozen=True)
class Split:
    """A frozen train/heldout split, one entry per dataset. See scripts/make_split.py."""

    schema_version: str
    seed: int
    train: dict[str, tuple[str, ...]]
    heldout: dict[str, tuple[str, ...]]
    dataset_versions: dict[str, str]


def load_split(path: str | Path) -> Split:
    """Load a split JSON file, validating every task id actually exists in its dataset.

    Raises ValueError if a dataset's train/heldout ids overlap, reference a task id that
    isn't present in the currently-loaded EvalPlus dataset, fail to cover every task the
    dataset currently ships (new upstream tasks must not silently vanish from both sides),
    or if the split's recorded dataset_versions disagree with the installed evalplus.
    """
    data: dict[str, Any] = json.loads(Path(path).read_text())

    recorded_versions = dict(data["dataset_versions"])
    train: dict[str, tuple[str, ...]] = {}
    heldout: dict[str, tuple[str, ...]] = {}
    for name, split in data["datasets"].items():
        expected_version = DATASET_VERSIONS.get(name)
        if recorded_versions.get(name) != expected_version:
            raise ValueError(
                f"split {name!r}: built against {recorded_versions.get(name)!r} but the "
                f"installed evalplus provides {expected_version!r} — regenerate the split "
                "or pin the matching evalplus version"
            )

        train_ids = list(split["train"])
        heldout_ids = list(split["heldout"])

        overlap = set(train_ids) & set(heldout_ids)
        if overlap:
            raise ValueError(f"split {name!r}: train/heldout overlap: {sorted(overlap)}")

        valid_ids = set(load_tasks(name).keys())  # type: ignore[arg-type]
        split_ids = set(train_ids) | set(heldout_ids)
        missing = split_ids - valid_ids
        if missing:
            raise ValueError(
                f"split {name!r}: task ids not present in dataset: {sorted(missing)}"
            )
        uncovered = valid_ids - split_ids
        if uncovered:
            raise ValueError(
                f"split {name!r}: dataset tasks absent from both train and heldout: "
                f"{sorted(uncovered)}"
            )

        train[name] = tuple(train_ids)
        heldout[name] = tuple(heldout_ids)

    return Split(
        schema_version=data["schema_version"],
        seed=data["seed"],
        train=train,
        heldout=heldout,
        dataset_versions=dict(data["dataset_versions"]),
    )
