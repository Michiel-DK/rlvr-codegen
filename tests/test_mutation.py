"""Tests for rlvr/mutation.py — the AST mutator and mutation-category logic (docs/07 Phase B).

Uses a handful of real HumanEval/MBPP tasks for the sandbox-backed tests (the RED demonstration
and the "trivially-broken mutant" test genuinely run candidates through
``rlvr.env.evaluate_code``, i.e. through the real subprocess sandbox) and small hand-written
source strings for the pure-AST tests (operator-site coverage, determinism, dedup, selection).
"""

from __future__ import annotations

import ast

from pathlib import Path

import pytest

from rlvr.data import load_tasks
from rlvr.env import default_timeout_s, evaluate_code
from rlvr.mutation import (
    CATEGORY_KILLED_BY_EXTENDED_ONLY,
    CATEGORY_KILLED_BY_VISIBLE,
    CATEGORY_SURVIVED_BOTH,
    categorize,
    generate_mutants,
    is_killed_by_extended,
)

# --------------------------------------------------------------------------
# fixtures — real tasks, loaded once
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def humaneval_tasks():
    return load_tasks("humaneval")


@pytest.fixture(scope="module")
def mbpp_tasks():
    return load_tasks("mbpp")


# A small, standalone-parseable (MBPP-shaped) function exercising every operator this module
# supports, in one source string, so the operator-site tests don't depend on real dataset
# contents changing under us.
_KNOWN_SOURCE = """\
def f(xs, i, n):
    if xs[i] < n:
        return True
    total = 1 + 2
    ok = True and False
    y = xs[i + 1]
    z = xs[1:n]
    return ok
"""


# --------------------------------------------------------------------------
# operator-site coverage
# --------------------------------------------------------------------------


def test_known_source_finds_expected_operator_sites():
    mutants = generate_mutants(_KNOWN_SOURCE, seed=1, max_mutants=1000)
    operators_found = {m.operator for m in mutants}
    assert operators_found == {
        "relational-operator-replacement",
        "arithmetic-operator-replacement",
        "boolean-operator-swap",
        "unary-constant-perturbation",
        "negate-if-condition",
        "off-by-one-slice-bound",
    }

    # relational: `xs[i] < n` — Lt against the other 5 relational ops = 5 mutants
    rel = [m for m in mutants if m.operator == "relational-operator-replacement"]
    assert len(rel) == 5

    # arithmetic: `1 + 2` (Add) and `i + 1` (Add) — 2 sites x 5 alternatives = 10 mutants
    arith = [m for m in mutants if m.operator == "arithmetic-operator-replacement"]
    assert len(arith) == 10

    # boolean: `True and False` — And -> Or = 1 mutant
    boolean = [m for m in mutants if m.operator == "boolean-operator-swap"]
    assert len(boolean) == 1

    # negate-if: one `if` statement = 1 mutant
    negate_if = [m for m in mutants if m.operator == "negate-if-condition"]
    assert len(negate_if) == 1

    # off-by-one slice bound: `xs[1:n]` has both lower=1 and upper=n present,
    # 2 bounds x 2 deltas (+1/-1) = 4 mutants
    slice_mutants = [m for m in mutants if m.operator == "off-by-one-slice-bound"]
    assert len(slice_mutants) == 4

    # unary/constant: `True`/`False` inside the BoolOp (2 bool constants), plus int constants
    # 1, 2, 1 (slice lower), i.e. three distinct int-constant sites (2 mutants each) — plus the
    # 2 bool constants (1 mutant each). Exact count isn't the point; just confirm it's nonzero
    # and every one is a real, distinct mutation.
    const_mutants = [m for m in mutants if m.operator == "unary-constant-perturbation"]
    assert len(const_mutants) > 0


def test_relational_operator_replacement_produces_all_five_alternatives():
    mutants = generate_mutants(_KNOWN_SOURCE, seed=1, max_mutants=1000)
    rel_sources = {m.source for m in mutants if m.operator == "relational-operator-replacement"}
    expected_ops = ["<=", ">", ">=", "==", "!="]
    for op in expected_ops:
        assert any(f"xs[i] {op} n" in src for src in rel_sources), (op, rel_sources)


def test_off_by_one_skips_absent_slice_bounds():
    """`a[:]` has both bounds syntactically absent — nothing to perturb, no mutant produced."""
    source = "def f(xs):\n    return xs[:]\n"
    mutants = generate_mutants(source, seed=1, max_mutants=1000)
    assert [m for m in mutants if m.operator == "off-by-one-slice-bound"] == []


def test_bool_constant_and_int_constant_are_not_conflated():
    """`True`/`False` (an int subclass in Python) must be negated, not incremented."""
    source = "def f():\n    return True\n"
    mutants = generate_mutants(source, seed=1, max_mutants=1000)
    const = [m for m in mutants if m.operator == "unary-constant-perturbation"]
    assert len(const) == 1
    assert "False" in const[0].source


# --------------------------------------------------------------------------
# determinism, compilation, dedup, selection
# --------------------------------------------------------------------------


def test_determinism_same_seed_identical_list():
    a = generate_mutants(_KNOWN_SOURCE, seed=42, max_mutants=5)
    b = generate_mutants(_KNOWN_SOURCE, seed=42, max_mutants=5)
    assert [m.mutant_id for m in a] == [m.mutant_id for m in b]
    assert [m.source for m in a] == [m.source for m in b]


def test_different_seeds_can_select_different_subsets():
    a = generate_mutants(_KNOWN_SOURCE, seed=1, max_mutants=3)
    b = generate_mutants(_KNOWN_SOURCE, seed=2, max_mutants=3)
    # Not a hard guarantee for arbitrary seeds in general, but true for these two on this
    # fixture — pins that `seed` actually participates in selection, not just plumbing.
    assert {m.mutant_id for m in a} != {m.mutant_id for m in b}


def test_all_mutants_compile_when_recomposed_with_a_real_prompt(humaneval_tasks, mbpp_tasks):
    he_task = humaneval_tasks["HumanEval/0"]
    mutants = generate_mutants(he_task.reference_solution, seed=20260814, max_mutants=50)
    assert mutants, "expected at least one mutant for HumanEval/0"
    for m in mutants:
        compile(he_task.prompt + m.source, "<mutant>", "exec")  # must not raise

    mbpp_task = mbpp_tasks["Mbpp/3"]
    mutants = generate_mutants(mbpp_task.reference_solution, seed=20260814, max_mutants=50)
    assert mutants, "expected at least one mutant for Mbpp/3"
    for m in mutants:
        compile(mbpp_task.prompt + m.source, "<mutant>", "exec")  # must not raise


def test_no_duplicate_mutant_sources():
    mutants = generate_mutants(_KNOWN_SOURCE, seed=1, max_mutants=1000)
    sources = [m.source for m in mutants]
    assert len(sources) == len(set(sources))


def test_max_mutants_respected_via_seeded_selection():
    all_mutants = generate_mutants(_KNOWN_SOURCE, seed=7, max_mutants=1000)
    assert len(all_mutants) > 5  # fixture must actually have more candidates than the cap below

    capped = generate_mutants(_KNOWN_SOURCE, seed=7, max_mutants=5)
    assert len(capped) == 5
    # every selected mutant is a real candidate from the uncapped set (selection, not invention)
    all_ids = {m.mutant_id for m in all_mutants}
    assert {m.mutant_id for m in capped} <= all_ids


def test_generated_mutant_sources_all_differ_from_original():
    mutants = generate_mutants(_KNOWN_SOURCE, seed=1, max_mutants=1000)
    for m in mutants:
        assert m.source != _KNOWN_SOURCE


def test_mutant_id_stable_hash_independent_of_other_survivors():
    """A mutant's id must not depend on max_mutants/selection — same (operator, location,
    resulting source) always yields the same id, whether or not it happened to be selected
    alongside a different set of other mutants."""
    small = {m.mutant_id: m.source for m in generate_mutants(_KNOWN_SOURCE, seed=1, max_mutants=3)}
    large = {m.mutant_id: m.source for m in generate_mutants(_KNOWN_SOURCE, seed=1, max_mutants=1000)}
    for mutant_id, source in small.items():
        assert large[mutant_id] == source


# --------------------------------------------------------------------------
# categorize() / is_killed_by_extended() — pure logic
# --------------------------------------------------------------------------


def test_categorize_killed_by_visible():
    assert categorize(passed_base=False, passed_plus=True) == CATEGORY_KILLED_BY_VISIBLE
    assert categorize(passed_base=False, passed_plus=False) == CATEGORY_KILLED_BY_VISIBLE


def test_categorize_killed_by_extended_only():
    assert categorize(passed_base=True, passed_plus=False) == CATEGORY_KILLED_BY_EXTENDED_ONLY


def test_categorize_survived_both():
    assert categorize(passed_base=True, passed_plus=True) == CATEGORY_SURVIVED_BOTH


def test_is_killed_by_extended_identity_pinned():
    """The identity docs/07's KEY OPTIMIZATION depends on: killed_by_visible ⇒ counted killed
    in the extended score too (extended ⊇ visible), not just killed_by_extended_only."""
    assert is_killed_by_extended(CATEGORY_KILLED_BY_VISIBLE) is True
    assert is_killed_by_extended(CATEGORY_KILLED_BY_EXTENDED_ONLY) is True
    assert is_killed_by_extended(CATEGORY_SURVIVED_BOTH) is False


# --------------------------------------------------------------------------
# trivially-broken mutant -> killed_by_visible (real sandbox)
# --------------------------------------------------------------------------


def test_trivially_broken_mutant_is_killed_by_visible(humaneval_tasks):
    task = humaneval_tasks["HumanEval/0"]
    broken_code = "\n\n    return None\n"  # always wrong — base suite alone must catch this
    base = evaluate_code(task, broken_code, "base", timeout_s=default_timeout_s(task.n_base))
    assert base.passed is False
    assert categorize(passed_base=base.passed, passed_plus=True) == CATEGORY_KILLED_BY_VISIBLE


# --------------------------------------------------------------------------
# RED DEMONSTRATION (A2) — the canonical verifier-gap case
# --------------------------------------------------------------------------


def test_red_demonstration_verifier_gap_on_humaneval_0(humaneval_tasks):
    """The canonical docs/07 case: a mutant that PASSES every visible (base) test and FAILS an
    extended (plus) test — this is exactly the "reward doesn't certify correctness" gap the
    whole Phase B audit measures, and it pins that `categorize` assigns it
    `killed_by_extended_only`, never `killed_by_visible`.

    This mutant is not hand-crafted: `<` -> `<=` in HumanEval/0's
    ``sorted_numbers[i + 1] - sorted_numbers[i] < threshold`` boundary check is generated by
    `generate_mutants` itself (relational-operator-replacement) with seed=20260814. It passes
    all 7 base inputs and fails 6/999 plus inputs — a real, reproducible near-boundary case, not
    a synthetic stand-in.
    """
    task = humaneval_tasks["HumanEval/0"]
    mutants = generate_mutants(task.reference_solution, seed=20260814, max_mutants=200)

    target = next(
        (
            m
            for m in mutants
            if m.operator == "relational-operator-replacement"
            and "<= threshold" in m.source
        ),
        None,
    )
    assert target is not None, (
        "expected generate_mutants to produce the `<` -> `<=` mutant on HumanEval/0's threshold "
        "check at seed=20260814 — if this ever stops being generated (e.g. after an operator "
        "change), hand-craft the mutant source here instead, per docs/07 Phase B's instruction"
    )

    base_result = evaluate_code(task, target.source, "base", timeout_s=default_timeout_s(task.n_base))
    plus_result = evaluate_code(task, target.source, "plus", timeout_s=default_timeout_s(task.n_plus))

    # Pin the actual verdicts this whole demonstration rests on.
    assert base_result.passed is True, "mutant must pass every visible test for the gap to exist"
    assert plus_result.passed is False, "mutant must fail at least one extended test"
    assert plus_result.n_passed < plus_result.n_total

    category = categorize(passed_base=base_result.passed, passed_plus=plus_result.passed)

    # RED: naive visible-only scoring would (wrongly) call this mutant "killed_by_visible" —
    # demonstrate that assertion is false before showing the correct one.
    with pytest.raises(AssertionError):
        assert category == CATEGORY_KILLED_BY_VISIBLE

    # GREEN: the correct category — this is the verifier gap docs/07 is about.
    assert category == CATEGORY_KILLED_BY_EXTENDED_ONLY
    assert is_killed_by_extended(category) is True  # still counts as "killed" in the extended score


# --------------------------------------------------------------------------
# parsing edge cases
# --------------------------------------------------------------------------


def test_unparseable_source_raises_value_error():
    with pytest.raises(ValueError):
        generate_mutants("def f(:\n    this is not python\n", seed=1, max_mutants=10)


def test_humaneval_shape_body_only_source_is_handled(humaneval_tasks):
    """HumanEval's reference_solution is a body-only continuation of the prompt's `def` line —
    not standalone-parseable on its own. generate_mutants must handle it via the wrapper path
    (see module docstring) rather than raising."""
    task = humaneval_tasks["HumanEval/0"]
    with pytest.raises(SyntaxError):
        ast.parse(task.reference_solution)  # confirms the fixture actually needs the wrapper path
    mutants = generate_mutants(task.reference_solution, seed=1, max_mutants=10)
    assert mutants  # did not raise, and found real mutation sites


def test_pooled_gap_equals_row_difference_in_manifest(tmp_path):
    """Review finding (PR #13): the GAP row was a task-weighted mean under two
    mutant-pooled rows — a reader subtracting the rows got a different number.
    The manifest now records gap_pooled, and it must equal extended − visible
    exactly; the task-mean gap remains as its own separately-labeled statistic."""
    import json
    import subprocess
    import sys

    out = tmp_path / "audit"
    r = subprocess.run(
        [
            sys.executable,
            "scripts/run_mutation_audit.py",
            "--dataset", "humaneval",
            "--limit", "5",
            "--max-mutants-per-task", "4",
            "--out", str(out),
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parent.parent,
        timeout=600,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    m = json.loads((out / "manifest.json").read_text())["metrics"]
    vis, ext = m["mutation_score_visible"]["point"], m["mutation_score_extended"]["point"]
    assert m["gap_pooled"] == pytest.approx(ext - vis, abs=1e-12)
    results = (out / "results.md").read_text()
    assert "GAP, pooled" in results and "GAP, mean per-task" in results
    assert "anti-conservative" in results  # the Wilson pooling caveat


def test_exclude_tasks_flag_removes_and_records(tmp_path):
    """--exclude-tasks drops env-limited tasks from the sweep and records the
    exclusion in the manifest config; unknown ids fail loudly."""
    import json
    import subprocess
    import sys

    repo = Path(__file__).resolve().parent.parent
    out = tmp_path / "audit-excl"
    r = subprocess.run(
        [
            sys.executable, "scripts/run_mutation_audit.py",
            "--dataset", "humaneval", "--limit", "5", "--max-mutants-per-task", "2",
            "--exclude-tasks", "HumanEval/2",
            "--out", str(out),
        ],
        capture_output=True, text=True, cwd=repo, timeout=600,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    m = json.loads((out / "manifest.json").read_text())
    assert m["config"]["excluded_tasks_env_limited"] == ["HumanEval/2"]
    assert m["metrics"]["n_tasks"] == 4
    assert "HumanEval/2" not in m["predictions"]

    r_bad = subprocess.run(
        [
            sys.executable, "scripts/run_mutation_audit.py",
            "--dataset", "humaneval", "--limit", "5", "--max-mutants-per-task", "2",
            "--exclude-tasks", "HumanEval/9999",
            "--out", str(tmp_path / "never"),
        ],
        capture_output=True, text=True, cwd=repo, timeout=600,
    )
    assert r_bad.returncode != 0
    assert "unknown" in (r_bad.stderr + r_bad.stdout)
