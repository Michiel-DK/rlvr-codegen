# E-corpus — the Phase E own-repo transfer set (mined 2026-08-15)

**39 admissible eval tasks** mined from merged PRs across four of this account's real
repos. The docs/07 admissibility bar — a task exists only if the linked test was
**actually reproduced failing (red) at the PR's base commit and passing (green) at the
merge commit** — was enforced by execution, not read from PR descriptions. The ≥30
threshold is met; the declared fallback does not fire.

**Eval-only. These tasks are never trained on** (docs/07 Phase E). Per docs/06's framing
correction: PR-mining is *competence demonstrated, not novelty* — the method is the
standard SWE-bench-style FAIL_TO_PASS reproduction, applied to private working repos.

## Funnel (honest counts, including failures)

| Repo | PRs scanned | Attempted | Admissible | Rejected |
|---|---|---|---|---|
| agent-sandbox | 43 | 11 | 10 | 1 (no python test changed) |
| mast | 120 | 10 | 10 | 0 |
| restaurant-brain | 120 | 12 | 11 | 1 (test-predates-fix: passes at both commits) |
| roger3000-dev | 50 | 8 | 8 | 0 |
| **Total** | — | **41** | **39** | 2 |

Every repo stopped at its admissibility cap with tractable candidates left unattempted
(mast alone has 8 named in its report) — 39 is a floor, not the yield limit.

## Task anatomy (`tasks.jsonl`, one row per task)

`repo · pr · title · base_sha · merged_sha · test_cmd · red_evidence · green_evidence ·
notes`, plus two derived flags (see `scripts/build_ecorpus.py`, which regenerates this
file from `reports/*.json`):

- **red_class** — how base fails: `assertion` 23 · `import-error` 8 · `missing-module` 4
  · `crash` 4. Consumers wanting only clean behavioral regressions should filter to
  `assertion`.
- **task_shape** — `bugfix` 34 · `feature-add` 5. The feature-add tasks' red state is
  "the module doesn't exist yet", which is real but trivial; they are flagged, not hidden.

## Method caveats (read before consuming)

1. **Test overlay.** Most PRs ship fix and test together, so the merge commit's test
   file was overlaid onto the base commit's code to produce a meaningful red (the
   standard SWE-bench FAIL_TO_PASS method). Exceptions where the base's own files
   sufficed are noted per task. Restaurant-brain used a validated symlink-farm variant
   (control-run checked; one false-green bug in the harness itself was caught and fixed
   during mining).
2. **Environment requirements** live in each `reports/<repo>.json` under
   `environment_notes`: 6 mast tasks need the local `mast_vc` Postgres; agent-sandbox
   tasks are standalone `python3 <file>` scripts (no pytest); roger3000-dev tasks are
   node/shell suites, dependency-free.
3. One agent-sandbox task (PR 28) has its exact driver command reconstructible but not
   verbatim-preserved — marked `INCOMPLETE-AS-REPORTED` in `test_cmd`.
4. Base SHAs are the merge commit's first parent (`merge_sha^1`), validated as correct
   on these repos' linear histories.
5. All mining ran in detached scratch worktrees; the source repos' working trees were
   never touched and every worktree was removed (verified per lane).

## Files

- `tasks.jsonl` — the 39 admissible tasks (regenerate: `python scripts/build_ecorpus.py`)
- `reports/<repo>.json` — verbatim per-repo mining reports: admissible + rejected with
  reasons + environment notes. The reports are the source of truth; `tasks.jsonl` is a
  mechanical view of them.
