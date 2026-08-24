"""Assemble the Phase E transfer-set task list from the per-repo miner reports.

Reads data/e-corpus/reports/*.json (the verbatim mining reports, each task's red/green
verified by actually running the test at the PR's base and merge commits — see
data/e-corpus/README.md for the method and its caveats) and writes data/e-corpus/tasks.jsonl,
one row per admissible task, with two mechanically derived flags:

- red_class: how the base state fails — "assertion" (clean behavioral failure),
  "import-error" (collection-time ImportError/AttributeError on a changed symbol),
  "missing-module" (the fix ships a brand-new module/file), "crash" (harness crash,
  e.g. a TDZ ReferenceError). Derived from the red_evidence text.
- task_shape: "feature-add" iff the miner's notes flagged the PR as feature-shaped
  (net-new module/agent rather than a behavioral fix), else "bugfix".

Eval-only: these tasks are NEVER trained on (docs/07 Phase E).
"""

from __future__ import annotations

import json
from pathlib import Path

REPORTS = Path(__file__).resolve().parent.parent / "data" / "e-corpus" / "reports"
OUT = REPORTS.parent / "tasks.jsonl"


def red_class(red_evidence: str) -> str:
    text = red_evidence.lower()
    if "modulenotfounderror" in text or "filenotfounderror" in text:
        return "missing-module"
    if "importerror" in text or "attributeerror" in text:
        return "import-error"
    if "referenceerror" in text or "tdz" in text:
        return "crash"
    return "assertion"


def task_shape(notes: str) -> str:
    # Miner reports phrase the flag differently ("feature-shaped", "net-new",
    # "whole new script", "new module", "new-agent build task") — match all of them;
    # missing one silently under-flags (caught on restaurant-brain PR 423).
    text = notes.lower()
    markers = ("feature-shaped", "net-new", "whole new", "new module", "new-agent")
    return "feature-add" if any(m in text for m in markers) else "bugfix"


def main() -> None:
    rows = []
    funnel = []
    for report_path in sorted(REPORTS.glob("*.json")):
        report = json.loads(report_path.read_text())
        for t in report["admissible"]:
            rows.append(
                {
                    "repo": report["repo"],
                    "pr": t["pr"],
                    "title": t["title"],
                    "base_sha": t["base_sha"],
                    "merged_sha": t["merged_sha"],
                    "test_cmd": t["test_cmd"],
                    "red_class": red_class(t["red_evidence"]),
                    "task_shape": task_shape(t.get("notes", "")),
                    "red_evidence": t["red_evidence"],
                    "green_evidence": t["green_evidence"],
                    "notes": t.get("notes", ""),
                    "verified_at": "2026-08-15",
                }
            )
        funnel.append(
            {
                "repo": report["repo"],
                "prs_scanned": report["prs_scanned"],
                "attempted": report["candidates_attempted"],
                "admissible": len(report["admissible"]),
                "rejected": len(report["rejected"]),
            }
        )

    rows.sort(key=lambda r: (r["repo"], r["pr"]))
    with open(OUT, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")

    print(f"wrote {OUT} ({len(rows)} tasks)")
    for row in funnel:
        print(
            f"  {row['repo']}: scanned={row['prs_scanned']} attempted={row['attempted']} "
            f"admissible={row['admissible']} rejected={row['rejected']}"
        )
    total_admissible = sum(r["admissible"] for r in funnel)
    total_attempted = sum(r["attempted"] for r in funnel)
    print(f"TOTAL: {total_admissible} admissible / {total_attempted} attempted "
          f"(docs/07 bar: >=30 admissible -> {'MET' if total_admissible >= 30 else 'NOT MET'})")


if __name__ == "__main__":
    main()
