"""Run manifests: a machine-checkable record of what produced a metrics table.

docs/07 requires every number to be reproducible from a committed script + frozen split +
sandbox + run manifest. A ``RunManifest`` is the last of those four: it pins the split file
(by content hash, not just path), the package versions in play, the git commit, and the free-form
config/metrics/predictions that a run produced — including committed predictions, per docs/07's
requirement that they live in the manifest rather than only in a log file.

``created_at`` is caller-supplied, not auto-captured at write time, so that manifests stay
byte-reproducible from the same inputs (determinism over convenience).
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any

_TRACKED_PACKAGES = ("evalplus", "numpy")


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    created_at: datetime
    git_sha: str
    package_versions: dict[str, str]
    split_file: str
    split_sha256: str
    config: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    predictions: dict[str, Any] = field(default_factory=dict)


def capture_package_versions() -> dict[str, str]:
    """Python version plus the installed version of each tracked package (evalplus, numpy)."""
    versions: dict[str, str] = {"python": sys.version.split()[0]}
    for pkg in _TRACKED_PACKAGES:
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            versions[pkg] = "unknown"
    return versions


def sha256_file(path: str | Path) -> str:
    """SHA-256 hex digest of a file's contents, streamed in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: str | Path, manifest: RunManifest) -> None:
    data = asdict(manifest)
    data["created_at"] = manifest.created_at.isoformat()
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def read_manifest(path: str | Path) -> RunManifest:
    data: dict[str, Any] = json.loads(Path(path).read_text())
    data = dict(data)
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    return RunManifest(**data)
