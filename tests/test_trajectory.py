"""Tests for rlvr.trajectory: append-only JSONL rollout log."""

from __future__ import annotations

import pytest

from rlvr.trajectory import (
    SCHEMA_VERSION,
    TrajectoryError,
    TrajectoryRecord,
    append_records,
    read_records,
)


def _record(i: int) -> TrajectoryRecord:
    return TrajectoryRecord(
        task_id=f"HumanEval/{i}",
        sample_idx=i,
        code=f"def f_{i}(): return {i}",
        verdict_base=bool(i % 2),
        verdict_plus=None if i == 0 else bool(i % 3),
        duration_s=0.1 * i,
        extra={"note": f"sample-{i}"},
    )


def test_write_and_read_back_equal(tmp_path):
    path = tmp_path / "traj.jsonl"
    records = [_record(i) for i in range(5)]
    append_records(path, records)

    assert read_records(path) == records


def test_records_carry_fixed_schema_version(tmp_path):
    path = tmp_path / "traj.jsonl"
    append_records(path, [_record(0)])
    read = read_records(path)
    assert read[0].schema_version == SCHEMA_VERSION == "rlvr-local-v0"


def test_appending_preserves_prior_records(tmp_path):
    path = tmp_path / "traj.jsonl"
    first_batch = [_record(i) for i in range(3)]
    append_records(path, first_batch)

    second_batch = [_record(i) for i in range(3, 6)]
    append_records(path, second_batch)

    assert read_records(path) == first_batch + second_batch


def test_corrupted_line_raises_clear_error_not_silent_skip(tmp_path):
    path = tmp_path / "traj.jsonl"
    append_records(path, [_record(0), _record(1)])
    with open(path, "a") as f:
        f.write("{this is not valid json\n")

    with pytest.raises(TrajectoryError, match="invalid JSON"):
        read_records(path)


def test_malformed_record_raises_clear_error(tmp_path):
    path = tmp_path / "traj.jsonl"
    with open(path, "w") as f:
        f.write('{"task_id": "HumanEval/0"}\n')  # missing required fields

    with pytest.raises(TrajectoryError, match="malformed record"):
        read_records(path)


def test_blank_lines_are_skipped_not_treated_as_corruption(tmp_path):
    path = tmp_path / "traj.jsonl"
    append_records(path, [_record(0)])
    with open(path, "a") as f:
        f.write("\n\n")
    append_records(path, [_record(1)])

    assert read_records(path) == [_record(0), _record(1)]
