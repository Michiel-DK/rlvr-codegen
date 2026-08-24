# 06 — Prior art and positioning (2026)

> STATUS: canon. Written 2026-08-14. All outward claims below carry a source URL and
> `verified@2026-08-14` — that is the date the link was read, not the date it stays true.
> Re-verify before any of this fronts a writeup or a conversation with someone external.

**The decision this document makes:** none of the findings below change Phases 0–2. They
land in **Phase 3 (analysis) and Phase 4 (writeup)**, where the framing is decided. Phase 0
proceeds unchanged and unblocked — see "What is gated, what isn't" at the bottom.

**Why it exists:** `04` and `05` were written 2026-07 and extended 2026-08-11, before the
field was surveyed. Three claims in them are contradicted by better sources. Rather than
rewrite canon on the strength of one afternoon's searching, the findings are quarantined
here and cited forward.

---

## 1. The held-out-test thesis is a populated subfield, not an open question

`04` presents "train tests vs held-out tests, and the finding is in the gap" as the
project's intellectual core. That design is correct. It is also, as of 2026, standard —
and its limitations are published.

| Work | Date | What it already does |
|---|---|---|
| [Countdown-Code](https://arxiv.org/abs/2603.07084) (arXiv 2603.07084) | 2026-03, rev 2026-04 | A minimal env with **dual access**: the model can solve the task *or* manipulate the harness. Cleanly separates **proxy reward (test pass/fail) from true reward (actual correctness)** — the exact instrument this repo proposes. Finds ~1% reward-hacking contamination in SFT is enough to prime hacking that RL then amplifies and generalizes beyond the training domain |
| [EvilGenie](https://arxiv.org/pdf/2511.21654) (arXiv 2511.21654) | 2025-11 | Reward-hacking benchmark using **holdout tests** (30% of cases, capped at 10) as the detector. Reports that **holdout tests have surprising failure modes** and that LLM judges are highly effective at hacking detection |
| [LLMs Gaming Verifiers](https://arxiv.org/abs/2604.15149) (arXiv 2604.15149) | 2026-04 | Taxonomy of verifier gaming — overwriting unit tests, monkey-patching scorers, deleting assertions, forcing early termination. Introduces Isomorphic Perturbation Testing |
| [Auditing Reward Hackability in Code RL Training Environments](https://arxiv.org/pdf/2606.16062) (arXiv 2606.16062) | 2026-06 | Audits public code-RL environments for reward-function defects; reports a **61.9% defect rate in LLM-augmented tests** |
| [Before the Model Learns the Bug: Fuzzing RLVR Verifiers](https://arxiv.org/html/2606.01066v1) (arXiv 2606.01066) | 2026-06 | Verifiers that run only visible tests, or accept stdout as evidence, reward code that doesn't implement the intended function |
| [SpecBench](https://arxiv.org/html/2605.21384v1) (arXiv 2605.21384) | 2026-05 | Reward hacking in long-horizon coding agents |

**The finding that actually bites:** EvilGenie documents that held-out tests — this repo's
primary instrument — **leak**. Held-out tests filter non-generalizing hardcodes but are not
robust against heuristic solutions that happen to generalize across the split, and a finite
held-out suite cannot certify specification compliance. This does not invalidate the
design. It means the honest 2026 framing is *"held-out tests are the standard instrument,
they are known to leak, here is the leak measured"* — not *"held-out tests catch reward
hacking."* `04`'s reasoning survives; `04`'s confidence does not.

## 2. Two of the plan's premises are occupied territory

**Real-PR mining into executable tasks** (`05` Phase 1b, the E-CORPUS method) is an
established line, not a novel one — `verified@2026-08-14`:

- [SWE-Gym](https://arxiv.org/pdf/2412.21139) — 2,438 real PR-sourced tasks, 11 Python repos, pre-configured executable envs
- [R2E-Gym](https://github.com/R2E-Gym/R2E-Gym) (COLM 2025) — SWE-GEN curates executable envs from *commits*, explicitly avoiding dependence on human-written PRs/tests
- [SWE-smith](https://github.com/SWE-bench/SWE-smith) (NeurIPS 2025 D&B Spotlight) — ~50k instances across 128 projects via function rewriting and bug synthesis

**Own/private repos as a held-out transfer split** is likewise occupied:

- [SWE-Bench Pro](https://static.scale.com/uploads/654197dc94d34f66c0f5184e/SWEAP_Eval_Scale%20(9).pdf) keeps a private held-out repo set precisely for overfitting checks; cross-repo evaluation holds out 103 repositories at training time
- [pre.dev](https://pre.dev/rl-environments) commercially sells runnable, verifier-scored tasks lifted from real private production codebases
- [rlvr-generalizability](https://github.com/uiuc-kang-lab/rlvr-generalizability) (ICLR 2026) already reports that RLVR gains transfer within structured domains (math↔code) but fail to generalize to unstructured ones

What remains genuinely ours is narrower and worth stating plainly: **not a novel result, a
competence demonstration** — that we can build the mining machinery and run the split
honestly on our own code. That is a portfolio claim, and it is a fine one. It is not a
research claim.

## 3. ⛔ Correction: environment packaging is table stakes, not the differentiator

`05` lines 71–75 justify the verifiers-style environment interface as *"the piece of the
RLVR stack the field currently values most."* That claim is contradicted by a better source
and must not be repeated in a writeup:

- The [Environments Hub](https://www.primeintellect.ai/blog/environments) has been live as a
  public, community-populated registry since **2025-08-27** (`verified@2026-08-14`)
- The [`verifiers` spec](https://docs.primeintellect.ai/tutorials-environments/environments)
  is documented and standardized — *"environments are modules which declare dependencies in
  a `pyproject.toml` and are distributed as wheels"* (`verified@2026-08-14`)

The field values environments enough to have **standardized and commoditized** them.
Packaging one is table stakes. The work is still worth doing — it is near-zero marginal
cost over scaffolding Phase 0 needs anyway, and it makes the artifact shareable — but the
*justification* changes from "differentiator" to "conformance to the ecosystem's interface."

- ⚠️ **UNVERIFIED:** a search snippet claimed "2,500+ community environments." Not confirmed
  against any primary source — the PI blog is 2025-08 and cites only "over 30 researchers"
  in private beta. **Do not quote the 2,500 figure.** The rank-A conclusion above stands
  without it.

## 4. Benchmark and base-model context

- **MBPP / HumanEval are widely described as saturated in 2026**, useful mainly for
  small-model separation and regression testing. ⚠️ Sourced only to SEO content sites
  (rank D) — no primary source checked, and **no pass@1 numbers are quoted here for that
  reason.** The plan's use of them for a 1.5B model is defensible on the small-model
  carve-out, but do not cite saturation figures without a primary source.
- **GRPO + LoRA on a small Qwen is handbook material** — e.g. the
  [GRPO+LoRA engineering handbook](https://huggingface.co/blog/Weyaxi/engineering-handbook-grpo-lora-with-verl)
  (`verified@2026-08-14`). This *confirms* `05`'s framing rule rather than threatening it:
  the mechanics are commodity, so the measurement has to be the deliverable.
- **Phase 5's citation predates a follow-up.** `05` rests on
  [OctoThinker](https://arxiv.org/abs/2506.20512) (2025-06).
  [PRISM](https://arxiv.org/pdf/2603.17074) (arXiv 2603.17074, 2026-03, *"Demystifying
  Retention and Interaction in Mid-Training"*) is a 2026 mid-training follow-up.
  ⚠️ **UNREAD** — surfaced in search, not opened. Read it before Phase 5 unglues, not before
  Phase 0.

---

## What this changes, and when

**Phase 3 (analysis) — adopt the leak as a measurement, not just a caveat.** The strongest
available reframing: *"held-out tests are the field's standard instrument and EvilGenie
shows they leak; here is that leak measured on tasks mined from my own repos."* That is a
2026 question rather than a 2025 one, and it costs nothing extra — it is a different read of
the same three-split table, plus the hidden/property-based tests already listed as `04`
stretch goals.

**Phase 4 (writeup) — three framing corrections are mandatory:**
1. Held-out tests presented as *known-leaky standard instrument*, not as the thesis
2. PR-mining and own-repo transfer presented as *competence demonstrated*, not novelty
3. Environment packaging presented as *ecosystem conformance*, not as what the field values most

Cite this doc's table as prior art. A writeup that implies novelty in any of the three
places is refutable in one search by anyone reading it — which is the failure mode this
document exists to prevent.

## What is gated, what isn't

- **Not gated (build now):** Phases 0, 1, 1b, 2. Sandbox, split, pass@k, CIs, rollouts,
  mining, training. Nothing above changes a line of that code. The instrument is the same
  instrument whether or not its limitations are published.
- **Gated on this doc:** Phase 3's framing and every sentence of Phase 4. Do not write the
  README's thesis paragraph without re-reading this file.
- **Gated on reading PRISM:** Phase 5 only.

## What would invalidate this doc

A primary source showing held-out-test leakage is *not* an established finding (would
restore `04`'s original confidence) · finding that the Environments Hub is dead or that the
`verifiers` spec was abandoned (would restore the `05` packaging claim) · a Phase-3 result
where the leak is unmeasurable at 1.5B scale, in which case the reframing in "What this
changes" is unavailable and the honest fallback is the original three-split table.

## Provenance

Every claim here was retrieved 2026-08-14 by web search and fetch. Sources are ranked per
`outward-claim-discipline`: arXiv papers and vendor documentation are rank A–B; the
benchmark-saturation claim in §4 is rank D and marked as such; the "2,500 environments"
figure was rejected outright for lack of a primary source. **The errors found all point
against the project** — that is the expected shape of a falsification pass, and it is why
the one surviving differentiator (§2, the own-repo split) was searched separately rather
than assumed.
