# Phase B deliverable — verifier-adequacy audit (2026-08-14)

The docs/07 kill-criterion artifact: mutation scores of the *visible* (original
benchmark) test suite vs the *extended* (EvalPlus) suite, over seeded mutants of
the reference solutions. No model, no GPU, no training.

## Headline

| Dataset | Visible suite | Extended suite | Gap (pooled) | Gap (task-mean, 95% CI) | Mutants | Tasks |
|---|---|---|---|---|---|---|
| HumanEval | 89.2% (88.0–90.4) | 92.9% (91.8–93.8) | **+3.6%** | +3.2% (+2.2 – +4.3) | 2455 | 163 |
| MBPP | 87.1% (85.9–88.2) | 93.5% (92.6–94.3) | **+6.4%** | +5.7% (+4.3 – +7.2) | 3477 | 377 |

Reading: on HumanEval, 10.8% of injected bugs survive the visible test-pass
reward; a third of those (3.6pp) are caught by the extended suite — that slice
is the *measured* reward-certification gap a test-pass RL reward cannot see.
MBPP's thinner base suite (~3 asserts/problem) shows the larger gap, as the
docs/07 instrument analysis predicted. The remainder (`survived_both`) is not
distinguishable by either suite — **not** claimed as equivalence, and the
extended suite is **not** ground truth (stronger proxy only).

## Reproduce

```
python scripts/run_mutation_audit.py --dataset humaneval --workers 6 \
    --exclude-tasks HumanEval/83 --out runs/mutation-humaneval
python scripts/run_mutation_audit.py --dataset mbpp --workers 6 \
    --exclude-tasks Mbpp/255 --out runs/mutation-mbpp
```

Seed 20260814 throughout (mutant selection, split, bootstrap). Determinism
verified: same seed, different `--workers` → byte-identical `mutants.jsonl`.

## Declared exclusions and scope

- `HumanEval/83` and `Mbpp/255` are **env-limited** (their reference solutions
  need CPU/memory budgets candidates don't get — see `calibration-*.json`);
  mutant verdicts there would measure the budget, not the suite.
- Environment health: reference solutions pass 164/164 and 378/378 (base),
  163/164 and 377/377 (plus) — `calibration-*.json` in this directory.
- Outputs whose serialization exceeds 64 KiB compare by sha256 (exact, no atol).
- Mutation operators: relational / arithmetic / boolean / constant-perturbation /
  if-negation / slice-off-by-one, stdlib-`ast`, deterministic seeded selection,
  ≤20 mutants per task.

Files: `results-*.md` (rendered tables incl. per-task), `manifest-*.json` (run
manifests: config, split sha256, package versions, per-task predictions),
`mutants-*.jsonl` (one row per mutant with per-suite verdicts),
`calibration-*.json` (environment-health run manifests).
