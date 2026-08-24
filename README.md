# rlvr-codegen

> **Public snapshot (2026-08-24).** Sanitized snapshot of the working repo: the private
> build-harness submodule (`harness/`) is removed, and `data/e-corpus/tasks.jsonl` has
> titles/notes redacted for tasks mined from private production repos (task shapes,
> verification evidence and all HumanEval/MBPP results are intact).


A learning-driven project: train a small code model with **reinforcement learning from
verifiable rewards (RLVR)**, where the reward is "do the unit tests pass," and study the
one question that makes or breaks the whole idea: does the model *learn to write correct
code*, or does it just *learn to pass the visible tests*?

This repo is two things at once:

1. **A build project** toward a rigorous, reproducible RLVR result (live plan:
   [`docs/07-rescope-verifier-adequacy.md`](docs/07-rescope-verifier-adequacy.md)).
2. **A set of from-scratch notes** on the concepts, so the learning is durable and legible
   to anyone reading (including future me). Start with the docs below.

**Results so far (2026-08-15, ~$0, no GPU):** the verifier was measured before anything
trains against it — mutation-score gap between the visible and EvalPlus-extended suites of
**+3.6%** (HumanEval) / **+6.4%** (MBPP), and a pre-RL base-model probe showing **12.2%**
(HumanEval) / **17.8%** (MBPP) of visible-passing completions fail the extended suite.
Plus a 39-task eval-only transfer set mined from this account's own repos
([`data/e-corpus/`](data/e-corpus/)). Full writeup:
[`docs/08-results-verifier-adequacy.md`](docs/08-results-verifier-adequacy.md); raw
artifacts under [`results/`](results/); plain-language explainer (open in a browser):
[`docs/testing-the-tests.html`](docs/testing-the-tests.html).

## The thesis (why this project is worth doing)

"Tests pass" looks like a clean, objective reward. It is more gameable than it looks. A
model optimized purely to turn the visible tests green can produce narrow, special-cased
fixes that satisfy the check without the underlying logic being right. That is the
band-aid-fix failure mode: the immediate problem is fixed, the *kind* of bug remains.

So the core experiment is not "can RL make a code model pass more tests." It is:

> Train on one set of tests, evaluate on a **held-out set the model never optimized
> against**, and measure whether the gains generalize or just memorize the visible checks.

A rigorous result either way is the point. If held-out `pass@k` rises with train `pass@k`,
the reward taught real capability. If train `pass@k` climbs while held-out stalls, we have
measured reward hacking directly, which is itself a strong, honest finding.

## Learning path (read in order)

| Doc | What you'll understand |
|---|---|
| [`docs/01-lineage-and-glossary.md`](docs/01-lineage-and-glossary.md) | The lineage SFT → RLHF → RLVR, and the vocabulary (policy, reward, KL, advantage, on/offline) |
| [`docs/02-dpo.md`](docs/02-dpo.md) | DPO from scratch: preference pairs, the loss, β, why it's "offline" |
| [`docs/03-grpo.md`](docs/03-grpo.md) | GRPO from scratch: online RL, the group baseline, no critic, the R1 recipe |
| [`docs/04-reward-hacking.md`](docs/04-reward-hacking.md) | Why test-pass reward is gameable, Goodhart's law, held-out vs hidden tests |
| [`docs/05-build-plan.md`](docs/05-build-plan.md) | ⛔ superseded by `07` — kept for history, GPU/cost model still valid |
| [`docs/06-prior-art-and-positioning.md`](docs/06-prior-art-and-positioning.md) | Where this sits in the 2026 field, what's already occupied, and the three framing claims that were retracted |
| [`docs/07-rescope-verifier-adequacy.md`](docs/07-rescope-verifier-adequacy.md) | **The live plan.** Measure the verifier before training against it |
| [`docs/08-results-verifier-adequacy.md`](docs/08-results-verifier-adequacy.md) | **The results.** Phases A–C measured: the verifier gap, the environment it stands on, the pre-RL baseline |

## Status

Planning + learning stage. No training runs yet. Private until there is a reproducible
result worth showing.

**Next move is Phase A + B of [`docs/07`](docs/07-rescope-verifier-adequacy.md)** — build the
environment, then measure how much its reward actually certifies (mutation score + the
visible-vs-extended test gap). No GPU, no training, ~$0. If that table doesn't exist by the
end of the weekend of 2026-08-15, the plan says stop.
