# 03 — GRPO (Group Relative Policy Optimization)

Paper: Shao et al., 2024, *DeepSeekMath* (GRPO is introduced there and is the algorithm
behind DeepSeek-R1's reasoning training).

## What it is

GRPO is real, online reinforcement learning: during training the model generates fresh
rollouts, they get scored by the reward, and the model updates from its *own current*
outputs. Generate → score → update → repeat. This is what lets new behavior *emerge*
(longer, more careful chains of thought appear on their own when they lead to higher
reward).

## The problem it solves vs PPO

PPO (the classic RLHF algorithm) needs a **value model** (a "critic"): a second network
that estimates the expected reward from a given state, used as a baseline so you know
whether a rollout beat expectations. That critic is another large model to hold in memory
and train, and it's a common source of instability.

GRPO's trick: **get the baseline from a group of samples instead of a learned critic.**

## The mechanism, step by step

For each prompt:

1. Sample a **group** of G rollouts (e.g. G = 8) from the current policy.
2. Score all G with the reward (here: run the tests on each generated program).
3. Compute each rollout's **advantage** as its reward *relative to the group*:
   `advantage_i = (reward_i − mean(rewards)) / std(rewards)`.
   So a rollout that beat the group's average gets a positive advantage; one below average
   gets negative.
4. Do a policy-gradient update: increase the probability of tokens in above-average
   rollouts, decrease it for below-average ones, with a **KL penalty** to the reference
   model keeping the policy from drifting into nonsense.

That's the whole idea. The group's own mean is the baseline. No critic network.

## Why the group baseline is clever

The hard part of policy gradients is variance: raw rewards are noisy, so you subtract a
baseline to ask "better *than what?*". PPO learns that baseline with a critic. GRPO just
uses "better than the other 7 attempts on this same prompt," which is a perfectly good
baseline and free to compute. It works especially well when the reward is cheap to
evaluate many times, which is exactly the case for verifiable rewards (running tests is
fast and deterministic).

## Why it's the impressive one (and the harder one)

- **Impressive:** it's genuine online RL, it's the R1 recipe, and it can discover behavior
  that wasn't in any dataset. "I ran GRPO with a verifiable reward" signals you understand
  where post-training actually is in 2025–26.
- **Harder:** you're generating constantly during training (throughput matters), you need
  the reward (test execution) fast and *inside the loop*, and online RL has more ways to go
  wrong: reward collapse, KL blowing up, the policy degenerating. Getting a *stable* GRPO
  run is a real skill, which is part of why it's worth demonstrating.

## The one-paragraph mental model

GRPO is writing 8 solutions yourself, running the tests on all 8, and adjusting toward
whichever ones beat your own average, on a leash so you don't drift into gibberish. You
learn from your own attempts, live, so you can bootstrap past where you started. That's the
power, and the danger: if the reward is gameable, online RL will find the game faster than
anything. Which is the subject of [`04-reward-hacking.md`](04-reward-hacking.md).

## DPO vs GRPO, side by side

| | DPO | GRPO |
|---|---|---|
| Data source | fixed pre-collected pairs | fresh self-generated rollouts |
| On/offline | offline | online |
| Baseline | the reference model (in the loss) | the group mean reward |
| Extra networks | none (just a frozen reference) | none (that's the point vs PPO) |
| Can discover new behavior | no | yes |
| Stability / cost | stable, cheap | finicky, expensive |
| Role in this repo | Phase 2 starting point | Phase 2 headline follow-up |
