"""Tests for rlvr.manifest: RunManifest JSON round-trip + split hash verification."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from rlvr.manifest import (
    RunManifest,
    capture_package_versions,
    read_manifest,
    sha256_file,
    write_manifest,
)


def _sample_manifest(split_file: Path) -> RunManifest:
    return RunManifest(
        run_id="test-run-0001",
        created_at=datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc),
        git_sha="deadbeef" * 5,
        package_versions=capture_package_versions(),
        split_file=str(split_file),
        split_sha256=sha256_file(split_file),
        config={"dataset": "humaneval", "k": 10},
        metrics={"pass_at_1": 0.42},
        predictions={"HumanEval/0": ["def f(): ..."]},
    )


def test_manifest_round_trip(tmp_path):
    split_file = tmp_path / "split.json"
    split_file.write_text('{"hello": "world"}')

    manifest = _sample_manifest(split_file)
    out_path = tmp_path / "manifest.json"
    write_manifest(out_path, manifest)
    loaded = read_manifest(out_path)

    assert loaded == manifest


def test_manifest_split_sha256_matches_independent_hash(tmp_path):
    split_file = tmp_path / "split.json"
    split_file.write_text('{"some": "content", "n": 42}')

    manifest = _sample_manifest(split_file)
    independent = hashlib.sha256(split_file.read_bytes()).hexdigest()
    assert manifest.split_sha256 == independent


def test_capture_package_versions_includes_expected_keys():
    versions = capture_package_versions()
    assert "python" in versions
    assert "evalplus" in versions
    assert "numpy" in versions
    assert versions["evalplus"] != "unknown"
    assert versions["numpy"] != "unknown"


def test_write_manifest_produces_valid_json_with_expected_fields(tmp_path):
    split_file = tmp_path / "split.json"
    split_file.write_text("{}")
    manifest = _sample_manifest(split_file)
    out_path = tmp_path / "manifest.json"
    write_manifest(out_path, manifest)

    data = json.loads(out_path.read_text())
    assert data["run_id"] == "test-run-0001"
    assert data["split_sha256"] == manifest.split_sha256
    assert data["predictions"] == {"HumanEval/0": ["def f(): ..."]}
    assert data["metrics"] == {"pass_at_1": 0.42}
