#!/usr/bin/env python3
"""Regenerate data/splits/split_v1.json — the frozen, seeded train/heldout split.

Deterministic by construction: for each dataset, task ids are sorted (so the split does not
depend on dict iteration order), shuffled with ``random.Random(seed)``, then cut 70% train /
30% heldout. The committed data/splits/split_v1.json is FROZEN — this script is how it was
produced and how anyone can verify it reproduces byte-for-byte (as parsed JSON) with seed
20260814. Run with a different --seed to see it produce a different (and thus non-matching)
split — that divergence is the red demonstration that the reproduction test actually pins the
seed; see tests/test_data.py.

Usage:
    python scripts/make_split.py                     # regenerate the committed split
    python scripts/make_split.py --seed 20260815 --out /tmp/other.json   # red demo
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from rlvr.data import DATASET_VERSIONS, load_tasks

SEED = 20260814
TRAIN_FRACTION = 0.7
SCHEMA_VERSION = "split-v1"
DATASETS = ("humaneval", "mbpp")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "data" / "splits" / "split_v1.json"


def build_dataset_split(dataset: str, seed: int) -> dict[str, list[str]]:
    """Shuffle this dataset's sorted task ids with the given seed and cut 70/30."""
    task_ids = sorted(load_tasks(dataset).keys())
    shuffled = task_ids[:]
    random.Random(seed).shuffle(shuffled)
    n_train = round(len(shuffled) * TRAIN_FRACTION)
    train = sorted(shuffled[:n_train])
    heldout = sorted(shuffled[n_train:])
    return {"train": train, "heldout": heldout}


def build_document(seed: int = SEED) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "datasets": {name: build_dataset_split(name, seed) for name in DATASETS},
        "dataset_versions": dict(DATASET_VERSIONS),
    }


def serialize_document(document: dict) -> str:
    """The one serialization path — RunManifest.split_sha256 hashes these exact bytes, so
    the committed file, main(), and the byte-identity test must all go through here."""
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED, help="shuffle seed (default: %(default)s)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output path")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialize_document(build_document(args.seed)))
    print(f"wrote {args.out} (seed={args.seed})")


if __name__ == "__main__":
    main()
