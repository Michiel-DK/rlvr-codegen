# Mutation-score audit — humaneval

docs/07 Phase B: mutation score visible vs extended, over reference-solution mutants.
Seed: 20260814. N tasks: 163. N mutants attempted: 2455 (N valid, env_error excluded: 2455; env_error: 0).

## Headline

| Metric | Value |
|---|---|
| Mutation score — visible (base) suite | 89.2% (95% CI 88.0%–90.4%, n=2455) ¹ |
| Mutation score — extended (base ∪ plus) suite | 92.9% (95% CI 91.8%–93.8%, n=2455) ¹ |
| GAP, pooled (extended − visible, = row 2 − row 1) | +3.6% |
| GAP, mean per-task (extended − visible) ² | +3.2% (95% CI +2.2%–+4.3%) |
| N mutants (valid / attempted) | 2455 / 2455 |
| N tasks | 163 |
| env_error count | 0 |
| survived_both count | 175 |

¹ Pooled-mutant Wilson interval: treats all valid mutants as independent Bernoulli trials, which they are not (mutants cluster within tasks) — read these CIs as anti-conservative. ² The task-mean GAP weights every task equally regardless of its mutant count, so it need not equal the pooled row-2 − row-1 difference; both are reported to keep the arithmetic honest (review finding, PR #13).

`survived_both` is **not** equivalence and the extended suite is **not** ground truth (docs/07 forbids both claims) — it means the mutant is not distinguishable by either suite: possibly the mutation is behaviorally equivalent, possibly both suites simply miss it. GAP's point estimate is the mean, over tasks with at least one valid mutant, of that task's own (extended_score − visible_score); its 95% CI is a percentile bootstrap (n_boot=10000, seed=20260814) over those same per-task gap values — a task-resampled CI, not a mutant-resampled one, since a mutant's fate is not independent of which task it came from.

## Per-task

| task_id | n_valid | killed_visible | killed_ext_only | survived_both | env_error | visible | extended | gap | flags |
|---|---|---|---|---|---|---|---|---|---|
| HumanEval/0 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/1 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/2 | 5 | 4 | 1 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
| HumanEval/3 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/4 | 15 | 14 | 1 | 0 | 0 | 93.3% | 100.0% | +6.7% |  |
| HumanEval/5 | 13 | 12 | 0 | 1 | 0 | 92.3% | 92.3% | +0.0% |  |
| HumanEval/6 | 20 | 15 | 1 | 4 | 0 | 75.0% | 80.0% | +5.0% |  |
| HumanEval/7 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/8 | 4 | 4 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/9 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/10 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/11 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/12 | 7 | 6 | 0 | 1 | 0 | 85.7% | 85.7% | +0.0% |  |
| HumanEval/13 | 12 | 11 | 0 | 1 | 0 | 91.7% | 91.7% | +0.0% |  |
| HumanEval/14 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/15 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/16 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/17 | 20 | 16 | 0 | 4 | 0 | 80.0% | 80.0% | +0.0% |  |
| HumanEval/18 | 7 | 6 | 0 | 1 | 0 | 85.7% | 85.7% | +0.0% |  |
| HumanEval/19 | 20 | 14 | 4 | 2 | 0 | 70.0% | 90.0% | +20.0% |  |
| HumanEval/20 | 19 | 18 | 1 | 0 | 0 | 94.7% | 100.0% | +5.3% |  |
| HumanEval/21 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/22 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/23 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/24 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/25 | 20 | 15 | 0 | 5 | 0 | 75.0% | 75.0% | +0.0% |  |
| HumanEval/26 | 18 | 17 | 0 | 1 | 0 | 94.4% | 94.4% | +0.0% |  |
| HumanEval/27 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/28 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/29 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/30 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/31 | 20 | 14 | 1 | 5 | 0 | 70.0% | 75.0% | +5.0% |  |
| HumanEval/32 | 20 | 18 | 1 | 1 | 0 | 90.0% | 95.0% | +5.0% |  |
| HumanEval/33 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/34 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/35 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/36 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/37 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/38 | 20 | 16 | 1 | 3 | 0 | 80.0% | 85.0% | +5.0% |  |
| HumanEval/39 | 20 | 15 | 0 | 5 | 0 | 75.0% | 75.0% | +0.0% |  |
| HumanEval/40 | 20 | 13 | 3 | 4 | 0 | 65.0% | 80.0% | +15.0% |  |
| HumanEval/41 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/42 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/43 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/44 | 20 | 17 | 2 | 1 | 0 | 85.0% | 95.0% | +10.0% |  |
| HumanEval/45 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/46 | 20 | 13 | 1 | 6 | 0 | 65.0% | 70.0% | +5.0% |  |
| HumanEval/47 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/48 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/49 | 20 | 16 | 1 | 3 | 0 | 80.0% | 85.0% | +5.0% |  |
| HumanEval/50 | 20 | 18 | 1 | 1 | 0 | 90.0% | 95.0% | +5.0% |  |
| HumanEval/51 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/52 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/53 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/54 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/55 | 20 | 16 | 2 | 2 | 0 | 80.0% | 90.0% | +10.0% |  |
| HumanEval/56 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/57 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/58 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/59 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/60 | 19 | 18 | 0 | 1 | 0 | 94.7% | 94.7% | +0.0% |  |
| HumanEval/61 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/62 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/63 | 20 | 14 | 2 | 4 | 0 | 70.0% | 80.0% | +10.0% |  |
| HumanEval/64 | 20 | 16 | 3 | 1 | 0 | 80.0% | 95.0% | +15.0% |  |
| HumanEval/65 | 20 | 17 | 1 | 2 | 0 | 85.0% | 90.0% | +5.0% |  |
| HumanEval/66 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/67 | 20 | 16 | 0 | 4 | 0 | 80.0% | 80.0% | +0.0% |  |
| HumanEval/68 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/69 | 19 | 19 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/70 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/71 | 20 | 19 | 1 | 0 | 0 | 95.0% | 100.0% | +5.0% |  |
| HumanEval/72 | 13 | 12 | 1 | 0 | 0 | 92.3% | 100.0% | +7.7% |  |
| HumanEval/73 | 19 | 19 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/74 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/75 | 20 | 10 | 2 | 8 | 0 | 50.0% | 60.0% | +10.0% |  |
| HumanEval/76 | 20 | 12 | 8 | 0 | 0 | 60.0% | 100.0% | +40.0% |  |
| HumanEval/77 | 14 | 14 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/78 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/79 | 14 | 14 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/80 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/81 | 20 | 17 | 1 | 2 | 0 | 85.0% | 90.0% | +5.0% |  |
| HumanEval/82 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/84 | 4 | 4 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/85 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/86 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/87 | 17 | 17 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/88 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/89 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/90 | 16 | 11 | 0 | 5 | 0 | 68.8% | 68.8% | +0.0% |  |
| HumanEval/91 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| HumanEval/92 | 20 | 19 | 1 | 0 | 0 | 95.0% | 100.0% | +5.0% |  |
| HumanEval/93 | 20 | 18 | 2 | 0 | 0 | 90.0% | 100.0% | +10.0% |  |
| HumanEval/94 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/95 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/96 | 20 | 13 | 0 | 7 | 0 | 65.0% | 65.0% | +0.0% |  |
| HumanEval/97 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/98 | 15 | 15 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/99 | 20 | 18 | 1 | 1 | 0 | 90.0% | 95.0% | +5.0% |  |
| HumanEval/100 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/101 | 5 | 3 | 0 | 2 | 0 | 60.0% | 60.0% | +0.0% |  |
| HumanEval/102 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/103 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/104 | 17 | 16 | 0 | 1 | 0 | 94.1% | 94.1% | +0.0% |  |
| HumanEval/105 | 20 | 16 | 3 | 1 | 0 | 80.0% | 95.0% | +15.0% |  |
| HumanEval/106 | 20 | 16 | 2 | 2 | 0 | 80.0% | 90.0% | +10.0% |  |
| HumanEval/107 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/108 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/109 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/110 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/111 | 20 | 16 | 1 | 3 | 0 | 80.0% | 85.0% | +5.0% |  |
| HumanEval/112 | 13 | 12 | 1 | 0 | 0 | 92.3% | 100.0% | +7.7% |  |
| HumanEval/113 | 14 | 13 | 0 | 1 | 0 | 92.9% | 92.9% | +0.0% |  |
| HumanEval/114 | 20 | 14 | 1 | 5 | 0 | 70.0% | 75.0% | +5.0% |  |
| HumanEval/115 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/116 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/117 | 18 | 16 | 1 | 1 | 0 | 88.9% | 94.4% | +5.6% |  |
| HumanEval/118 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/119 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/120 | 4 | 4 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/121 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/122 | 20 | 13 | 6 | 1 | 0 | 65.0% | 95.0% | +30.0% |  |
| HumanEval/123 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/124 | 20 | 16 | 3 | 1 | 0 | 80.0% | 95.0% | +15.0% |  |
| HumanEval/125 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/126 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/127 | 20 | 11 | 8 | 1 | 0 | 55.0% | 95.0% | +40.0% |  |
| HumanEval/128 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/129 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/130 | 20 | 18 | 2 | 0 | 0 | 90.0% | 100.0% | +10.0% |  |
| HumanEval/131 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/132 | 20 | 17 | 0 | 3 | 0 | 85.0% | 85.0% | +0.0% |  |
| HumanEval/133 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/134 | 20 | 18 | 1 | 1 | 0 | 90.0% | 95.0% | +5.0% |  |
| HumanEval/135 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/136 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/137 | 11 | 8 | 2 | 1 | 0 | 72.7% | 90.9% | +18.2% |  |
| HumanEval/138 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/139 | 13 | 12 | 1 | 0 | 0 | 92.3% | 100.0% | +7.7% |  |
| HumanEval/140 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/141 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/142 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/143 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/144 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/145 | 16 | 15 | 0 | 1 | 0 | 93.8% | 93.8% | +0.0% |  |
| HumanEval/146 | 20 | 18 | 1 | 1 | 0 | 90.0% | 95.0% | +5.0% |  |
| HumanEval/147 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/148 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/149 | 20 | 16 | 1 | 3 | 0 | 80.0% | 85.0% | +5.0% |  |
| HumanEval/150 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/151 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| HumanEval/152 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/153 | 20 | 17 | 0 | 3 | 0 | 85.0% | 85.0% | +0.0% |  |
| HumanEval/154 | 20 | 17 | 2 | 1 | 0 | 85.0% | 95.0% | +10.0% |  |
| HumanEval/155 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/156 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| HumanEval/157 | 20 | 15 | 5 | 0 | 0 | 75.0% | 100.0% | +25.0% |  |
| HumanEval/158 | 20 | 17 | 0 | 3 | 0 | 85.0% | 85.0% | +0.0% |  |
| HumanEval/159 | 20 | 18 | 1 | 1 | 0 | 90.0% | 95.0% | +5.0% |  |
| HumanEval/160 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/161 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| HumanEval/162 | 6 | 5 | 0 | 1 | 0 | 83.3% | 83.3% | +0.0% |  |
| HumanEval/163 | 20 | 15 | 3 | 2 | 0 | 75.0% | 90.0% | +15.0% |  |
