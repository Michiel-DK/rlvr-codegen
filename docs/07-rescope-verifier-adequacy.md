# 07 — Rescope 2026-08-14: verifier adequacy first

> STATUS: canon. **Supersedes [`05-build-plan.md`](05-build-plan.md)** as the live build plan.
> Written 2026-08-14, after the prior-art pass in
> [`06-prior-art-and-positioning.md`](06-prior-art-and-positioning.md).
> Premises and their verification dates below. `04` (concepts) and `06` (prior art) remain
> canon and are unchanged by this doc.

**Why this outranks `05`:** `05` was written before the field was surveyed. `06` retracted
three of its framing claims with sourced evidence. `05` also ordered the work so that the
first shippable artifact required a rented GPU — which put every deliverable behind the most
expensive, most commodity step. This doc keeps `05`'s economics and discipline and inverts
its order.

**This is the third rescope** (translation-RLAIF → code RLVR → 08-11 transfer eval → here),
on a repo that has shipped zero code. That is recorded, not hidden. The kill criterion at the
bottom exists specifically so there is no fourth.

---

## The decision this document makes

**Measure the verifier before training against it.** The first deliverable is a number about
*the reward function*, produced with no GPU, no training, and no rented anything. Training
moves behind it.

The one-line story becomes:

> "Before training a code model with a test-pass reward, I measured how much that reward
> actually certifies — mutation scores and the visible-vs-extended test gap on my own
> environment — then trained against it and showed what the gap predicted."

## What carries forward from `05` unchanged

- The economics: vast.ai ~$0.3–0.6/hr, ~20–50 GPU-h → $15–40 for the training half, $30–80
  with a realistic first-GRPO debugging margin. Re-check at rental time.
- The stack: `trl` · `peft` (LoRA) · `transformers` · `datasets` · numpy · W&B.
- The policy: Qwen2.5-Coder-1.5B + LoRA, fits a single 24 GB GPU.
- The honest risks, all four — sandbox safety non-negotiable, reward hacking expected at
  small scale, small-model ceiling, GRPO instability.
- The framing rule: this ships as a measurement artifact, never as "a training run."
- The own-repo transfer set and the gated mid-training arm, moved to Phases E and G below.

## What changed, and why

**1. The resource that is actually scarce is not the one `05` optimized for.** `05` budgets
dollars and GPU-hours. The binding constraint is *operator attention and token budget*.
Phases A–C below consume only that; Phase D is the first that needs money. Sequencing the
free work first is not timidity, it is matching the plan to the constraint.

**2. Reward hacking is the named bottleneck of a real market.** Epoch AI's RL-environments
FAQ ([`epoch.ai`](https://epoch.ai/gradient-updates/state-of-rl-envs), 2026-01-12,
`verified@2026-08-14`) reports reward hacking as the *top* difficulty in environment
construction — "many many iterations to check against" — with quality control the #1
bottleneck. Prime Intellect pays bounties for environments
([program post](https://www.primeintellect.ai/blog/scaling-environments-program),
2025-10-27, `verified@2026-08-14`; ⚠️ ~10 months stale — re-check before relying on it):
**$100–500** open-access, **$1000–5000+** application-only.
- ⚠️ Their published domain list is Autonomous AI Research, Frontier Evals, Browser
  Automation, Theorem Proving, Subject-Specific QA, Legal/Finance. **Code quality is NOT on
  it.** A search snippet claimed otherwise; the primary source does not support it. Do not
  plan around a code-environment bounty existing.
- ⚠️ The large figures in the Epoch piece ($20k/environment, ~$300k for a Slack replica,
  six-to-seven figures per quarter) are **lab↔vendor contracts**, and Epoch explicitly does
  not address whether independent builders reach that market. They are context, not a
  business case.

**3. A verifier audit needs no model at all.** [arXiv 2606.16062](https://arxiv.org/pdf/2606.16062)
audited existing code-RL environments for reward hackability without training anything
(`verified@2026-08-14`). That is an existence proof that Phase B below produces a real result
on its own.

## The instrument (this is the part `05` did not have)

**Measured 2026-08-14:** the original benchmarks ship too few tests to certify much.

| Suite | Tests per problem | Source |
|---|---|---|
| MBPP | ~3 per problem | ⚠️ rank-D secondary; confirm against the dataset in Phase A |
| HumanEval | ~9.6 average | ⚠️ rank-D secondary; confirm against the dataset in Phase A |
| **MBPP+** | **35× MBPP** | [evalplus/evalplus](https://github.com/evalplus/evalplus) (primary, `verified@2026-08-14`) |
| **HumanEval+** | **80× HumanEval** | [evalplus/evalplus](https://github.com/evalplus/evalplus) (primary, `verified@2026-08-14`) |

That asymmetry **is** the instrument:

- **The original suite = the verifier the reward would use.** Small, and the thing an RL
  policy would optimize against.
- **The EvalPlus extended suite = the adequacy oracle.** ⚠️ It is a *strictly stronger proxy,
  not ground truth.* Any claim that it measures "true correctness" is false and must not
  appear in the writeup.
- **Code that passes the original and fails the extended is a measured verifier gap** — the
  hardcode/fragility failure mode `04` describes, quantified, with no training required.

⚠️ **Design consequence: prefer HumanEval as the primary target.** Three assertions (MBPP) is
too coarse for a meaningful mutation score. Confirm the real per-problem counts in Phase A
before committing — if HumanEval's ~9.6 doesn't hold, Phase B's headline number may not
exist, and that is the kill criterion firing.

## Phases

Each phase produces a standalone deliverable. Any phase can be the last one and the repo
still says something true.

### Phase A — Environment + ruler · CPU/tokens · ~$0
Sandbox (subprocess, timeouts, no network, resource caps — airtight before anything else),
frozen seeded train/held-out split committed to the repo, pass@k (Chen et al. unbiased
estimator) + bootstrap 95% CIs, one-command reproducible base-model baseline. Packaged behind
the `verifiers`-style interface (task in → rollout → reward out) — **as ecosystem
conformance, not as differentiation** (`06` §3). Emits **run manifests** (split seed, config,
metrics, CIs, committed predictions) and **JSONL trajectory logs**. Confirm the per-problem
test counts in the table above while here.

### Phase B — Verifier adequacy audit · CPU/tokens · ~$0 · **the headline**
No model, no training. Two measurements on the environment built in A:
1. **Mutation score** — inject bugs into reference solutions (`mutmut` or `cosmic-ray`), then
   measure what fraction the *original* suite catches vs what the *extended* suite catches.
   The delta is how much the reward fails to certify.
2. **Visible-vs-extended gap** — pass rate on original tests vs EvalPlus tests, per problem.
3. Each verifier carries a **declared scope**: what it verifies, what it cannot. Property-based
   checks (`hypothesis`) as a third verifier where the task shape allows.

Deliverable: a mutation-score table with CIs. This is publishable on its own and needs
nothing rented.

### Phase C — Base-model hacking probe · CPU/tokens + cheap inference · ~$0–5
Sample k programs from the base model, score against original vs extended suites. Measures
how often a *non-RL* model already produces code that games the visible tests. Establishes
the baseline gap that Phase D's training either widens (hacking) or narrows (generalization).
⚠️ This measures the visible→extended gap, **not** correctness — see the instrument note.

### Phase D — Train · GPU · $30–80 · gated on A–C
DPO first (offline, stable), then GRPO (online, the headline). The reward is Phase A's
environment. The question is now sharp: *does the train→extended gap widen under RL?*

### Phase E — Own-repo transfer set · CPU/tokens · ~$0
Mine merged PRs into eval-only tasks via the E-CORPUS method (base commit RED, merged commit
GREEN, both reproduced or inadmissible; measured precedent 6/8 on easy picks, agent-sandbox
2026-08-01). Never trained on. <30 admissible → report the fallback, as `05` required.
Framed as **competence demonstrated, not novelty** (`06` §2).

### Phase F — Writeup
`06`'s three mandatory corrections are binding. Lead with the Phase B table.

### Phase G — Mid-training arm · GATED on A–F
Unchanged from `05` Phase 5. Read [PRISM](https://arxiv.org/pdf/2603.17074) (⚠️ UNREAD) first.

## Premises, and their status

- **EvalPlus multipliers (80×/35×)** — ✅ primary source, `verified@2026-08-14`.
- **Per-problem test counts for MBPP/HumanEval** — ⚠️ rank-D secondary only. Phase A confirms.
- **Reward hacking is the environment market's top bottleneck** — ✅ Epoch AI, 2026-01-12.
- **A verifier audit needs no training** — ✅ existence proof, arXiv 2606.16062.
- **PI bounties** — ⚠️ post is ~10 months old; no code-environment category confirmed.
- **Real-PR tasks are minable** — 6/8 measured (agent-sandbox 2026-08-01); portfolio-wide
  admissible count remains ⚠️ UNVERIFIED until Phase E.

## Kill criteria — what ends this

- **The weekend rule.** If Phase A + Phase B do not produce a mutation-score table by the end
  of the 2026-08-15 weekend, stop. Nothing has been rented and the repo honestly stays docs.
  A rescope that drops its kill criterion is how a third rescope becomes a fourth.
- Per-problem test counts too thin for a meaningful mutation score on either benchmark, with
  no cheap fix → Phase B's headline does not exist; say so and stop.
- Phase E yields <30 admissible own-repo tasks → fall back to public holdout only, and say so.
- GRPO never stabilizes after budgeted retries → the DPO result plus honest GRPO notes stands.

## Definition of done

- **Phase B alone:** a mutation-score + visible-vs-extended table on a packaged environment,
  reproducible from one command. This is a complete deliverable.
- **Full:** the above, plus a trained adapter with held-out pass@k against base with
  non-overlapping 95% CIs, plus the own-repo transfer column (or its declared fallback), plus
  an explicit read on whether the gain generalized or hacked — backed by whether the
  visible→extended gap widened under training.
- Every number reproducible from a committed script + frozen split + sandbox + run manifest.
