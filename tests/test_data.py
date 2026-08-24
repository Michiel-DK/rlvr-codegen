"""Tests for rlvr.data: dataset access + frozen split loading/validation.

Dataset-dependent tests hit the evalplus local cache (HumanEvalPlus v0.1.10, MbppPlus v0.2.0,
already fetched on this machine) — no network required.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import pytest

from rlvr.data import Task, load_split, load_tasks

REPO_ROOT = Path(__file__).resolve().parent.parent
SPLIT_PATH = REPO_ROOT / "data" / "splits" / "split_v1.json"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from make_split import SEED, build_document, serialize_document  # noqa: E402


def test_load_tasks_humaneval_counts_and_mean():
    tasks = load_tasks("humaneval")
    assert len(tasks) == 164
    mean_n_base = statistics.mean(t.n_base for t in tasks.values())
    assert abs(mean_n_base - 9.6) < 0.5


def test_load_tasks_mbpp_counts_and_mean():
    tasks = load_tasks("mbpp")
    assert len(tasks) == 378
    mean_n_base = statistics.mean(t.n_base for t in tasks.values())
    assert abs(mean_n_base - 3.1) < 0.5


def test_task_fields_populated():
    tasks = load_tasks("humaneval")
    task = tasks["HumanEval/0"]
    assert isinstance(task, Task)
    assert task.task_id == "HumanEval/0"
    assert task.prompt
    assert task.entry_point == "has_close_elements"
    assert task.reference_solution
    assert task.n_base == len(task.base_inputs) > 0
    assert task.n_plus == len(task.plus_inputs) > 0
    assert isinstance(task.atol, (int, float))


def test_mbpp_zero_plus_task_is_surfaced_not_hidden():
    tasks = load_tasks("mbpp")
    zero_plus_ids = {t.task_id for t in tasks.values() if t.n_plus == 0}
    assert "Mbpp/793" in zero_plus_ids
    # n_plus == 0 must be visible (not filtered out) and n_base must still be populated.
    task = tasks["Mbpp/793"]
    assert task.n_plus == 0
    assert task.n_base > 0


def test_load_tasks_rejects_unknown_dataset():
    with pytest.raises(ValueError):
        load_tasks("not-a-real-dataset")  # type: ignore[arg-type]


def test_load_split_matches_committed_file():
    split = load_split(SPLIT_PATH)
    committed = json.loads(SPLIT_PATH.read_text())
    assert split.schema_version == committed["schema_version"]
    assert split.seed == committed["seed"]
    for name in ("humaneval", "mbpp"):
        assert list(split.train[name]) == committed["datasets"][name]["train"]
        assert list(split.heldout[name]) == committed["datasets"][name]["heldout"]


def test_load_split_train_heldout_disjoint_and_exhaustive():
    split = load_split(SPLIT_PATH)
    for name, expected_total in (("humaneval", 164), ("mbpp", 378)):
        train, heldout = set(split.train[name]), set(split.heldout[name])
        assert train.isdisjoint(heldout)
        assert len(train) + len(heldout) == expected_total
        assert train | heldout == set(load_tasks(name).keys())


def test_load_split_rejects_unknown_task_id(tmp_path):
    bad = {
        "schema_version": "split-v1",
        "seed": 20260814,
        "datasets": {"humaneval": {"train": ["HumanEval/not-real"], "heldout": []}},
        "dataset_versions": {"humaneval": "HumanEvalPlus v0.1.10"},
    }
    path = tmp_path / "bad_split.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_split(path)


def test_load_split_rejects_train_heldout_overlap(tmp_path):
    bad = {
        "schema_version": "split-v1",
        "seed": 20260814,
        "datasets": {"humaneval": {"train": ["HumanEval/0"], "heldout": ["HumanEval/0"]}},
        "dataset_versions": {"humaneval": "HumanEvalPlus v0.1.10"},
    }
    path = tmp_path / "bad_split.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_split(path)


def test_load_split_rejects_dataset_version_mismatch(tmp_path):
    """Review finding (PR #10): the docstring promised version validation nothing performed —
    a later evalplus release changing test data under the same ids must fail loudly."""
    doc = json.loads(SPLIT_PATH.read_text())
    doc["dataset_versions"]["humaneval"] = "HumanEvalPlus v0.0.1-not-installed"
    path = tmp_path / "stale_split.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="built against"):
        load_split(path)


def test_load_split_rejects_uncovered_dataset_tasks(tmp_path):
    """Review finding (PR #10): only subset-direction was checked — a task present in the
    dataset but in neither train nor heldout silently shrank the effective dataset."""
    doc = json.loads(SPLIT_PATH.read_text())
    doc["datasets"]["humaneval"]["heldout"] = doc["datasets"]["humaneval"]["heldout"][:-1]
    path = tmp_path / "shrunk_split.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="absent from both"):
        load_split(path)


def test_regenerate_split_reproduces_committed_file_exactly():
    """Pins the split: regenerating with the committed SEED must equal the committed JSON
    byte-for-byte as a parsed structure. See the PR body for the red demonstration that this
    test actually fails when the seed changes (build-flow A2)."""
    regenerated = build_document(SEED)
    committed = json.loads(SPLIT_PATH.read_text())
    assert regenerated == committed


def test_seed_is_pinned_to_the_frozen_literal():
    """Review finding (PR #10): asserting via the imported SEED symbol is circular — if
    someone changes SEED in make_split.py and regenerates the JSON, everything stays green.
    Only a literal pins the frozen value."""
    assert SEED == 20260814
    committed = json.loads(SPLIT_PATH.read_text())
    assert committed["seed"] == 20260814


def test_committed_file_is_byte_identical_to_serialization_path():
    """Review finding (PR #10): structural equality is whitespace-insensitive, but
    RunManifest.split_sha256 hashes real bytes — so the committed file must match the
    script's exact serialization, exercised through serialize_document itself (A4: through
    the real entry point, not a re-derived copy of it)."""
    expected = serialize_document(build_document(SEED))
    assert SPLIT_PATH.read_text() == expected


def test_different_seed_produces_a_different_split():
    """Compare only the dataset membership, not the whole document -- ``build_document`` also
    stamps the seed value into the doc, which would make a whole-document != trivially true
    even if the shuffle itself ignored the seed. This is the assignment the seed controls."""
    committed = json.loads(SPLIT_PATH.read_text())
    other = build_document(20260815)
    assert other["datasets"] != committed["datasets"]
