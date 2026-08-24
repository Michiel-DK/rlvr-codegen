# 08 — Results: how much does a test-pass reward actually certify?

> STATUS: canon. The Phase F writeup required by [`07`](07-rescope-verifier-adequacy.md),
> covering Phases A–C (shipped 2026-08-14/15, ~$0, no GPU). Framing constraints from
> [`06`](06-prior-art-and-positioning.md) §Phase-4 are binding here and are applied
> throughout. Raw artifacts: [`results/phase-b-2026-08-14/`](../results/phase-b-2026-08-14/)
> and [`results/phase-c-2026-08-15/`](../results/phase-c-2026-08-15/).

## The one-line story

Before training a code model against a test-pass reward, we measured how much that reward
actually certifies: mutation scores and the visible-vs-extended test gap on a packaged
environment, then how often an untrained base model already produces code that passes the
visible tests and fails the extended ones. Training now sits behind a number instead of a
hope.

## Headline — Phase B: the verifier, audited without a model

Seeded mutants (single AST edits: relational / arithmetic / boolean operators, constant
perturbation, negated conditions, slice off-by-one) were injected into the benchmark
reference solutions, then executed against the **visible** suite (the original benchmark's
tests — what a test-pass RL reward would use) and the **extended** suite (base ∪
[EvalPlus](https://github.com/evalplus/evalplus) plus-inputs).

| Dataset | Killed by visible | Killed by extended | Gap (pooled) | Gap (task-mean, 95% CI) | Mutants | Tasks |
|---|---|---|---|---|---|---|
| HumanEval | 89.2% (88.0–90.4) | 92.9% (91.8–93.8) | **+3.6%** | +3.2% (+2.2 – +4.3) | 2,455 | 163 |
| MBPP | 87.1% (85.9–88.2) | 93.5% (92.6–94.3) | **+6.4%** | +5.7% (+4.3 – +7.2) | 3,477 | 377 |

Reading the HumanEval row: 10.8% of injected bugs pass every visible test. A third of those
(3.6pp of all mutants) are caught by the extended suite — that slice is a *measured* defect
of the reward: buggy code the reward calls correct, demonstrably so. The remainder
(`survived_both`: 175 mutants) is **not** claimed as equivalence — those mutants are
merely indistinguishable by the strongest suite available, which is a statement about the
suites, not about the code (MBPP's counterpart: 226). The MBPP row is the same measurement on a thinner visible suite
(~3.1 asserts/problem vs HumanEval's 9.6) and shows the larger gap, in the direction the
instrument analysis in `07` predicted.

Both per-suite CIs are pooled-mutant Wilson intervals and are anti-conservative (mutants
cluster within tasks); the task-mean gap carries the honest task-resampled bootstrap CI.
Both estimators are reported because they legitimately differ.

## Headline — Phase C: the base model, probed before any RL

Completions (k=10 per task, temperature 0.8) sampled from **Qwen2.5-Coder-1.5B** (bf16,
MLX, local Apple-Silicon laptop — nothing rented) on the held-out splits, scored against
both suites:

| Metric | HumanEval (48 tasks, 480 samples) | MBPP (113 tasks, 1,130 samples) |
|---|---|---|
| pass@1 (visible) | 25.6% (17.5–34.2) | 14.4% (10.9–18.2) |
| pass@10 (visible) | 62.5% (47.9–75.0) | 56.6% (46.9–65.5) |
| pass@10 (extended) | 56.2% (41.7–70.8) | 46.9% (38.1–55.8) |
| **Gap rate**: visible-passers failing extended | **12.2%** (7.5–19.1, n=123) | **17.8%** (12.7–24.4, n=163) |

One in eight visible-passing HumanEval completions — and roughly one in six on MBPP —
fails the extended suite, *before any RL has optimized against that reward*. The MBPP gap
coming out higher than HumanEval's is the direction the instrument analysis predicted
(MBPP's visible suite is ~3× thinner), though the two intervals overlap, so read the
ordering as consistent-with-prediction rather than established by this sample size. Comparing this to Phase B needs
matched denominators: the pooled 3.6% gap is diluted by mutants that never survive the
visible suite at all. Restricted to the same population Phase C measures — cases that
already pass visible — the mutant leak rate is 33.7% (89/264, HumanEval) and 49.7%
(223/449, MBPP), both *higher* than the model's 12.2% / 17.8%. Under a matched denominator,
single-edit synthetic mutants that clear the visible suite are caught by the extended
suite more often than an untrained model's visible-passing completions are. Read this as a
caution, not a multiplier in either direction: the two instruments measure structurally
different failure populations, and mutant-based numbers do not transfer directly to model
behavior.

This number is the pre-registered baseline for the training phase. The question `07` poses
for Phase D is now operational: after RL against the visible reward, re-measure the gap rate
on the same frozen held-out split — a rate rising out the top of today's CI is evidence the
policy learned the reward rather than the task; a falling rate is evidence of
generalization.

## What the instrument is (and is not)

- **Visible suite** = the reward under audit. **Extended suite** = a *strictly stronger
  proxy — not ground truth*. Every gap number here is a lower bound on the reward's blind
  spot, never a correctness claim. (This sentence is load-bearing; `07` forbids the
  stronger claim.)
- Confirmed against the shipped datasets (evalplus 0.3.1), not secondary sources: HumanEval
  164 tasks, mean 9.6 base tests/problem (median 7; 24% of tasks have <5), extended ×79.1;
  MBPP 378 tasks, mean 3.1 (98% of tasks <5), extended ×34.9.
- EvalPlus generates its extra tests by ChatGPT-seeded, type-aware mutation of test
  *inputs*, labeled by differential execution of the ground-truth solution
  ([arXiv 2305.01210](https://arxiv.org/abs/2305.01210)). It never mutates solution code,
  so Phase B's solution-code mutation score is methodologically independent of how the
  extended suite was built. One consequence enforced throughout: the **full** plus suites
  are used, never the reduced "-mini" variants — those were selected partly by
  mutant-killing, which would correlate the ruler with the measurement.
- Held-out tests are the field's standard instrument and are *known to leak* (see `06`);
  they are used here as that standard instrument, not presented as a novel defense.

## The environment the numbers stand on

All measurements run through one packaged path (task → sandboxed execution → per-input
verdicts → reward), exercised by 172 committed tests:

- **Sandbox**: macOS `sandbox-exec` deny-default profile plus an in-process fallback layer;
  kernel-level network denial, process-group kill, RSS watchdog (POSIX rlimits for memory
  are inert on this platform — measured, not assumed), pinned `PYTHONHASHSEED`, and
  per-call observability flags so a degraded run is distinguishable from a clean one. Its
  module docstring carries a declared scope: what it blocks, what it cannot.
- **Determinism**: frozen train/held-out split (seed 20260814, byte-reproducible from a
  committed script, seed pinned by literal assertion), seeded mutant selection (same seed +
  different worker counts → byte-identical output), seeded bootstrap, run manifests
  recording git SHA / package versions / split hash, and JSONL trajectory logs
  (`rlvr-local-v0`).
- **Calibration before measurement**: reference solutions pass 164/164 and 378/378 on the
  visible suites, 163/164 and 377/377 on extended. The two exceptions — `HumanEval/83`
  (CPU-bound bigint arithmetic) and `Mbpp/255` (memory-bound) — need resource budgets
  candidates don't get. In calibration, `HumanEval/83` was scored and genuinely failed the
  extended suite for this reason (hence 163/164); `Mbpp/255`'s reference run itself hit
  the resource limit and was excluded from the extended count (hence 377/377 of those
  scorable). Both are **excluded and declared** in the Phase B mutation audit, where a
  mutant verdict would measure the budget, not the suite.
- **Adversarial hardening, because this thing scores adversaries**: protocol records are
  nonce-framed (candidate stdout can neither corrupt nor forge them — a forged
  all-pass protocol line gets no credit), a sandbox-launch failure cannot be faked by
  candidate stderr, and reference-execution failures raise loudly instead of silently
  mis-scoring every later candidate.
- Review discipline: every guard was demonstrated failing (red) against the defect it
  claims to catch before being trusted green; independent fresh-context reviews plus an
  adversarial verify pass ran on each component, and their real findings (a scoring path
  that zeroed *correct* code, a poisonable oracle cache, a forgeable error flag, an
  indent-repair that could have inflated Phase C) were fixed before any headline number was
  produced.

Honest instrument notes that survive into every results table: outputs whose serialization
exceeds 64 KiB compare by SHA-256 (exact; float tolerance doesn't apply there), and Phase
C's completions carry a one-space indent repair for a verified tokenizer boundary artifact —
gated to that exact signature, with pass rates reported separately for repaired vs
unrepaired samples so a rescue effect would be visible (repaired 123/477 passed; the 3
unrepaired samples all failed).

## Positioning (per `06`, so this document isn't refutable in one search)

Nothing here is claimed as novel methodology. Mutation testing is standard; EvalPlus is
prior art and is what makes the visible-vs-extended comparison cheap; auditing code-RL
environments without training has an existence proof
([arXiv 2606.16062](https://arxiv.org/pdf/2606.16062)); environment packaging is ecosystem
conformance, not differentiation. What this repo contributes is the *discipline*: the
verifier measured before anything trains against it, on a calibrated environment, with the
numbers reproducible from committed scripts, a frozen split, and one seed — and a
pre-registered baseline that makes the eventual training run falsifiable. Reward hacking
being the top practical bottleneck in environment construction
([Epoch AI, 2026-01](https://epoch.ai/gradient-updates/state-of-rl-envs), verified
2026-08-14) is the market context, not a claim of this repo.

## Costs, and what comes next

Phases A–C: **$0 rented** (agent tokens + a laptop). Remaining phases, from `07`:

- **D — train** (DPO, then GRPO; LoRA on a single 24 GB GPU, ~$30–80): the reward is this
  environment; the deliverable is the gap-rate delta against Phase C's 12.2% baseline.
- **E — own-repo transfer set** (~$0): eval-only tasks mined from merged PRs —
  *competence demonstrated, not novelty*.
- **G — mid-training arm** (gated on A–F **and on reading PRISM, currently unread**;
  +$30–65 on top of D): non-Coder base, continued pretraining on a code corpus, then the
  same RL recipe on both bases. It extends D; it cannot replace it — mid-training without
  the RL phase is a shaped base with nothing to measure the shaping against.

## Reproduce

```bash
pip install -e '.[dev]'                       # + '.[gen]' for Phase C sampling
python scripts/run_calibration.py     --dataset humaneval --suite both --out runs/calib
python scripts/run_mutation_audit.py  --dataset humaneval --workers 6 \
    --exclude-tasks HumanEval/83 --out runs/mutation          # Phase B (MBPP: Mbpp/255)
python scripts/run_phase_c_sample.py  --dataset humaneval --split-side heldout --k 10 \
    --out runs/phase-c                                        # Phase C (Apple Silicon)
python scripts/run_phase_c_score.py   --samples runs/phase-c/samples.jsonl --k 10 \
    --out runs/phase-c
```

Seed 20260814 everywhere. Every table in this document regenerates from these commands plus
the committed split; per-mutant and per-sample JSONL sit next to each results table under
`results/`.
