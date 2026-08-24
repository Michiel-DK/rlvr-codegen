# 05 — Build plan

> ⛔ **STATUS: superseded-by [`07-rescope-verifier-adequacy.md`](07-rescope-verifier-adequacy.md)
> (2026-08-14).** `07` outranks this doc because this one was written before the field was
> surveyed — [`06`](06-prior-art-and-positioning.md) retracted three of its framing claims
> with sources, and its phase order put the first shippable artifact behind a rented GPU.
> `07` keeps this doc's economics, stack, risks and framing rule, and inverts the order so
> the verifier is measured before it is trained against.
>
> **Kept for history and for the parts `07` carries forward verbatim. Do not plan from this
> file.** The historical status line follows.

> STATUS: canon *(historical — see supersession above)*. Written 2026-07 (rescope from
> translation-RLAIF); **extended 2026-08-11**
> (transfer eval on own repos · environment packaging · mid-training arm). Premises below.
>
> **(2026-08-14) Prior-art pass:** [`06-prior-art-and-positioning.md`](06-prior-art-and-positioning.md)
> surveyed the 2026 field and corrected three framing claims in this doc. **Phases 0–2 are
> unchanged and unblocked.** The corrections bind Phase 3's analysis and every sentence of
> Phase 4 — read `06` before writing the writeup, not before writing the sandbox.

Rescoped from the original translation-RLAIF plan to **code generation with execution
reward**, with **held-out-test generalization as the core thesis**
(see [`04-reward-hacking.md`](04-reward-hacking.md)).

## Rescope 2026-08-11 — what changed and why

**Decision this document makes:** Q2 ships as a *measurement artifact* (reward-hacking +
generalization readout), never as "a training run" — a plain GRPO run is 2026 course
homework and would dilute the portfolio's eval-first story. Three binding conditions:
(1) measurement-led framing; (2) a **transfer eval on our own production repos** as the
third split; (3) the writeup sits inside the verification thesis (same Goodhart class as
the harness's A2 / criterion-gate work). If holdout discipline gets cut to "just get a run
done", STOP — that version is worse than leaving the repo as docs.

**Premises (and their status):**
- Real-PR tasks are minable: E-CORPUS probe measured **6/8 red→green pairs reproducible at
  base commits** (agent-sandbox, verified 2026-08-01). Portfolio ≈ 1,500–2,000 merged PRs
  → ⚠️ UNVERIFIED estimate 50–300 admissible tasks; Phase 1b measures the real number.
- Own code as mid-training corpus is TOO SMALL alone: **≈14M tokens** measured across the
  six repos (2026-08-11) vs the ~100M+ a meaningful pass wants → own code is a domain
  slice (~5–10%) mixed into public code, never the corpus.
- Costs below assume vast.ai $0.3–0.6/hr — spot-checked 2026-08, re-check at rental time.

**What would invalidate this plan:** Phase 1b yields <30 admissible own-repo tasks (the
transfer eval loses power → fall back to public-only holdout and say so in the writeup) ·
GRPO never stabilizes after budgeted retries (fall back to the DPO-only result — already
an allowed outcome below) · the E-CORPUS admissibility machinery proves non-reusable.

**Stop rule (commitment test):** Phases 0–1 are CPU-only laptop work. If Phase 0 stalls
past ~2 focused days, stop — nothing has been rented, and the repo honestly stays docs.

## The one-line story the finished repo tells

"I trained a small code model with RL from a verifiable reward (unit tests), and measured
whether it learned to write correct code or just to pass the visible tests — on held-out
tests it never optimized against, **and on tasks mined from my own production repos**,
with confidence intervals."

Hits: post-training depth (DPO + GRPO), eval rigor (held-out pass@k + CIs), GPU/scale, a
deep flagship, and a judgment thesis that most RLVR demos skip.

## The loop

```
coding tasks ──▶ policy samples k programs each ──▶ run TRAIN tests (sandbox) ──▶ reward
                                                                                    │
        DPO: pair passing vs failing programs        GRPO: group-relative advantage
                                                                                    │
                                     update policy (LoRA) ──▶ policy'
                                                                                    │
              eval: policy' vs base on HELD-OUT tests — pass@k with bootstrap CIs
```

## Phases

### Phase 0 — Eval harness + sandbox first (highest value, no training)
- Pick a dataset with tests: **MBPP** and/or **HumanEval** (small, standard, per-problem
  unit tests). Freeze an explicit **train-tests / held-out-tests** split (or held-out
  *problems*), committed to the repo with a seed.
- Build a **safe execution sandbox**: run model-generated code in isolation (subprocess
  with timeout + resource limits, or a container). This is the infra piece that doubles as
  a showcase, and it must be airtight before any RL touches it.
- Implement **pass@k** (unbiased estimator, Chen et al. 2021) and **bootstrap 95% CIs**.
- Deliverable: base-model pass@k on the held-out set, reproducible from one command, with
  CIs and committed predictions. A defensible baseline before any RL.
- **(2026-08-11) Package tasks + sandbox behind a verifiers-style environment interface**
  (task in → rollout → reward out). Near-zero extra cost over the scaffolding we need
  anyway, and it turns Phase 0 into a shareable 2026-native artifact — "a verifiable-code
  environment mined from real production PRs." ⛔ **(2026-08-14) The original justification
  here — "the piece of the RLVR stack the field currently values most" — is retracted:**
  the Environments Hub and the `verifiers` spec have standardized this, so packaging is
  *ecosystem conformance*, not a differentiator. Still worth building; do not sell it as
  novel. See [`06-prior-art-and-positioning.md`](06-prior-art-and-positioning.md) §3.
- Estimated: 1–2 days, ~$0 (CPU). Reuse agent-sandbox's E-CORPUS admissibility code.

### Phase 1 — Preference / rollout data
- Policy: a small code model, e.g. **Qwen2.5-Coder-1.5B** (has real code ability at small
  size). LoRA for all training.
- For each train task, sample **k = 4–8** programs, run the **train** tests, record
  pass/fail (and fraction passed).
- For DPO: form pass-vs-fail pairs per task (drop tasks with all-pass or all-fail, no
  signal). For GRPO: keep the raw per-rollout rewards.
- Estimated: 1–2 days, ~$0.

### Phase 1b — (2026-08-11) The own-repo transfer set
- Mine the portfolio's merged PRs into eval-only tasks via the E-CORPUS method: base
  commit + the PR's test file must fail (RED), merged commit must pass (GREEN); both
  reproduced locally or the task is inadmissible. Measured precedent: 6/8 on easy picks.
- These tasks are **never trained on**. They are the third split — the transfer eval that
  answers "did RL on public tasks generalize to real production code."
- Report the admissible count with its denominator. <30 admissible → the invalidation
  clause above fires (fall back to public holdout only, and say so).
- Estimated: 1–2 days, ~$0 (mining + red/green reproduction is CPU).

### Phase 2 — Train
- **DPO first** (offline, stable): get the whole loop producing a measurable result.
- **GRPO next** (online, the headline): sample groups, reward from the sandbox in the loop,
  group-relative advantage, KL to reference. Watch for reward collapse / KL blow-up.
- Tooling: `trl` (`DPOTrainer`, `GRPOTrainer`), `peft` (LoRA), `transformers`.

### Phase 3 — Evaluation + reward-hacking analysis (the part that sells it)
- policy' vs base on the **held-out** tests: pass@1 and pass@k, with bootstrap CIs.
- **(2026-08-11) Three splits, not two:** train / held-out-public / **own-repo transfer**
  (Phase 1b). The transfer column is the differentiated result; report it even (especially)
  if it's flat.
- **The key plot:** train pass@k vs held-out pass@k over training. Generalization = both
  rise together. Reward hacking = train rises, held-out stalls/drops.
- Overfitting probes: does the model special-case visible inputs? Spot-check failures;
  optionally add **property-based / hidden tests** written after training.
- **(2026-08-14) Measure the instrument, not just the model.** EvilGenie documents that
  held-out tests themselves leak — they filter non-generalizing hardcodes but not heuristics
  that happen to generalize across the split. The stronger read of the same three-split
  table is *"here is how much the standard instrument leaks, measured on my own repos."*
  Costs nothing extra beyond the hidden/property-based tests already listed above.
  See [`06`](06-prior-art-and-positioning.md) §1.
- Controls: output length and format before/after, so gains aren't an artifact.

### Phase 4 — Writeup
- README leads with the thesis and the one held-out table (CIs). A "what we found about
  reward hacking" section. Model card / RESULTS.md naming exact adapters + the one-command
  eval.
- **(2026-08-11) Framing rule:** the writeup sits inside the verification thesis — same
  Goodhart class as the harness's vacuous-guard (A2) and criterion-gate work. It is an
  eval-rigor artifact that happens to contain a training run, not "my RL project".
- **(2026-08-14) Three mandatory corrections, all from [`06`](06-prior-art-and-positioning.md):**
  held-out tests are a *known-leaky standard instrument*, not the thesis · PR-mining and the
  own-repo split are *competence demonstrated*, not novelty · environment packaging is
  *ecosystem conformance*. Cite `06`'s prior-art table. A writeup implying novelty in any of
  the three is refutable in one search by whoever reads it.
- Estimated: 0.5–1 day.

### Phase 5 — (2026-08-11) Mid-training arm — GATED: do not start until Phases 0–4 are DONE
- The OctoThinker comparison at toy scale ([2506.20512](https://arxiv.org/pdf/2506.20512):
  mid-training choices determine RL scaling). Take the **non-Coder** Qwen2.5-1.5B base
  (the "-Coder" variant already carries Qwen's own code mid-training — using it would
  confound the comparison), continued-pretrain (plain next-token, no RL) on ~100–500M
  tokens of public code with our ≈14M own-code tokens as a ~5–10% domain slice
  (the OctoLong recipe: cross-repository contexts).
- Then re-run Phases 2–3 **unchanged** on both bases. The deliverable is one table:
  same RLVR recipe, mid-trained vs raw base, delta measured on all three splits.
- Corpus curation is the real work (1–2 days), not the compute (~5–20 GPU-h, $10–30;
  re-run of 2–3 adds $15–35). Arm total: **+$30–65, ~1 extra week.**
- Why gated: mid-training without the Q2 instrument is a shaped base with nothing to
  measure the shaping against.
- **(2026-08-14)** OctoThinker is 2025-06; [PRISM](https://arxiv.org/pdf/2603.17074)
  (2603.17074, 2026-03) is a mid-training follow-up. ⚠️ **UNREAD** — read it before this
  phase unglues. Gates nothing earlier.

## GPU / cost / time

- Qwen2.5-Coder-1.5B + LoRA fits a single 24 GB GPU (RTX 4090 / A10). Sandbox runs on CPU
  alongside.
- Vast.ai ~$0.3–0.6/hr. The wall-clock cost is dominated by rollout generation + test
  execution, not the gradient step.
- Rough total: **~20–50 GPU-hours → ~$15–40.** GRPO is the expensive half.
- **(2026-08-11) With a realistic first-GRPO debugging margin (1.5–2×): budget $30–80 and
  ~1.5–2 focused part-time weeks for Phases 0–4.** Phases 0/1/1b are CPU-only (~$0);
  Phase 2 wall-clock is mostly unattended. Mid-training arm (Phase 5): +$30–65, +1 week.
  Both together: **~$60–150, 3–4 part-time weeks.**

## Stack

`trl` (DPOTrainer / GRPOTrainer) · `peft` (LoRA) · `transformers` · a sandbox
(subprocess + timeouts, or a container) · `datasets` (MBPP / HumanEval) · numpy (bootstrap)
· W&B for tracking, artifacts committed to the repo.

## Honest risks (state them in the writeup)

- **Sandbox safety is non-negotiable.** You are executing model-generated code. Isolate it
  (timeouts, no network, resource caps, ideally a container). Get this right before RL.
- **Reward hacking is the expected result at small scale**, not a bug to hide. The held-out
  split is built to catch it, and catching it is a valid outcome.
- **Small model ceiling.** A 1.5B coder is limited; absolute pass@k will be modest. The
  value is the loop + the generalization measurement, not topping a leaderboard.
- **GRPO instability.** Budget time for it. If GRPO won't stabilize, a rigorous DPO result +
  an honest "GRPO notes" writeup is still a strong deliverable.

## Definition of done

- A trained adapter (DPO, ideally also GRPO) with **held-out pass@k** reported against the
  base model, with non-overlapping 95% CIs — plus an explicit read on whether the gain
  generalized or reward-hacked, backed by the train-vs-held-out curve.
- **(2026-08-11)** The **own-repo transfer column** reported alongside (or the <30-tasks
  fallback declared), and the Phase-0 environment packaged behind the verifiers-style
  interface.
- Every number reproducible from a committed eval script + frozen split + sandbox.
- Phase 5 has its own done: the two-base comparison table, or an honest "arm not run"
  with the gate's reason.
