"""rlvr.generate — completion-style sampling for docs/07 Phase C (base-model hacking probe).

Phase C samples k programs from the UNTRAINED base model and scores them against the visible
(base) and extended (base ∪ plus) suites. ⚠️ Per docs/07's instrument note: this measures the
visible→extended gap, NOT correctness. A high pass rate on either suite is not a claim that the
sampled code is "right" — see rlvr/env.py and docs/07 for what "extended" does and does not
certify.

Backend protocol
-----------------
:class:`Generator` is a narrow ``Protocol`` (``generate(prompt, *, max_tokens, temperature,
seed) -> str``) so a hosted-API backend can be added for Phase D without touching any caller of
this module. :class:`MlxGenerator` is the only implementation today, backed by ``mlx-lm``
(Apple Silicon). ``mlx_lm``/``mlx`` are imported lazily, inside ``MlxGenerator``'s methods, not
at module import time — this keeps ``rlvr.generate`` importable (for ``truncate_completion``,
``build_prompt``, unit tests with a fake ``Generator``) in an environment that never installed
the optional ``gen`` extra (``pip install -e '.[gen]'``).

FALSIFIER RESULT (A1, verified 2026-08-15, Apple M1 Pro / 16 GB)
--------------------------------------------------------------------
``mlx-community/Qwen2.5-Coder-1.5B-Instruct`` (the model named in the brief as a thing to rule
out) is the WRONG model for this probe — it is instruction-tuned, not the completion-style base
model docs/07's policy choice calls for. Checked the ``mlx-community`` org on the HF Hub
(``HfApi().list_models(search="Qwen2.5-Coder-1.5B", author="mlx-community")``, 2026-08-15) and
found a base (non-instruct) conversion: **``mlx-community/Qwen2.5-Coder-1.5B-bf16``**. Loaded via
``mlx_lm.load`` and generated a completion for a HumanEval-style prompt at ``temperature=0.8``:
completes and continues the function body without instruction-following scaffolding (no chat
template, no "Here's the function:" preamble) — confirms it is the base model. Measured
~41 tok/s sustained generation (M1 Pro, ``mlx-lm==0.31.3``, ``mlx==0.32.0``, model already
downloaded/cached; cold download of the ~3 GB ``bf16`` weights took ~66s on this connection,
one-time cost). This is the default ``--model`` for ``scripts/run_phase_c_sample.py``.

Seeding and reproducibility (spec item 1 — checked empirically, not assumed)
--------------------------------------------------------------------------------
``MlxGenerator.generate`` calls ``mx.random.seed(seed)`` immediately before each
``mlx_lm.generate`` call. This mutates MLX's **global** RNG state (there is no per-instance RNG
handle in ``mlx_lm``'s public API) — sequential calls on the same ``MlxGenerator`` instance are
therefore each individually seeded and don't depend on call order for their OWN output, but two
back-to-back calls sharing a process do share (and each reset) the same global generator.

Checked empirically (2026-08-15, single process, one loaded ``mlx-community/Qwen2.5-Coder-1.5B-bf16``
instance, ``mlx-lm==0.31.3``/``mlx==0.32.0``): two ``generate`` calls with identical
``(prompt, max_tokens, temperature=0.8, seed)`` produced byte-identical output. **This is
evidence for same-process, same-model-instance, same-library-version determinism only.** It is
NOT verified (and should not be assumed) across separate process invocations, across an mlx/mlx-lm
version bump, or across different hardware. Record the seed and the library versions on every
sample (the sampler script's manifest does this) so a reproduction attempt can check whether it
actually reproduced rather than assuming it did.

``derive_seed`` computes a deterministic per-sample seed from a stable hash (``hashlib.sha256``,
not Python's built-in ``hash()``, which is randomized per-process unless ``PYTHONHASHSEED`` is
pinned) of ``f"{task_id}:{sample_idx}"``, XORed with the run's base seed — so a resumed run
generates the exact same missing samples regardless of what order they're requested in. Verified
this round-trips through ``mx.random.seed`` without error for realistic values (64-bit ints,
e.g. ``20260814 ^ int.from_bytes(sha256(b"HumanEval/0:0").digest()[:8], "big")`` — mlx accepts
it directly, no narrowing needed).

Completion post-processing — first-line indent repair (found running the real-model smoke test)
------------------------------------------------------------------------------------------------
Running the required real-model smoke (2026-08-15, 3 HumanEval heldout tasks, k=2, 6 samples
total) surfaced a systematic bug: **all 6** raw completions failed to even compile
(``SyntaxError: unindent does not match any outer indentation level``), because every one of
them started its first line with exactly 3 leading spaces where 4 were needed. Traced to the
tokenizer, not the model's coding ability: encoding a HumanEval prompt's trailing
a 4-space-indented docstring-closing line (three quote characters, then newline) with this
model's tokenizer splits it as token ``"   "`` (3 spaces) followed by a second token holding ONE
more space bundled together with the quote characters — verified directly via
``tokenizer.encode``. The prompt's own last token
already "spends" one of the four indent spaces, so the model's first generated token needs to
itself start with a leading space to reach the correct depth; when it instead predicts a token
with no (or too little) leading whitespace, the resulting text is short by exactly the swallowed
amount. This is a known class of BPE prompt/completion-boundary artifact in code-LM evaluation,
not evidence the base model can't write an indented body — the semantic content of all 6 raw
completions (checked by hand) was reasonable Python.

``expected_body_indent`` computes the correct target width per-task, from
``task.reference_solution`` (past ``code_prefix``, so it works identically for both datasets)
rather than a hardcoded constant — MBPP reference solutions are NOT uniformly 4-space-indented
(checked directly: ``Mbpp/2`` uses 2-space bodies, ``Mbpp/3``/``Mbpp/4`` use 4-space), so a
hardcoded "always pad to 4" would have actively corrupted 2-space MBPP completions (fixing only
the first line, leaving every subsequent line at the task's real 2-space depth, i.e. introducing
a NEW mismatch instead of fixing the original one). ``repair_first_line_indent`` then pads the
completion's first line up to that width — but ONLY when it already has SOME indentation (1..N-1
spaces) that's short of the target; a completion whose first line has ZERO leading whitespace is
left untouched, because that is a materially different (and real) failure mode — the model
producing unindented, top-level-looking content — not the swallowed-space artifact this repair
targets, and forcing indentation onto it would manufacture a pass the sample didn't earn.
``scripts/run_phase_c_sample.py`` calls this repair on every raw completion before
``truncate_completion``, and records whether it fired (``indent_repaired: bool``) on the sample
record — Phase C's own results should be able to report how often this kicked in, not just
silently apply it.

Completion post-processing — ``truncate_completion``
--------------------------------------------------------
A completion-style base model does not stop at the end of the target function the way an
instruction-tuned model would; it keeps going (usage examples, a ``class`` definition, another
``def``, a ``__main__`` block, ...). This is the standard HumanEval-style treatment used
throughout the literature (a superset of the commonly cited stop-word list ``\\ndef``, ``\\nclass``,
``\\nif __name__``, ``\\nprint(``, ``\\n#``, ``\\nassert``): truncate at the first **non-blank
line at column 0** (no leading whitespace) after the first line of the completion.

This single rule subsumes all the named stop-words above — each of them is a specific instance
of "a non-blank line at column 0" — while also catching cases the named list misses (e.g. a bare
``x = 5`` or a ``for ...:`` loop emitted at the top level after the function body, neither of
which starts with any of the six named keywords). The completion's very first line is exempt:
it is a continuation of the still-open function signature/body from the prompt (verified against
real generations — see the falsifier result above, where the first line of the raw completion is
itself indented body content), and must never be truncated away on its own. A line nested inside
the function (e.g. a ``def helper():`` indented under the target function) is NOT at column 0 and
is correctly preserved — see ``tests/test_generate.py``'s nested-def case.

Declared limitation: this rule does not track bracket/backslash-continuation depth. A
multi-line expression whose continuation line happens to be written at column 0 (unusual, but
syntactically legal Python) would be truncated mid-expression by this heuristic. This is the same
scope tradeoff the cited stop-word literature makes; not fixed here for the same reason: real
base-model completions overwhelmingly re-indent continuations, and tracking bracket depth
through ``ast``-unparsed and non-``ast``-parseable partial text is a materially harder problem
this probe does not need to solve.

Prompt construction — HumanEval vs MBPP (spec item 3)
----------------------------------------------------------
**HumanEval**: ``task.prompt`` verbatim, completion style — this is exactly rlvr/env.py's A4
composition rule (``task.prompt + code`` is valid, directly-executable Python). ``code_prefix``
is ``""``: the model's (truncated) completion IS the full ``code`` argument for
``rlvr.env.evaluate_code``.

**MBPP**: checked the actual shape of MBPP prompts in ``rlvr/data.py`` (verified again here,
2026-08-15, across all 378 MBPP+ tasks) — they are a natural-language docstring + one
``assert``-style doctest, with NO ``def`` line and NO function signature:
a triple-quoted docstring containing "Write a function to find the shared elements..." followed
by a single ``assert similar_elements(...) == ...`` doctest-style line, and nothing else.
Fed directly to a completion model, this prompt gives no signal at all about the entry point's
name or parameters — the model would have to invent both, and ``entry_point`` would then not
match. Rather than scope Phase C to HumanEval only (which docs/07 explicitly permits), this
module extracts a **signature scaffold**: every line of ``task.reference_solution`` up to and
including the first line that, stripped, starts with ``"def "`` and ends with ``":"`` — which
also naturally captures any ``import``/setup lines the reference places before the ``def`` (e.g.
Mbpp/4's ``import heapq as hq``), so the model isn't asked to guess a needed import that the
reference itself declares. Verified this finds a matching line for all 378/378 MBPP+ tasks
(``2026-08-15``) — no task falls back to "unsupported."

``code_prefix`` for MBPP is that scaffold (not empty). **The sampler records ``code_prefix`` on
every sample; the scorer reads it back rather than re-deriving it from ``reference_solution`` at
score time** — recomputing it independently would let a sampler/scorer skew (e.g. a future edit
to this function) silently mis-score every MBPP sample without either script noticing.

Design consequence carried over from docs/07 (§"Design consequence"): HumanEval remains the
recommended ``--dataset`` for the overnight Phase C run — MBPP's ~3 visible tests are already
flagged there as too coarse for a meaningful *mutation* score, and the same "too few visible
tests to see a gap against" concern plausibly applies to the hacking-probe gap metric too. MBPP
support exists and is scored identically either way; this is a recommendation for the default
invocation, not a restriction enforced in code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from rlvr.data import DatasetName, Task

__all__ = [
    "Generator",
    "MlxGenerator",
    "PromptSpec",
    "build_prompt",
    "derive_seed",
    "expected_body_indent",
    "repair_first_line_indent",
    "truncate_completion",
]


# --------------------------------------------------------------------------
# backend protocol
# --------------------------------------------------------------------------


class Generator(Protocol):
    """Narrow backend interface. Implement this for a new backend (e.g. a hosted API in Phase D)
    without touching any caller in this module or in scripts/run_phase_c_sample.py."""

    def generate(self, prompt: str, *, max_tokens: int, temperature: float, seed: int) -> str: ...


class MlxGenerator:
    """MLX-backed :class:`Generator`. See module docstring for the seeding/reproducibility
    contract and the falsifier result that selected the default model id."""

    def __init__(self, model_id: str):
        from mlx_lm import load  # lazy — see module docstring

        self.model_id = model_id
        self._model, self._tokenizer = load(model_id)

    def generate(self, prompt: str, *, max_tokens: int, temperature: float, seed: int) -> str:
        import mlx.core as mx
        from mlx_lm import generate as _mlx_generate
        from mlx_lm.sample_utils import make_sampler

        # Mutates MLX's global RNG state — see module docstring's "Seeding and reproducibility".
        mx.random.seed(seed)
        sampler = make_sampler(temp=temperature)
        return _mlx_generate(
            self._model,
            self._tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=sampler,
            verbose=False,
        )


def derive_seed(base_seed: int, task_id: str, sample_idx: int) -> int:
    """Deterministic per-sample seed: ``base_seed XOR sha256(f"{task_id}:{sample_idx}")[:8]``.

    Stable across processes/runs/interpreter invocations (unlike Python's built-in ``hash()``,
    randomized per-process unless ``PYTHONHASHSEED`` is pinned) — a resumed sampling run derives
    the identical seed for the identical (task_id, sample_idx) it's filling in, regardless of
    what order the missing pairs are requested in.
    """
    digest = hashlib.sha256(f"{task_id}:{sample_idx}".encode()).digest()
    offset = int.from_bytes(digest[:8], "big")
    return base_seed ^ offset


# --------------------------------------------------------------------------
# completion post-processing
# --------------------------------------------------------------------------


def expected_body_indent(task: Task, spec: PromptSpec) -> int:
    """Indentation width (leading space/tab count) of the reference solution's own first body
    line, past ``spec.code_prefix``. See the module docstring's "first-line indent repair"
    section — this is dataset-uniform for HumanEval (always 4) but NOT for MBPP (varies per
    task, e.g. 2 for ``Mbpp/2``, 4 for ``Mbpp/3``), so it is computed per-task from the
    reference solution rather than hardcoded.
    """
    remainder = task.reference_solution[len(spec.code_prefix) :]
    for line in remainder.split("\n"):
        if line.strip() != "":
            return len(line) - len(line.lstrip(" \t"))
    return 4  # no non-blank body line found (not observed on any real task) — PEP8 fallback


def repair_first_line_indent(raw_completion: str, expected_indent: int) -> str:
    """Pad the completion's first line by EXACTLY the diagnosed artifact amount.

    The verified tokenizer boundary artifact swallows exactly ONE indent space (module
    docstring), so the repair fires only when the first line is exactly one space short
    (``current_indent == expected_indent - 1``). Any other shortfall is a genuine model
    error and must stay broken — an unconditioned pad would silently rescue malformed
    completions and inflate the published baseline (review finding, PR #15). A zero-indent
    first line is likewise left untouched (see module docstring).
    """
    if not raw_completion:
        return raw_completion
    lines = raw_completion.split("\n")
    first = lines[0]
    stripped = first.lstrip(" ")
    current_indent = len(first) - len(stripped)
    if stripped != "" and current_indent == expected_indent - 1 and current_indent > 0:
        lines[0] = " " * expected_indent + stripped
    return "\n".join(lines)


def truncate_completion(text: str) -> str:
    """Truncate a base-model completion at the first non-blank, column-0 line after its first
    line. See the module docstring's "Completion post-processing" section for the full
    rationale (this rule subsumes the standard HumanEval stop-word list) and its one declared
    limitation (no bracket/backslash-continuation tracking).
    """
    lines = text.split("\n")
    if not lines:
        return text
    out = [lines[0]]  # never truncated — continuation of the still-open prompt, see docstring
    for line in lines[1:]:
        if line.strip() == "":
            out.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            break
        out.append(line)
    return "\n".join(out)


# --------------------------------------------------------------------------
# prompt construction
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptSpec:
    """``prompt`` is what's fed to the model. ``code_prefix`` is the text (possibly empty) that
    must be prepended to the model's (truncated) completion before the result is a valid
    ``code`` argument for ``rlvr.env.evaluate_code`` — i.e. the full candidate is
    ``code_prefix + truncate_completion(raw_completion)``, and ``task.prompt + code_prefix +
    truncate_completion(raw_completion)`` is what actually executes. Empty for HumanEval; the
    signature scaffold for MBPP — see module docstring.
    """

    prompt: str
    code_prefix: str
    # True only where the tokenizer boundary artifact can occur: the prompt ends inside a
    # partially-indented region (HumanEval's trailing docstring-close line). MBPP's scaffold
    # ends at column 0 after "def ...():\n" — the artifact CANNOT occur there, so repair is
    # disabled and a short-indented first line stays broken (review finding, PR #15).
    allow_indent_repair: bool = False


def build_prompt(task: Task, dataset: DatasetName) -> PromptSpec | None:
    """Build a completion-style prompt for ``task``. Returns ``None`` if no sensible completion
    prompt could be constructed (MBPP only — see module docstring; not observed on any of the
    378 MBPP+ tasks as of 2026-08-15, but callers must handle it rather than assume it can't
    happen on a future evalplus dataset revision).
    """
    if dataset == "humaneval":
        return PromptSpec(prompt=task.prompt, code_prefix="", allow_indent_repair=True)
    if dataset == "mbpp":
        lines = task.reference_solution.split("\n")
        scaffold_lines: list[str] = []
        found = False
        for line in lines:
            scaffold_lines.append(line)
            stripped = line.strip()
            if stripped.startswith("def ") and stripped.rstrip().endswith(":"):
                found = True
                break
        if not found:
            return None
        scaffold = "\n".join(scaffold_lines)
        if not scaffold.endswith("\n"):
            scaffold += "\n"
        return PromptSpec(prompt=task.prompt + scaffold, code_prefix=scaffold)
    raise ValueError(f"unknown dataset {dataset!r}; expected 'humaneval' or 'mbpp'")
