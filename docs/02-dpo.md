# 02 — DPO (Direct Preference Optimization)

Paper: Rafailov et al., 2023, *Direct Preference Optimization: Your Language Model is
Secretly a Reward Model.*

## The problem DPO solves

Classic RLHF is a two-step dance: (1) train a reward model on preference pairs, then (2)
run PPO to push the policy toward high reward. Two models, and an RL loop that is hard to
stabilize.

DPO's insight is a piece of algebra: for the specific objective RLHF optimizes (maximize
reward subject to a KL leash to the reference model), the *optimal policy* can be written
directly in terms of the policy's own probabilities. So you can skip the reward model and
the RL loop, and train the policy directly on the preference pairs with a plain
classification-style loss.

## The setup

You need a dataset of triples: `(prompt, chosen, rejected)` where `chosen` is the better
response and `rejected` is the worse one. For this repo, the pairs come from the verifier:
generate several code completions, run the tests, pair a **passing** completion (chosen)
against a **failing** one (rejected) for the same prompt.

## The loss, in words

For each pair, DPO looks at four numbers:

- how likely the *policy* thinks the **chosen** response is,
- how likely the *reference model* thinks the **chosen** response is,
- the same two for the **rejected** response.

It defines an *implicit reward* for a response as `β · log( π_policy(response) /
π_reference(response) )`. In plain terms: how much more (or less) probability has the
policy put on this response compared to where it started. Then the loss pushes the
implicit reward of `chosen` to be higher than that of `rejected`. That's it: increase the
policy's relative preference for the good response over the bad one, anchored to the
reference so it can't run away.

- **β (beta)** is the knob. Small β = stay close to the reference, move cautiously. Large β
  = trust the preferences more, move harder. Typical range 0.05–0.5. Too large and the
  model overfits the pairs and degrades; too small and nothing happens.
- The **reference model** appears in the loss precisely so the update is *relative*. You're
  not memorizing the chosen text, you're shifting preference away from the reference.

## Why it's "offline"

The pairs are collected once, up front. During training the model never generates anything
new. It just sweeps the fixed pile of pairs. That's what makes DPO cheap and stable, and
also what limits it: the model can only learn preferences that are *already represented* in
your collected pairs. It cannot discover a better solution it never sampled.

## When to use it here

DPO is the **Phase 2 starting point**: get the full loop working (generate → run tests →
pair pass vs fail → DPO → eval) with something stable before reaching for online RL. It
gives an early, real result to measure.

## The one-paragraph mental model

DPO is studying from a fixed answer key of "this solution is good, this one is bad" pairs.
You get reliably better at telling those apart, anchored so you don't forget everything
else. But you never write a new solution and get graded on it, so you can't discover a
strategy that isn't already in the key. For that, you need GRPO ([`03-grpo.md`](03-grpo.md)).
