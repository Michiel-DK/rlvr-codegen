"""Deterministic AST-based mutation testing (docs/07 Phase B).

FALSIFIER RESULT (A1, recorded 2026-08-14): ``mutmut`` (3.7.0, the latest on PyPI at the time
of this check) was inspected as a candidate library for generating a single mutated function
body from a source STRING. It is not cleanly usable that way:

- Its whole-file API (``mutmut.mutation.file_mutation.mutate_file_contents``) parses a file and
  emits ONE combined output file containing every mutant as a separate function plus
  "trampoline" dispatch machinery (a ``mutants_<name>`` dict switched by mutmut's own
  coverage-driven test-runner loop) — the unit of output is "a whole mutated file wired for
  mutmut's own harness", not "one standalone mutated source string per mutant".
- Extracting a single mutant as an isolated runnable snippet would mean reverse-engineering
  private, undocumented internals (``mutmut.mutation.mutators``, ``mutmut.mutation.trampoline*``
  are not part of any public/stable API, not exported from ``mutmut/__init__.py``) and pulling
  in ``libcst`` as a new dependency for what those internals build on.
- ``cosmic-ray`` has the same shape of problem: it is a project/config/database-oriented CLI
  (a ``cosmic-ray.toml`` + a SQLite session file + its own distributed worker/test-runner loop),
  not a "mutate this string" library call.

Conclusion: per docs/07 Phase B's own instruction ("If not, write a small deterministic
AST-based mutator — that is NOT a deviation from docs/07's intent"), this module is a small,
dependency-free (stdlib ``ast`` only — no new dependency added) AST mutator built for exactly
the shape Phase B needs: mutate one reference solution, get back standalone mutant source
strings.

Mutation target (A4, per rlvr/env.py's own composition rule)
--------------------------------------------------------------
``generate_mutants`` takes ``task.reference_solution`` verbatim (never ``task.prompt`` — "mutate
only the solution body, not the prompt scaffolding") and returns mutants whose ``.source`` is a
drop-in replacement for ``task.reference_solution`` — i.e. ``task.prompt + mutant.source`` is
exactly the shape ``rlvr.env.evaluate_code`` expects for its ``code`` argument, the same
composition rule ``rlvr/env.py``'s module docstring documents (A4).

This matters because ``task.reference_solution`` has two different on-the-wire shapes (see
``rlvr/env.py``): HumanEval's is a *body-only* continuation of the prompt's open ``def ...:``
line (not standalone-parseable Python — it starts mid-indentation with no enclosing block);
MBPP's is a *complete* ``def ...:`` block, standalone-parseable on its own. ``generate_mutants``
handles both: it first tries ``ast.parse(source)`` directly (the MBPP shape); if that raises
``SyntaxError`` (the HumanEval shape), it wraps the source in a synthetic
``def __rlvr_mutation_wrapper__():`` header — which, because the HumanEval body always begins
with its own leading newline, turns back into valid Python — mutates inside that wrapped tree,
then strips the wrapper header back off and dedents the body by one level before returning, so
the caller always gets back a body-only replacement for ``task.reference_solution``, regardless
of which shape it started as. The wrapper prefixes text onto an otherwise-empty first line
without inserting any newline, so line numbers recorded on ``Mutant`` are identical whether or
not wrapping happened — no offset correction is needed.

Operators (the "standard set" docs/07 names)
-----------------------------------------------
Each operator below produces one mutant per (mutation site, alternative) pair — e.g. one
``Compare`` node with a single ``<`` produces 5 mutants (one per other relational operator), not
1.

- **relational-operator-replacement** — ``ast.Compare``: each comparison operator (``<`` ``<=``
  ``>`` ``>=`` ``==`` ``!=``) replaced with each of the other five (classic ROR).
- **arithmetic-operator-replacement** — ``ast.BinOp``: each arithmetic operator (``+`` ``-``
  ``*`` ``/`` ``//`` ``%``) replaced with each of the other five.
- **boolean-operator-swap** — ``ast.BoolOp``: ``and`` <-> ``or``.
- **unary-constant-perturbation** — ``ast.Constant``: an ``int`` constant (excluding ``bool``,
  which is an ``int`` subclass and is handled separately) yields two mutants, ``n + 1`` and
  ``n - 1``; a ``bool`` constant yields one mutant, its negation (``True`` <-> ``False``).
- **negate-if-condition** — ``ast.If``: the test expression wrapped in ``not (...)``.
- **off-by-one-slice-bound** — ``ast.Subscript`` whose slice is an ``ast.Slice``: each present
  bound (``lower``/``upper`` — a bound that is syntactically absent, e.g. the missing start of
  ``a[:n]``, is left alone; there is nothing there to perturb) is wrapped as ``(bound + 1)`` and
  ``(bound - 1)`` — two mutants per present bound. This is "syntactically safe" in the sense
  docs/07 asks for: it only ever wraps an *existing* expression, never invents one.

Deduplication and selection
------------------------------
A candidate is discarded if it fails to compile (``compile(..., "exec")``) or renders identical
to the *unmutated* tree's own rendering (comparing against a baseline pass through the same
``ast.unparse`` pipeline, not against the raw input string — ``ast.unparse`` does not
byte-for-byte preserve the original text, so comparing a mutated render against the raw source
would flag almost every real mutant as spuriously "unchanged"). Survivors are deduplicated by
final mutated source text (two different sites can render identically, e.g. mutating either
operand of a commutative ``+`` past its sibling can coincide in rare cases). If more candidates
remain than ``max_mutants``, a ``random.Random(seed)`` picks the subset — deterministic for a
given seed, independent of dict/set iteration order because dedup happens by inserting into an
ordered list guarded by a ``set`` membership check, not by iterating a set/dict directly.
"""

from __future__ import annotations

import ast
import hashlib
import random
from dataclasses import dataclass

__all__ = [
    "Mutant",
    "generate_mutants",
    "CATEGORY_KILLED_BY_VISIBLE",
    "CATEGORY_KILLED_BY_EXTENDED_ONLY",
    "CATEGORY_SURVIVED_BOTH",
    "categorize",
    "is_killed_by_extended",
]

_WRAPPER_NAME = "__rlvr_mutation_wrapper__"

_REL_CLASSES: tuple[type[ast.cmpop], ...] = (
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Eq,
    ast.NotEq,
)
_ARITH_CLASSES: tuple[type[ast.operator], ...] = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
)


@dataclass(frozen=True)
class Mutant:
    """One mutated version of a reference solution.

    ``source`` is a drop-in replacement for the ``task.reference_solution`` that produced it —
    see the module docstring's "Mutation target" section. ``line``/``col`` are 1-indexed /
    0-indexed per Python's own ``ast`` convention, and refer to the position in the ORIGINAL
    (unwrapped) source that was passed to :func:`generate_mutants`.
    """

    mutant_id: str
    source: str
    operator: str
    line: int
    col: int


# --------------------------------------------------------------------------
# parsing / rendering — handles both reference_solution shapes (see module docstring)
# --------------------------------------------------------------------------


def _parse_solution(source: str) -> tuple[ast.Module, bool]:
    """Parse ``source`` either standalone (MBPP shape) or wrapped (HumanEval shape).

    Returns ``(tree, wrapped)``. ``wrapped`` is True when a synthetic
    ``def __rlvr_mutation_wrapper__():`` header was needed to make ``source`` parseable at all
    — see the module docstring.
    """
    try:
        return ast.parse(source), False
    except SyntaxError:
        pass
    wrapped_source = f"def {_WRAPPER_NAME}():{source}"
    try:
        return ast.parse(wrapped_source), True
    except SyntaxError as e:
        raise ValueError(
            "could not parse reference solution as standalone code (MBPP shape) or as a "
            f"wrapped function body (HumanEval shape): {e}"
        ) from e


def _snapshot(tree: ast.Module, wrapped: bool) -> tuple[str, str]:
    """Render ``tree`` in its current (possibly temporarily mutated) state.

    Returns ``(full_text, mutant_source)``:

    - ``full_text`` is ``ast.unparse(tree)`` as-is — ALWAYS standalone-parseable Python (with
      the synthetic wrapper header still attached, if ``wrapped``), so it is what gets fed to
      the syntax-validity check in :func:`generate_mutants`.
    - ``mutant_source`` is what actually gets returned to the caller as ``Mutant.source``: for
      the non-wrapped (MBPP) case it's identical to ``full_text``; for the wrapped (HumanEval)
      case the synthetic header LINE is dropped and nothing else is touched — the body's
      indentation is left exactly as ``ast.unparse`` produced it (always one level, i.e. 4
      spaces, deep for a function body) because that is exactly the indentation a body-only
      ``reference_solution`` replacement needs: the real prompt's own ``def ...:`` line expects
      its continuation body at that same depth, and the wrapper def and the real def are both
      single-level nestings — see the module docstring's "Mutation target" section.
    """
    full_text = ast.unparse(tree)
    if not wrapped:
        return full_text, full_text
    header, _, rest = full_text.partition("\n")
    assert header == f"def {_WRAPPER_NAME}():", (
        f"internal invariant violation: expected wrapper header, got {header!r}"
    )
    return full_text, rest


# --------------------------------------------------------------------------
# candidate generation — mutate one field in place, render, restore
# --------------------------------------------------------------------------


def _rel_alternatives(op: ast.cmpop) -> list[ast.cmpop]:
    return [cls() for cls in _REL_CLASSES if not isinstance(op, cls)]


def _arith_alternatives(op: ast.operator) -> list[ast.operator]:
    return [cls() for cls in _ARITH_CLASSES if not isinstance(op, cls)]


def _candidates(tree: ast.Module, wrapped: bool) -> list[tuple[str, int, int, str, str]]:
    """(operator_name, line, col, full_text, mutant_source) for every mutation site x alternative.

    Every candidate is produced by mutating exactly one field of one node IN PLACE on the
    shared ``tree``, rendering, then restoring the original value before moving on — no tree
    copies are needed because at most one leaf field differs from the pristine tree at any
    instant. See :func:`_snapshot` for what ``full_text`` vs ``mutant_source`` mean.
    """
    out: list[tuple[str, int, int, str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                for alt in _rel_alternatives(op):
                    old = node.ops[i]
                    node.ops[i] = alt
                    full, mutant = _snapshot(tree, wrapped)
                    out.append(("relational-operator-replacement", node.lineno, node.col_offset, full, mutant))
                    node.ops[i] = old

        elif isinstance(node, ast.BinOp) and isinstance(node.op, _ARITH_CLASSES):
            old = node.op
            for alt in _arith_alternatives(old):
                node.op = alt
                full, mutant = _snapshot(tree, wrapped)
                out.append(("arithmetic-operator-replacement", node.lineno, node.col_offset, full, mutant))
            node.op = old

        elif isinstance(node, ast.BoolOp):
            old = node.op
            node.op = ast.Or() if isinstance(old, ast.And) else ast.And()
            full, mutant = _snapshot(tree, wrapped)
            out.append(("boolean-operator-swap", node.lineno, node.col_offset, full, mutant))
            node.op = old

        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                old_val = node.value
                node.value = not old_val
                full, mutant = _snapshot(tree, wrapped)
                out.append(("unary-constant-perturbation", node.lineno, node.col_offset, full, mutant))
                node.value = old_val
            elif isinstance(node.value, int):
                old_val = node.value
                for delta in (1, -1):
                    node.value = old_val + delta
                    full, mutant = _snapshot(tree, wrapped)
                    out.append(("unary-constant-perturbation", node.lineno, node.col_offset, full, mutant))
                node.value = old_val

        elif isinstance(node, ast.If):
            old_test = node.test
            negated = ast.UnaryOp(op=ast.Not(), operand=old_test)
            ast.copy_location(negated, old_test)
            ast.fix_missing_locations(negated)
            node.test = negated
            full, mutant = _snapshot(tree, wrapped)
            out.append(("negate-if-condition", node.lineno, node.col_offset, full, mutant))
            node.test = old_test

        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            sl = node.slice
            for bound_name in ("lower", "upper"):
                old_bound = getattr(sl, bound_name)
                if old_bound is None:
                    continue  # syntactically absent bound — nothing to perturb, see docstring
                for delta, op_cls in ((1, ast.Add), (-1, ast.Sub)):
                    new_bound = ast.BinOp(left=old_bound, op=op_cls(), right=ast.Constant(value=1))
                    ast.copy_location(new_bound, old_bound)
                    ast.fix_missing_locations(new_bound)
                    setattr(sl, bound_name, new_bound)
                    full, mutant = _snapshot(tree, wrapped)
                    out.append(("off-by-one-slice-bound", node.lineno, node.col_offset, full, mutant))
                    setattr(sl, bound_name, old_bound)

    return out


def _mutant_id(operator: str, line: int, col: int, mutated_source: str) -> str:
    """Stable hash: same (operator, location, resulting source) always yields the same id,
    across runs and independent of ``seed`` or ``max_mutants`` (a survivor's identity does not
    depend on who else survived selection)."""
    digest = hashlib.sha256(f"{operator}|{line}|{col}|{mutated_source}".encode()).hexdigest()
    return digest[:12]


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------


def generate_mutants(source: str, *, seed: int, max_mutants: int) -> list[Mutant]:
    """Generate deterministic mutants of a reference solution's source.

    ``source`` is ``task.reference_solution`` (never ``task.prompt`` — see module docstring).
    Returns at most ``max_mutants`` :class:`Mutant`, sorted by ``(line, col, operator,
    mutant_id)`` for stable, readable output. Deterministic: the same ``(source, seed,
    max_mutants)`` always yields the identical list, in the identical order.

    Raises ``ValueError`` if ``source`` cannot be parsed at all (neither standalone nor
    wrapped — see :func:`_parse_solution`).
    """
    tree, wrapped = _parse_solution(source)
    _, baseline_mutant = _snapshot(tree, wrapped)

    seen_sources: set[str] = set()
    candidates: list[Mutant] = []
    for operator, line, col, full_text, mutant_source in _candidates(tree, wrapped):
        if mutant_source == baseline_mutant:
            continue  # no-op mutation (e.g. would require special-casing to occur; kept as a
            # defensive guard rather than assumed impossible)
        if mutant_source in seen_sources:
            continue  # dedupe by final mutated source (docs/07 spec)
        try:
            # Compile-check `full_text`, not `mutant_source`: for the HumanEval (wrapped) shape
            # `mutant_source` is deliberately body-only and NOT standalone-parseable on its own
            # (same as the real `task.reference_solution` it replaces) — `full_text` still
            # carries the synthetic wrapper header, so it's always standalone-checkable
            # regardless of shape. See `_snapshot`.
            compile(full_text, "<mutant>", "exec")
        except SyntaxError:
            continue
        seen_sources.add(mutant_source)
        candidates.append(
            Mutant(
                mutant_id=_mutant_id(operator, line, col, mutant_source),
                source=mutant_source,
                operator=operator,
                line=line,
                col=col,
            )
        )

    if len(candidates) > max_mutants:
        rng = random.Random(seed)
        candidates = rng.sample(candidates, max_mutants)

    candidates.sort(key=lambda m: (m.line, m.col, m.operator, m.mutant_id))
    return candidates


# --------------------------------------------------------------------------
# categorization — shared by scripts/run_mutation_audit.py and tests/test_mutation.py
# --------------------------------------------------------------------------

# A mutant's category, given its pass/fail verdict against the base (visible) suite and the
# plus (extended) suite. ``env_error`` (a ReferenceExecutionError/sandbox_error on either suite)
# is deliberately NOT one of these three — it is excluded from the categories that feed the
# mutation-score denominators and is tracked separately, per docs/07 discipline that an
# environment defect must be loud rather than folded into a verdict it isn't.
CATEGORY_KILLED_BY_VISIBLE = "killed_by_visible"
CATEGORY_KILLED_BY_EXTENDED_ONLY = "killed_by_extended_only"
CATEGORY_SURVIVED_BOTH = "survived_both"


def categorize(passed_base: bool, passed_plus: bool) -> str:
    """Categorize one mutant from its verdict on the base and plus suites.

    KEY OPTIMIZATION this enables (see scripts/run_mutation_audit.py): the extended suite is a
    strict superset of the visible suite (``plus_inputs`` are *additional* inputs, not a
    replacement — see rlvr/data.py), so ``killed_by_visible`` already implies "would also be
    killed by extended" WITHOUT needing to run the plus suite at all — only mutants that survive
    the base suite need a plus-suite run to tell ``killed_by_extended_only`` apart from
    ``survived_both``. A caller can therefore pass ``passed_plus=True`` (or skip the plus run
    entirely and treat it as passing) for any mutant that already failed the base suite, and
    still get the correct category from this function — it only inspects ``passed_plus`` when
    ``passed_base`` is True.
    """
    if not passed_base:
        return CATEGORY_KILLED_BY_VISIBLE
    if not passed_plus:
        return CATEGORY_KILLED_BY_EXTENDED_ONLY
    return CATEGORY_SURVIVED_BOTH


def is_killed_by_extended(category: str) -> bool:
    """Whether a mutant counts as "killed" in the extended-suite mutation score.

    Pins the identity docs/07's KEY OPTIMIZATION depends on: ``killed_by_visible`` counts as
    killed in the extended score too (extended ⊇ visible), not just ``killed_by_extended_only``.
    """
    return category in (CATEGORY_KILLED_BY_VISIBLE, CATEGORY_KILLED_BY_EXTENDED_ONLY)
