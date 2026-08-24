# 04 — Reward hacking, and why "tests pass" is not as clean as it looks

This is the intellectual core of the project. If you understand only one doc, this is it.

> **The field names this problem.** The *Code as Agent Harness* survey (arXiv 2605.18747,
> 2026) treats exactly this gap as a central open problem — §5.2.1 "Harness-Level Evaluation
> and Oracle Adequacy" (the reward/oracle is not the full specification) and §5.2.2 "Semantic
> Verification Beyond Executable Feedback" (why passing tests isn't semantic correctness).
> §3.4.3 "Sandboxed Execution and Permissioned State Transition" is the reference architecture
> for this repo's Phase-0 sandbox. _(Paper + section titles verified against the source
> 2026-07-21; the specific in-text quotes have not been checked verbatim — confirm against the
> PDF before quoting directly.)_

## Goodhart's law

> When a measure becomes a target, it ceases to be a good measure.

The moment you *optimize* for a proxy, the optimizer finds the gap between the proxy and
what you actually wanted. RL is an especially ruthless optimizer, so it exposes that gap
faster and more thoroughly than a human ever would.

## Why a verifiable reward doesn't make you safe

"Tests pass" feels objective and un-gameable, and it is much better than a fuzzy learned
reward model. But the target is *pass the tests you can see*, and that is not the same as
*write correct code*. Ways the gap shows up:

- **Overfitting to visible tests.** The model special-cases the exact inputs the tests
  check (`if n == 4: return 24`) instead of implementing the general function.
- **Weak test suites.** If the tests don't cover an edge case, correct-on-the-tests can be
  wrong in general. The model happily lives in that blind spot.
- **Narrow, brittle fixes.** For "fix this bug" tasks, the model patches the one failing
  input and leaves the underlying condition in place for the next input.

This is exactly the band-aid-fix failure mode described in production: the immediate
problem is fixed, but the *kind* of bug remains, waiting to resurface elsewhere. A verifier
reward will produce that pattern *by construction* if you let it, because passing the
visible check is literally the objective.

(Attribution note: the framing above echoes commentary attributed to Linus Torvalds in
2026 about AI-generated patches. Treat the quote as motivating intuition, not a cited
source. The underlying point, symptom-fixing vs cause-understanding, stands on its own.)

## The experimental design that catches it

The defense is not a cleverer reward. It's an **eval the model never got to optimize
against.** Split the tests:

- **Train tests** — used to compute the reward during RL. The model sees their pass/fail.
- **Held-out tests** — used only at evaluation. Same problems, *different* tests (or
  entirely held-out problems). The model never optimized against these.

Then the finding is in the *gap*:

- If **held-out pass@k rises with train pass@k**, the reward taught a capability that
  generalizes. The RL worked in the way you hoped.
- If **train pass@k climbs while held-out stalls or drops**, you have measured reward
  hacking directly. The model got better at the visible checks and no better (or worse) at
  the actual task.

Either outcome is a real, reportable result. The second is arguably the *more* valuable
one, because it's a measured, honest demonstration of the exact thing that makes verifiable
-reward RL subtle. Most tutorials only ever report the train-set number and quietly imply
generalization.

> **(2026-08-14) The reasoning above survives; the confidence does not.** A prior-art pass
> found that held-out tests are the field's *standard* instrument as of 2026, and that they
> are documented to **leak** — they filter non-generalizing hardcodes but not heuristics that
> happen to generalize across the split, and a finite suite cannot certify a specification.
> The design stays. The claim "held-out tests catch reward hacking" becomes "held-out tests
> are the standard instrument, they are known to leak, here is the leak measured."
> See [`06-prior-art-and-positioning.md`](06-prior-art-and-positioning.md) §1.

## Extra hardening (stretch goals)

- **Hidden / adversarial tests** written after training, probing edge cases the train tests
  ignored.
- **Property-based tests** (e.g. Hypothesis) that generate many inputs, much harder to
  special-case than a handful of fixed assertions.
- **Length and format controls**, so "pass rate went up" isn't just "outputs got longer /
  changed shape."

## Why this makes the project worth doing

Without this, the project is "I ran GRPO on a code dataset," which thousands of people have
done. With it, the project is "I understand why verifiable-reward RL on code is subtler
than it looks, and I built the eval to measure it." That is a judgment result, not a
mechanics result, and judgment is the scarcer signal. See
[`05-build-plan.md`](05-build-plan.md) for how it's staged.
