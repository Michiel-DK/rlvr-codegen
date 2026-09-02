"""Render docs/img/verifier-gap.png, the README hero chart.

Numbers are copied from the committed results tables (no recomputation here):

- Phase B, mutation-score gap (extended − visible), mean per task, 95% task-resampled
  bootstrap CI: results/phase-b-2026-08-14/results-humaneval.md line 13,
  results/phase-b-2026-08-14/results-mbpp.md line 13. Pooled gaps (+3.6 / +6.4) from
  line 12 of the same files.
- Phase C, gap rate among visible-passing completions of the untrained
  Qwen2.5-Coder-1.5B (k=10), 95% Wilson CI:
  results/phase-c-2026-08-15/results-humaneval-heldout-k10.md line 13,
  results/phase-c-2026-08-15/results-mbpp-heldout-k10.md line 13.

Both series are summarised in docs/08-results-verifier-adequacy.md (tables at lines
25-28 and 49-54). The two instruments measure different populations; docs/08 rules the
comparison "a caution, not a multiplier", so the chart shows them side by side, not as
a ratio.

    python scripts/make_readme_chart.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "verifier-gap.png"

DATASETS = ["HumanEval", "MBPP"]
# (point, ci_low, ci_high), all in percentage points
MUTATION_GAP_TASK_MEAN = [(3.2, 2.2, 4.3), (5.7, 4.3, 7.2)]
MUTATION_GAP_POOLED = [3.6, 6.4]
MODEL_GAP_RATE = [(12.2, 7.5, 19.1), (17.8, 12.7, 24.4)]
MODEL_GAP_N = [123, 163]


def main() -> None:
    bg, fg, grid = "#f4f5f7", "#1f2937", "#d1d5db"
    c_mut, c_model = "#8a97a6", "#2f4a63"

    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=130)
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(bg)

    w = 0.36
    xs = [0, 1]
    for i, (x, mut, model) in enumerate(zip(xs, MUTATION_GAP_TASK_MEAN, MODEL_GAP_RATE)):
        ax.bar(x - w / 2, mut[0], w, color=c_mut,
               yerr=[[mut[0] - mut[1]], [mut[2] - mut[0]]], capsize=4,
               error_kw={"ecolor": fg, "elinewidth": 1.2},
               label="mutation-score gap: extended − visible suite\n(task-mean, 95% bootstrap CI; no model involved)" if i == 0 else None)
        ax.bar(x + w / 2, model[0], w, color=c_model,
               yerr=[[model[0] - model[1]], [model[2] - model[0]]], capsize=4,
               error_kw={"ecolor": fg, "elinewidth": 1.2},
               label="untrained Qwen2.5-Coder-1.5B, k=10: visible-passing\ncompletions that fail the extended suite (95% Wilson CI)" if i == 0 else None)
        ax.text(x - w / 2, mut[2] + 0.6, f"+{mut[0]:.1f} pp\n(pooled +{MUTATION_GAP_POOLED[i]:.1f})",
                ha="center", va="bottom", fontsize=8.5, color=fg)
        ax.text(x + w / 2, model[2] + 0.6, f"{model[0]:.1f}%\n(n={MODEL_GAP_N[i]})",
                ha="center", va="bottom", fontsize=8.5, color=fg)

    ax.set_xticks(xs)
    ax.set_xticklabels(DATASETS, fontsize=10, color=fg)
    ax.set_ylabel("percentage points", color=fg, fontsize=9.5)
    ax.set_ylim(0, 30)
    ax.tick_params(colors=fg, labelsize=9)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(grid)
    ax.yaxis.grid(True, color=grid, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_title("What the visible test suite misses, measured before any RL training",
                 fontsize=10, color=fg, loc="left")
    ax.legend(loc="upper left", fontsize=7.8, frameon=False, labelcolor=fg)
    fig.text(0.01, 0.01,
             "Source: results/phase-b-2026-08-14/, results/phase-c-2026-08-15/ (docs/08). "
             "Different populations, side by side, not a ratio.",
             fontsize=7, color=fg, alpha=0.75)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, facecolor=bg)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
