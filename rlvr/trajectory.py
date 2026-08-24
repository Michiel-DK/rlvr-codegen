"""Append-only JSONL writer/reader for rollout trajectory records.

This is a deliberately LOCAL, versioned format (``schema_version="rlvr-local-v0"``) — NOT the
harness's shared trajectory schema. Per repo CLAUDE.md, that shared schema is gated and not yet
spec'd (see the harness open items before treating this as anything but a local candidate
emitter). Versioning it now means rollout logs produced here can be migrated once the shared
schema lands, without having guessed at its shape.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "rlvr-local-v0"


@dataclass(frozen=True)
class TrajectoryRecord:
    task_id: str
    sample_idx: int
    code: str
    verdict_base: bool | None
    verdict_plus: bool | None
    duration_s: float
    extra: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION


class TrajectoryError(ValueError):
    """Raised when a trajectory JSONL file contains an unparseable or malformed line."""


def append_records(path: str | Path, records: list[TrajectoryRecord]) -> None:
    """Append records to ``path`` as JSONL, one record per line. Creates the file if absent."""
    with open(path, "a") as f:
        for record in records:
            f.write(json.dumps(dataclasses.asdict(record), sort_keys=True) + "\n")


def read_records(path: str | Path) -> list[TrajectoryRecord]:
    """Read all records from a trajectory JSONL file, in file order.

    Raises TrajectoryError (naming the file and line number) on a line that isn't valid JSON or
    doesn't match TrajectoryRecord's fields — corruption is surfaced, never silently skipped.
    """
    records: list[TrajectoryRecord] = []
    with open(path) as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                raise TrajectoryError(f"{path}:{lineno}: invalid JSON: {e}") from e
            try:
                records.append(TrajectoryRecord(**data))
            except TypeError as e:
                raise TrajectoryError(f"{path}:{lineno}: malformed record: {e}") from e
    return records
