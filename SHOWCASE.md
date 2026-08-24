# Test the tests before you train on them.

> **Frozen write-up, 2026-08-24.** The repo keeps moving; this page doesn't. Every number
> below traces to a committed file (named inline); raw artifacts live under `results/`.
> The headline fact about this repo is what it did **before** spending on training —
> and that no training result is claimed yet.

## The one-paragraph version

The plan is RLVR: train a small code model where the reward is "the unit tests pass."
The known failure mode is that this reward is gameable — a model can learn to turn the
visible tests green without the code being right. So before any GPU was rented, the repo
**audited the reward itself**: seeded thousands of known-buggy mutants and measured how
many the visible test suites actually catch (Phase B), then probed how often an
*untrained* base model already produces visible-passing code that fails a held-out
extended suite (Phase C), and mined a 39-task transfer set from this account's own repos
so generalization can later be tested on code the benchmarks never saw (Phase E). Total
spend: **~$0, no GPU, run on a laptop**. Training (Phase D, $30–80) is deliberately
*behind* these numbers — it now sits behind a measurement instead of a hope
(`docs/07-rescope-verifier-adequacy.md` is the pre-registered plan; `docs/08-…` the
results).

## The scoreboard

From `docs/08-results-verifier-adequacy.md` (raw: `results/phase-b-2026-08-14/`,
`results/phase-c-2026-08-15/`):

| measurement | HumanEval | MBPP |
|---|---|---|
| mutants killed by **visible** suite (Phase B) | 89.2% | 87.1% |
| additional kill by **extended** suite (the gap) | **+3.6pp** | **+6.4pp** |
| base model, pass@10 visible (Phase C, Qwen2.5-Coder-1.5B) | 62.5% | 56.6% |
| **visible-passers that fail extended** | **12.2%** | **17.8%** |

Reading the last row: before any RL has optimized anything, one in eight HumanEval
completions the reward would call *correct* is demonstrably not — one in six on MBPP.
That is the baseline gap Phase D's training will either widen (reward hacking, measured)
or narrow (generalization, measured). Either outcome is a result.

## Four receipts

### 1. The reward's blind spot, measured without a model

Phase B injects single-AST-edit mutants (flipped relational/boolean operators, constant
perturbations, off-by-one slices) into the benchmarks' *reference solutions* — code known
correct, made wrong in one place — and runs both suites over them (2,455 mutants / 163
tasks on HumanEval; 3,477 / 377 on MBPP). 10.8% of HumanEval's injected bugs pass every
visible test. The +3.6pp slice the extended suite catches is a **measured defect of the
reward**: buggy code the reward calls correct, demonstrably so. And the mutants *neither*
suite kills (175 / 226) are explicitly **not** claimed as equivalent code — the doc calls
that a statement about the suites, not about the code.

### 2. A directional prediction, made before the data

MBPP's visible suites are ~3× thinner than HumanEval's (~3.1 vs 9.6 asserts per task).
The instrument analysis in `docs/07` predicted the gap should therefore be *larger* on
MBPP — and it is, in both phases (+6.4 vs +3.6 mutation gap; 17.8% vs 12.2% model gap).
The writeup still notes the Phase C intervals overlap, so it reads its own confirmation
as "consistent with prediction," not "established." Both CI styles are reported (pooled
Wilson *and* task-resampled bootstrap) because they legitimately differ and the pooled
one is anti-conservative.

### 3. The comparison the doc refuses to sell

Naively, "mutant gap 3.6%" vs "model gap 12.2%" invites a headline. The doc instead
matches denominators: restricted to things that already pass the visible suite, the
mutant leak rate is 33.7% (HumanEval) / 49.7% (MBPP) — *higher* than the model's
12.2% / 17.8%. It then explicitly rules the comparison a **caution, not a multiplier**:
the two instruments measure structurally different failure populations, and synthetic
single-edit mutants do not transfer directly to model behavior. A less careful writeup
would have picked whichever ratio flattered the thesis.

### 4. Pre-registered bars, and the fallback written down in advance

`docs/07` fixed the decision structure before the work: Phases A–C consume $0 and gate
Phase D's spend; the own-repo transfer set (Phase E) carried a pre-registered bar of
**≥30 admissible tasks** *and* a pre-written fallback — "<30 → fall back to public
holdout only, and say so." Result: **39 admissible tasks** (`data/e-corpus/`), bar met,
fallback unused but still on record. The plan also marked its own open risk honestly:
the admissible count was tagged ⚠️ UNVERIFIED in the plan until Phase E actually ran.

## What is honestly not done

- **No RL result exists yet.** Nothing here claims training works; the claim is that
  when Phase D runs, its result will be *interpretable* — against a measured verifier
  gap, a measured pre-RL baseline, and a held-out transfer set. The training run is the
  cheapest part of the plan and was still sequenced last, on purpose.
- **The extended suite is not ground truth either.** EvalPlus-extended kills more
  mutants, but `survived_both` mutants show its limits; every gap number is relative to
  the strongest available suite, not to correctness itself.
- **One base model, one size** (Qwen2.5-Coder-1.5B, k=10). The probe measures *this*
  model's gap, not a law.

## Why this transfers

Any pipeline that optimizes against an automated check — RL rewards, CI gates, eval
harnesses, LLM judges — inherits this question: *how much does the check actually
certify?* The pattern here is portable and cheap: before optimizing against a verifier,
seed known-bad inputs and measure the catch rate; probe the pre-optimization gap;
pre-register the bars and fallbacks; and refuse the flattering cross-instrument
comparison unless the denominators match. The plain-language version of the method (for
non-specialists) ships in the repo as `docs/testing-the-tests.html`.

---

*Plan: `docs/07-rescope-verifier-adequacy.md` · results: `docs/08-results-verifier-adequacy.md`
· raw artifacts: `results/` · concepts from scratch: `docs/01–06`.*
