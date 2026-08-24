# 01 — Lineage and glossary

## The lineage: how we got to RLVR

**1. Pretraining.** A base model is trained to predict the next token over a huge corpus.
It knows a lot but doesn't reliably *do what you ask*.

**2. SFT (supervised fine-tuning).** Show the model examples of (prompt → good response)
and train it to imitate them. This is what `lora_llama` does for translation. SFT teaches
a behavior, but only up to the quality of the demonstrations, and it can't tell "good" from
"slightly better."

**3. RLHF (RL from human feedback).** Instead of imitating fixed answers, learn from
*preferences*. Humans rank responses; you train a **reward model** to predict those
rankings; then you use reinforcement learning (usually PPO) to push the policy toward
high reward. This is how ChatGPT-style models were aligned. It works but is heavy: a
separate reward model plus a finicky RL loop.

**4. RLVR (RL from verifiable rewards).** For some tasks you don't need a learned reward
model at all, because correctness is *checkable*. Math: is the final answer right? Code:
do the unit tests pass? The **verifier is the reward**. This is the engine under
DeepSeek-R1 and o1-style reasoning models. It's cheaper (no reward model to train) and the
reward is objective. The catch, which this repo is about, is that "checkable" is not the
same as "un-gameable."

This project sits at step 4, with `tests pass` as the verifier.

## Glossary (the words you need)

- **Policy** — the model being trained. It maps a prompt to a distribution over responses.
  In RL language, the model *is* the policy.
- **Rollout / sample** — one response the policy generates for a prompt.
- **Reward** — a number scoring how good a rollout is. Here: 1 if the code passes the
  tests, 0 if not (or a fraction: share of tests passed).
- **Reference model** — a frozen copy of the starting model. Training is regularized to not
  drift too far from it.
- **KL penalty** — a term that punishes the policy for moving too far from the reference
  model. Without it, RL can collapse into gibberish that happens to score well. KL is the
  leash.
- **Advantage** — "how much better than expected was this rollout?" Reinforce rollouts with
  positive advantage, suppress negative. The whole game is estimating a good baseline to
  subtract from the raw reward.
- **On-policy / online** — the model learns from samples it generates *right now*, during
  training. Powerful, because it can discover new behaviors, but expensive (constant
  generation) and less stable. GRPO is online.
- **Off-policy / offline** — the model learns from a *fixed, pre-collected* dataset. Cheap
  and stable, but it can't discover anything beyond what's in that dataset. DPO is offline.
- **SFT vs RL, in one line** — SFT imitates correct answers; RL optimizes a reward signal,
  so it can push *past* the demonstrations toward whatever the reward rewards (for better
  and, as this repo explores, for worse).

## The two algorithms this repo uses

- **DPO** (offline, preference pairs) — the simple, stable starting point. See
  [`02-dpo.md`](02-dpo.md).
- **GRPO** (online RL, group baseline) — the R1 recipe, the headline follow-up. See
  [`03-grpo.md`](03-grpo.md).

Both consume the *same* verifiable reward. They differ only in how they turn it into a
weight update.
