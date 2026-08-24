"""Tests for rlvr/generate.py and its two consumer scripts (docs/07 Phase C).

No model download here — every test either exercises pure functions (``truncate_completion``,
``derive_seed``, ``build_prompt``) or drives the sampler/scorer pipelines through a fake
:class:`rlvr.generate.Generator`, per the spec's "mock the Generator for pipeline tests" rule.
The scorer-side tests DO use the real sandbox (``rlvr.env.evaluate_code`` against real
HumanEval/0 base/plus suites) — that's fast and deterministic, the same precedent
tests/test_env.py and tests/test_mutation.py already set for "real sandbox, no model."

``scripts/`` is not an installed package (see tests/test_run_calibration.py's identical note) —
the two Phase C scripts are loaded directly by file path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from rlvr.data import load_tasks
from rlvr.env import default_timeout_s, evaluate_code
from rlvr.generate import (
    PromptSpec,
    build_prompt,
    derive_seed,
    expected_body_indent,
    repair_first_line_indent,
    truncate_completion,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sample_mod = _load_script("run_phase_c_sample", REPO_ROOT / "scripts" / "run_phase_c_sample.py")
score_mod = _load_script("run_phase_c_score", REPO_ROOT / "scripts" / "run_phase_c_score.py")


@pytest.fixture(scope="module")
def humaneval_tasks():
    return load_tasks("humaneval")


@pytest.fixture(scope="module")
def mbpp_tasks():
    return load_tasks("mbpp")


# --------------------------------------------------------------------------
# hand-written completion bodies (HumanEval/0 shape: body-only, continues the open `def`)
# --------------------------------------------------------------------------

# A different (O(n^2)) but CORRECT implementation of has_close_elements — same style as
# tests/test_env.py's CORRECT_CODE, duplicated here rather than imported (this test file stays
# independent of tests/test_env.py, same convention scripts/*.py already use for shared helpers).
CORRECT_BODY = """

    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            if abs(numbers[i] - numbers[j]) < threshold:
                return True
    return False
"""

WRONG_BODY = """

    for i in range(len(numbers) - 1):
        if abs(numbers[i] - numbers[i + 1]) < threshold:
            return True
    return False
"""

# Hardcodes the exact answer for each of HumanEval/0's 7 base inputs, garbage default otherwise
# — passes base 100%, fails plus badly. See tests/test_env.py's identical-in-spirit RED
# DEMONSTRATION fixture.
HARDCODE_BODY = """

    if numbers == [1.0, 2.0, 3.9, 4.0, 5.0, 2.2] and threshold == 0.3:
        return True
    if numbers == [1.0, 2.0, 3.9, 4.0, 5.0, 2.2] and threshold == 0.05:
        return False
    if numbers == [1.0, 2.0, 5.9, 4.0, 5.0] and threshold == 0.95:
        return True
    if numbers == [1.0, 2.0, 5.9, 4.0, 5.0] and threshold == 0.8:
        return False
    if numbers == [1.0, 2.0, 3.0, 4.0, 5.0, 2.0] and threshold == 0.1:
        return True
    if numbers == [1.1, 2.2, 3.1, 4.1, 5.1] and threshold == 1.0:
        return True
    if numbers == [1.1, 2.2, 3.1, 4.1, 5.1] and threshold == 0.5:
        return False
    return True
"""


# --------------------------------------------------------------------------
# truncate_completion
# --------------------------------------------------------------------------


class TestTruncateCompletion:
    def test_no_truncation_needed(self):
        text = "\n    return True\n"
        assert truncate_completion(text) == text

    def test_truncates_at_top_level_class(self):
        text = "\n    return True\n\nclass Foo:\n    pass\n"
        out = truncate_completion(text)
        assert "class Foo" not in out
        assert out == "\n    return True\n"

    def test_truncates_at_top_level_def(self):
        text = "\n    return True\n\ndef other_function():\n    pass\n"
        out = truncate_completion(text)
        assert "def other_function" not in out

    def test_truncates_at_if_name_main(self):
        text = '\n    return True\n\nif __name__ == "__main__":\n    print(solve())\n'
        out = truncate_completion(text)
        assert "__main__" not in out

    def test_truncates_at_top_level_print(self):
        text = "\n    return True\n\nprint(has_close_elements([1, 2], 0.1))\n"
        out = truncate_completion(text)
        assert "print(" not in out

    def test_truncates_at_top_level_comment(self):
        text = "\n    return True\n\n# Example usage\n"
        out = truncate_completion(text)
        assert "# Example usage" not in out

    def test_truncates_at_top_level_assert(self):
        text = "\n    return True\n\nassert has_close_elements([1, 2], 0.1) is True\n"
        out = truncate_completion(text)
        assert "assert has_close_elements" not in out

    def test_generic_column0_statement_also_truncates(self):
        """Catch-all rule (spec item: "or a line at column 0 that isn't a continuation") —
        NOT one of the six named keywords, but still column 0, so it still truncates."""
        text = "\n    return True\n\nx = compute_something_unrelated()\n"
        out = truncate_completion(text)
        assert "compute_something_unrelated" not in out
        assert out == "\n    return True\n"

    def test_nested_def_not_truncated(self):
        """The critical case: an indented (nested) def is NOT at column 0 and must survive."""
        text = (
            "\n"
            "    def helper(x):\n"
            "        return x + 1\n"
            "    return helper(5)\n"
        )
        assert truncate_completion(text) == text

    def test_blank_lines_inside_body_preserved(self):
        text = "\n    a = 1\n\n    b = 2\n    return a + b\n"
        assert truncate_completion(text) == text

    def test_first_line_never_truncated_even_at_column_zero(self):
        """The completion's own first line is a continuation of the still-open prompt and must
        never trigger truncation on its own, even if (unusually) it has no leading whitespace."""
        text = "return True\n\nclass Foo:\n    pass\n"
        out = truncate_completion(text)
        assert out.splitlines()[0] == "return True"
        assert "class Foo" not in out

    def test_empty_completion(self):
        assert truncate_completion("") == ""


# --------------------------------------------------------------------------
# expected_body_indent / repair_first_line_indent (found running the real-model smoke test —
# see rlvr/generate.py's module docstring for the tokenizer-boundary root cause)
# --------------------------------------------------------------------------


class TestIndentRepair:
    def test_expected_body_indent_humaneval_is_four(self, humaneval_tasks):
        task = humaneval_tasks["HumanEval/0"]
        spec = build_prompt(task, "humaneval")
        assert expected_body_indent(task, spec) == 4

    def test_expected_body_indent_mbpp_varies_per_task(self, mbpp_tasks):
        # Mbpp/2's reference body is 2-space indented; Mbpp/3's is 4-space indented — a
        # hardcoded constant would be wrong for one of the two.
        two_space_task = mbpp_tasks["Mbpp/2"]
        two_space_spec = build_prompt(two_space_task, "mbpp")
        assert expected_body_indent(two_space_task, two_space_spec) == 2

        four_space_task = mbpp_tasks["Mbpp/3"]
        four_space_spec = build_prompt(four_space_task, "mbpp")
        assert expected_body_indent(four_space_task, four_space_spec) == 4

    def test_repair_pads_short_indent_up_to_target(self):
        raw = "   assert x > 0\n    return x\n"  # 3 spaces on line 1, needs 4
        repaired = repair_first_line_indent(raw, 4)
        assert repaired == "    assert x > 0\n    return x\n"

    def test_repair_is_noop_when_indent_already_sufficient(self):
        raw = "    return x\n"
        assert repair_first_line_indent(raw, 4) == raw

    def test_repair_does_not_touch_zero_indent_first_line(self):
        """A genuinely unindented first line is a different, real failure mode (see module
        docstring) — must NOT be silently rescued by padding."""
        raw = "def other():\n    pass\n"
        assert repair_first_line_indent(raw, 4) == raw

    def test_repair_handles_empty_completion(self):
        assert repair_first_line_indent("", 4) == ""

    def test_repaired_completion_then_compiles(self, humaneval_tasks):
        """End-to-end: the exact bug found in the smoke test — a 3-space first line that fails
        to compile when concatenated with the prompt — is fixed by the repair step."""
        task = humaneval_tasks["HumanEval/4"]  # mean_absolute_deviation
        spec = build_prompt(task, "humaneval")
        broken_raw = (
            "   assert len(numbers) > 0\n"
            "    mean = sum(numbers) / len(numbers)\n"
            "    return sum([abs(n - mean) for n in numbers]) / len(numbers)\n"
        )
        program_before = task.prompt + broken_raw
        with pytest.raises(SyntaxError):
            compile(program_before, "<test>", "exec")

        target = expected_body_indent(task, spec)
        repaired = repair_first_line_indent(broken_raw, target)
        program_after = task.prompt + repaired
        compile(program_after, "<test>", "exec")  # must not raise


# --------------------------------------------------------------------------
# derive_seed
# --------------------------------------------------------------------------


class TestDeriveSeed:
    def test_deterministic(self):
        a = derive_seed(20260814, "HumanEval/0", 3)
        b = derive_seed(20260814, "HumanEval/0", 3)
        assert a == b

    def test_different_task_id_gives_different_seed(self):
        a = derive_seed(20260814, "HumanEval/0", 0)
        b = derive_seed(20260814, "HumanEval/1", 0)
        assert a != b

    def test_different_sample_idx_gives_different_seed(self):
        a = derive_seed(20260814, "HumanEval/0", 0)
        b = derive_seed(20260814, "HumanEval/0", 1)
        assert a != b

    def test_different_base_seed_gives_different_seed(self):
        a = derive_seed(1, "HumanEval/0", 0)
        b = derive_seed(2, "HumanEval/0", 0)
        assert a != b

    def test_accepted_by_mlx_random_seed(self):
        mx = pytest.importorskip("mlx.core")
        seed = derive_seed(20260814, "HumanEval/0", 0)
        mx.random.seed(seed)  # must not raise — see rlvr/generate.py's module docstring


# --------------------------------------------------------------------------
# build_prompt
# --------------------------------------------------------------------------


class TestBuildPrompt:
    def test_humaneval_prompt_is_verbatim_empty_prefix(self, humaneval_tasks):
        task = humaneval_tasks["HumanEval/0"]
        spec = build_prompt(task, "humaneval")
        assert spec == PromptSpec(prompt=task.prompt, code_prefix="", allow_indent_repair=True)

    def test_mbpp_prompt_includes_signature_scaffold(self, mbpp_tasks):
        task = mbpp_tasks["Mbpp/2"]  # similar_elements(test_tup1, test_tup2)
        spec = build_prompt(task, "mbpp")
        assert spec is not None
        assert spec.prompt.startswith(task.prompt)
        assert "def similar_elements(test_tup1, test_tup2):" in spec.code_prefix
        assert spec.prompt.endswith(spec.code_prefix)

    def test_mbpp_scaffold_carries_leading_imports(self, mbpp_tasks):
        """Mbpp/4's reference solution imports heapq before its def line — the scaffold must
        include that import, not just the def line, or the model has no idea what `hq` is."""
        task = mbpp_tasks["Mbpp/4"]
        spec = build_prompt(task, "mbpp")
        assert spec is not None
        assert "import heapq as hq" in spec.code_prefix
        assert "def heap_queue_largest" in spec.code_prefix

    def test_mbpp_code_prefix_plus_completion_composes_valid_program(self, mbpp_tasks):
        task = mbpp_tasks["Mbpp/3"]  # is_not_prime
        spec = build_prompt(task, "mbpp")
        assert spec is not None
        full_code = spec.code_prefix + "\n    return n > 1\n"
        program = task.prompt + full_code
        # Only the scaffold-derived part needs to be executable Python defining entry_point —
        # the docstring in task.prompt is a triple-quoted string, harmless as a leading statement.
        ns: dict = {}
        exec(program, ns)  # noqa: S102 — trusted hand-written test fixture, not untrusted input
        assert callable(ns[task.entry_point])

    def test_build_prompt_unknown_dataset_raises(self, humaneval_tasks):
        with pytest.raises(ValueError):
            build_prompt(humaneval_tasks["HumanEval/0"], "not-a-real-dataset")  # type: ignore[arg-type]

    def test_build_prompt_finds_scaffold_for_every_mbpp_task(self, mbpp_tasks):
        """Verified once already by hand (2026-08-15, see rlvr/generate.py's module docstring);
        pinned here so a future evalplus revision that breaks the assumption fails loudly."""
        failures = [tid for tid, t in mbpp_tasks.items() if build_prompt(t, "mbpp") is None]
        assert failures == []


# --------------------------------------------------------------------------
# sampler resume logic (fake Generator — no model)
# --------------------------------------------------------------------------


class _CountingGenerator:
    """Records every call's seed; always returns the same fixed completion text."""

    def __init__(self, output: str, model_id: str = "fake-counting-model"):
        self.output = output
        self.model_id = model_id
        self.calls: list[int] = []

    def generate(self, prompt: str, *, max_tokens: int, temperature: float, seed: int) -> str:
        self.calls.append(seed)
        return self.output


class _QueueGenerator:
    """Returns canned outputs in call order — used for the FakeGenerator scoring-pipeline test
    below, where each call must return a DIFFERENT completion (correct / wrong / hardcode)."""

    def __init__(self, outputs: list[str], model_id: str = "fake-queue-model"):
        self._outputs = list(outputs)
        self.model_id = model_id
        self.calls: list[dict] = []

    def generate(self, prompt: str, *, max_tokens: int, temperature: float, seed: int) -> str:
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature, "seed": seed})
        return self._outputs.pop(0)


def test_run_sampling_resumes_only_missing_pairs(tmp_path, humaneval_tasks):
    """RESUME (spec requirement): samples.jsonl with 3 of 5 records present → only the missing 2
    get generated, and the file ends up with exactly 5 records, no duplicates."""
    task_id = "HumanEval/0"
    out_dir = tmp_path / "phase-c-sample"
    out_dir.mkdir()
    samples_path = out_dir / "samples.jsonl"
    with open(samples_path, "w") as f:
        for idx in range(3):
            f.write(
                json.dumps(
                    {
                        "task_id": task_id,
                        "sample_idx": idx,
                        "dataset": "humaneval",
                        "prompt_sha256": "preexisting",
                        "code_prefix": "",
                        "raw_completion": "    return True\n",
                        "truncated_completion": "    return True\n",
                        "seed": 0,
                        "model_id": "preexisting-model",
                        "temperature": 0.8,
                        "max_tokens": 16,
                        "duration_s": 0.01,
                    }
                )
                + "\n"
            )

    gen = _CountingGenerator(output="    return False\n")
    summary = sample_mod.run_sampling(
        gen,
        tasks=humaneval_tasks,
        task_ids=[task_id],
        dataset="humaneval",
        k=5,
        seed=1,
        max_tokens=16,
        temperature=0.8,
        out_dir=out_dir,
        log=lambda *_a, **_k: None,
    )

    assert len(gen.calls) == 2  # only idx 3 and 4 were missing
    assert summary["n_written_this_run"] == 2
    lines = [json.loads(l) for l in samples_path.read_text().strip().splitlines()]
    assert len(lines) == 5
    keys = {(r["task_id"], r["sample_idx"]) for r in lines}
    assert keys == {(task_id, i) for i in range(5)}
    # each newly-written record's seed matches derive_seed, not the generator call's own bookkeeping
    new_records = [r for r in lines if r["sample_idx"] in (3, 4)]
    for r in new_records:
        assert r["seed"] == derive_seed(1, task_id, r["sample_idx"])


def test_run_sampling_is_a_noop_when_everything_already_present(tmp_path, humaneval_tasks):
    task_id = "HumanEval/0"
    out_dir = tmp_path / "phase-c-sample-full"
    out_dir.mkdir()
    samples_path = out_dir / "samples.jsonl"
    with open(samples_path, "w") as f:
        for idx in range(2):
            f.write(json.dumps({"task_id": task_id, "sample_idx": idx, "dataset": "humaneval"}) + "\n")

    gen = _CountingGenerator(output="    return False\n")
    sample_mod.run_sampling(
        gen,
        tasks=humaneval_tasks,
        task_ids=[task_id],
        dataset="humaneval",
        k=2,
        seed=1,
        max_tokens=16,
        temperature=0.8,
        out_dir=out_dir,
        log=lambda *_a, **_k: None,
    )
    assert gen.calls == []


# --------------------------------------------------------------------------
# scorer: RED/GREEN demonstration (A2) + resume logic + full pipeline
# --------------------------------------------------------------------------


def test_red_demonstration_gap_metric_zero_if_scored_visible_only(humaneval_tasks):
    """RED: a scorer that only ran the visible suite would call HARDCODE_BODY correct — the
    'gap' it would report is 0/1 = 0%, because visible-only scoring cannot see the extended-suite
    failure at all. GREEN: the real pipeline (base THEN plus, scripts.run_phase_c_score's own
    ``_score_sample``) categorizes it as CATEGORY_GAP — the gap becomes visible."""
    task = humaneval_tasks["HumanEval/0"]

    # RED: visible-only verdict — this is what a base-suite-only scorer would see and stop at.
    base_only = evaluate_code(task, HARDCODE_BODY, "base", timeout_s=default_timeout_s(task.n_base))
    assert base_only.passed is True  # a visible-only scorer reports this as "correct" — the bug

    # GREEN: the real two-suite pipeline.
    row = score_mod._score_sample(task, HARDCODE_BODY, memory_mb=512)
    assert row["category"] == score_mod.CATEGORY_GAP


def test_score_sample_categorizes_correct_and_wrong(humaneval_tasks):
    task = humaneval_tasks["HumanEval/0"]
    correct_row = score_mod._score_sample(task, CORRECT_BODY, memory_mb=512)
    assert correct_row["category"] == score_mod.CATEGORY_BOTH_PASS

    wrong_row = score_mod._score_sample(task, WRONG_BODY, memory_mb=512)
    assert wrong_row["category"] == score_mod.CATEGORY_VISIBLE_FAIL
    # KEY OPTIMIZATION: a visible failure must not have run the plus suite at all.
    assert wrong_row["plus_n_passed"] is None
    assert wrong_row["plus_n_total"] is None


def test_run_scoring_resumes_only_missing_pairs(tmp_path, humaneval_tasks, monkeypatch):
    task_id = "HumanEval/0"
    samples = [
        {"task_id": task_id, "sample_idx": i, "dataset": "humaneval", "code_prefix": "", "truncated_completion": CORRECT_BODY}
        for i in range(5)
    ]
    out_dir = tmp_path / "phase-c-score"
    out_dir.mkdir()
    scores_path = out_dir / "scores.jsonl"
    with open(scores_path, "w") as f:
        for i in range(3):
            f.write(
                json.dumps(
                    {
                        "task_id": task_id,
                        "sample_idx": i,
                        "category": score_mod.CATEGORY_BOTH_PASS,
                        "base_n_passed": 7,
                        "base_n_total": 7,
                        "plus_n_passed": 999,
                        "plus_n_total": 999,
                        "env_error_detail": None,
                    }
                )
                + "\n"
            )

    calls = []
    original = score_mod._score_sample

    def _counting(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(score_mod, "_score_sample", _counting)

    result = score_mod.run_scoring(
        samples,
        tasks=humaneval_tasks,
        out_dir=out_dir,
        k=5,
        seed=1,
        workers=2,
        log=lambda *_a, **_k: None,
    )

    assert len(calls) == 2  # only sample_idx 3 and 4 were missing
    lines = scores_path.read_text().strip().splitlines()
    assert len(lines) == 5
    assert result["n_valid"] == 5


def test_scoring_pipeline_with_fake_generator_gap_metric_counts_exactly_the_hardcode(tmp_path, humaneval_tasks):
    """End-to-end: FakeGenerator emits one known-correct, one wrong, one hardcode-to-visible
    sample for HumanEval/0 → sampled via run_sampling → scored via run_scoring → the gap metric
    must count exactly the hardcode sample, no more, no less."""
    task_id = "HumanEval/0"
    gen = _QueueGenerator(outputs=[CORRECT_BODY, WRONG_BODY, HARDCODE_BODY])

    sample_dir = tmp_path / "sample"
    sample_mod.run_sampling(
        gen,
        tasks=humaneval_tasks,
        task_ids=[task_id],
        dataset="humaneval",
        k=3,
        seed=20260814,
        max_tokens=384,
        temperature=0.8,
        out_dir=sample_dir,
        log=lambda *_a, **_k: None,
    )
    samples = [json.loads(l) for l in (sample_dir / "samples.jsonl").read_text().strip().splitlines()]
    assert len(samples) == 3

    score_dir = tmp_path / "score"
    result = score_mod.run_scoring(
        samples,
        tasks=humaneval_tasks,
        out_dir=score_dir,
        k=3,
        seed=20260814,
        workers=2,
        log=lambda *_a, **_k: None,
    )

    task_summary = next(t for t in result["per_task"] if t["task_id"] == task_id)
    assert task_summary["both_pass"] == 1  # CORRECT_BODY
    assert task_summary["visible_fail"] == 1  # WRONG_BODY
    assert task_summary["gap"] == 1  # HARDCODE_BODY — exactly one, not zero, not more
    assert result["gap_numer"] == 1
    assert result["gap_denom"] == 2  # CORRECT_BODY + HARDCODE_BODY both passed visible
    assert result["gap_rate"]["point"] == pytest.approx(0.5)


class TestReviewRoundTripPR15:
    """Fixes from the PR #15 review: repair conditioning, reduced-k pooling, torn-tail repair."""

    def test_repair_refuses_non_artifact_shortfall(self):
        # The artifact swallows EXACTLY one space; a 2-short first line is a genuine
        # model error and must stay broken (was silently rescued pre-fix).
        raw = "  return True\n    x = 1\n"
        assert repair_first_line_indent(raw, 4) == raw

    def test_repair_still_fires_on_exact_one_space_shortfall(self):
        raw = "   return True\n"
        assert repair_first_line_indent(raw, 4) == "    return True\n"

    def test_mbpp_prompt_spec_disables_repair(self, mbpp_tasks):
        # MBPP's scaffold ends at column 0 — the boundary artifact cannot occur there.
        task = next(iter(mbpp_tasks.values()))
        spec = build_prompt(task, "mbpp")
        assert spec is not None and spec.allow_indent_repair is False

    def test_humaneval_prompt_spec_enables_repair(self, humaneval_tasks):
        task = next(iter(humaneval_tasks.values()))
        spec = build_prompt(task, "humaneval")
        assert spec is not None and spec.allow_indent_repair is True

    def test_torn_trailing_line_is_repaired_then_resumable(self, tmp_path):
        p = tmp_path / "samples.jsonl"
        good = json.dumps({"task_id": "HumanEval/0", "sample_idx": 0, "x": 1})
        p.write_text(good + "\n" + '{"task_id": "HumanEval/0", "sample_i')  # torn tail
        keys = sample_mod._read_existing_keys(p)
        assert keys == {("HumanEval/0", 0)}
        # the torn line is GONE from the file, so a later append can't strand it as
        # interior corruption
        assert p.read_text() == good + "\n"

    def test_interior_corruption_still_fails_loudly(self, tmp_path):
        p = tmp_path / "samples.jsonl"
        good = json.dumps({"task_id": "HumanEval/0", "sample_idx": 0})
        p.write_text("NOT-JSON\n" + good + "\n")
        with pytest.raises(ValueError, match="interior"):
            sample_mod._read_existing_keys(p)

    def test_reduced_k_task_excluded_from_pooled_pass_at_k(self, tmp_path):
        # A task with n_valid < k contributes pass@k_effective, which is a different
        # statistic; it must not be averaged into the pooled pass@k rows (it stays
        # visible per-task and is counted in n_tasks_reduced_k).
        full = score_mod._per_task_summary(
            "T/full",
            [
                {"task_id": "T/full", "sample_idx": i, "category": score_mod.CATEGORY_BOTH_PASS}
                for i in range(4)
            ],
            n_samples_expected=4,
            k=4,
        )
        reduced = score_mod._per_task_summary(
            "T/reduced",
            [{"task_id": "T/reduced", "sample_idx": 0, "category": score_mod.CATEGORY_BOTH_PASS}],
            n_samples_expected=1,
            k=4,
        )
        assert full["k_effective"] == 4 and reduced["k_effective"] == 1
