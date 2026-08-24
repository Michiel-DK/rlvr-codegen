# Mutation-score audit — mbpp

docs/07 Phase B: mutation score visible vs extended, over reference-solution mutants.
Seed: 20260814. N tasks: 377. N mutants attempted: 3477 (N valid, env_error excluded: 3477; env_error: 0).

## Headline

| Metric | Value |
|---|---|
| Mutation score — visible (base) suite | 87.1% (95% CI 85.9%–88.2%, n=3477) ¹ |
| Mutation score — extended (base ∪ plus) suite | 93.5% (95% CI 92.6%–94.3%, n=3477) ¹ |
| GAP, pooled (extended − visible, = row 2 − row 1) | +6.4% |
| GAP, mean per-task (extended − visible) ² | +5.7% (95% CI +4.3%–+7.2%) |
| N mutants (valid / attempted) | 3477 / 3477 |
| N tasks | 377 |
| env_error count | 0 |
| survived_both count | 226 |

¹ Pooled-mutant Wilson interval: treats all valid mutants as independent Bernoulli trials, which they are not (mutants cluster within tasks) — read these CIs as anti-conservative. ² The task-mean GAP weights every task equally regardless of its mutant count, so it need not equal the pooled row-2 − row-1 difference; both are reported to keep the arithmetic honest (review finding, PR #13).

`survived_both` is **not** equivalence and the extended suite is **not** ground truth (docs/07 forbids both claims) — it means the mutant is not distinguishable by either suite: possibly the mutation is behaviorally equivalent, possibly both suites simply miss it. GAP's point estimate is the mean, over tasks with at least one valid mutant, of that task's own (extended_score − visible_score); its 95% CI is a percentile bootstrap (n_boot=10000, seed=20260814) over those same per-task gap values — a task-resampled CI, not a mutant-resampled one, since a mutant's fate is not independent of which task it came from.

## Per-task

| task_id | n_valid | killed_visible | killed_ext_only | survived_both | env_error | visible | extended | gap | flags |
|---|---|---|---|---|---|---|---|---|---|
| Mbpp/2 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/3 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/4 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/6 | 20 | 18 | 1 | 1 | 0 | 90.0% | 95.0% | +5.0% |  |
| Mbpp/7 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/8 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/9 | 20 | 16 | 0 | 4 | 0 | 80.0% | 80.0% | +0.0% |  |
| Mbpp/11 | 8 | 6 | 2 | 0 | 0 | 75.0% | 100.0% | +25.0% |  |
| Mbpp/12 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/14 | 17 | 16 | 1 | 0 | 0 | 94.1% | 100.0% | +5.9% |  |
| Mbpp/16 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/17 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/18 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/19 | 5 | 4 | 0 | 1 | 0 | 80.0% | 80.0% | +0.0% |  |
| Mbpp/20 | 20 | 6 | 6 | 8 | 0 | 30.0% | 60.0% | +30.0% |  |
| Mbpp/56 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/57 | 1 | 1 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/58 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/59 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/61 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/62 | 7 | 3 | 1 | 3 | 0 | 42.9% | 57.1% | +14.3% |  |
| Mbpp/63 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/64 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/65 | 18 | 18 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/66 | 7 | 5 | 2 | 0 | 0 | 71.4% | 100.0% | +28.6% |  |
| Mbpp/67 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/68 | 19 | 17 | 2 | 0 | 0 | 89.5% | 100.0% | +10.5% |  |
| Mbpp/69 | 20 | 12 | 5 | 3 | 0 | 60.0% | 85.0% | +25.0% |  |
| Mbpp/70 | 7 | 6 | 0 | 1 | 0 | 85.7% | 85.7% | +0.0% |  |
| Mbpp/71 | 20 | 14 | 1 | 5 | 0 | 70.0% | 75.0% | +5.0% |  |
| Mbpp/72 | 14 | 13 | 1 | 0 | 0 | 92.9% | 100.0% | +7.1% |  |
| Mbpp/74 | 14 | 12 | 1 | 1 | 0 | 85.7% | 92.9% | +7.1% |  |
| Mbpp/75 | 12 | 11 | 0 | 1 | 0 | 91.7% | 91.7% | +0.0% |  |
| Mbpp/77 | 14 | 13 | 0 | 1 | 0 | 92.9% | 92.9% | +0.0% |  |
| Mbpp/79 | 14 | 13 | 0 | 1 | 0 | 92.9% | 92.9% | +0.0% |  |
| Mbpp/80 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/82 | 17 | 17 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/84 | 20 | 14 | 3 | 3 | 0 | 70.0% | 85.0% | +15.0% |  |
| Mbpp/85 | 14 | 14 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/86 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/87 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/88 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/89 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/90 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/91 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/92 | 18 | 15 | 3 | 0 | 0 | 83.3% | 100.0% | +16.7% |  |
| Mbpp/93 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/94 | 4 | 4 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/95 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/96 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| Mbpp/97 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/98 | 10 | 10 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/99 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/100 | 20 | 13 | 3 | 4 | 0 | 65.0% | 80.0% | +15.0% |  |
| Mbpp/101 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/102 | 1 | 1 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/103 | 20 | 15 | 0 | 5 | 0 | 75.0% | 75.0% | +0.0% |  |
| Mbpp/104 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/105 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/106 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/108 | 10 | 10 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/109 | 17 | 16 | 0 | 1 | 0 | 94.1% | 94.1% | +0.0% |  |
| Mbpp/111 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/113 | 20 | 11 | 9 | 0 | 0 | 55.0% | 100.0% | +45.0% |  |
| Mbpp/116 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/118 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/119 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/120 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/123 | 20 | 16 | 0 | 4 | 0 | 80.0% | 80.0% | +0.0% |  |
| Mbpp/124 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/125 | 20 | 13 | 4 | 3 | 0 | 65.0% | 85.0% | +20.0% |  |
| Mbpp/126 | 20 | 16 | 1 | 3 | 0 | 80.0% | 85.0% | +5.0% |  |
| Mbpp/127 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/128 | 5 | 4 | 1 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
| Mbpp/129 | 20 | 12 | 1 | 7 | 0 | 60.0% | 65.0% | +5.0% |  |
| Mbpp/130 | 2 | 1 | 0 | 1 | 0 | 50.0% | 50.0% | +0.0% |  |
| Mbpp/131 | 6 | 4 | 2 | 0 | 0 | 66.7% | 100.0% | +33.3% |  |
| Mbpp/132 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/133 | 7 | 4 | 1 | 2 | 0 | 57.1% | 71.4% | +14.3% |  |
| Mbpp/135 | 19 | 19 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/137 | 20 | 19 | 1 | 0 | 0 | 95.0% | 100.0% | +5.0% |  |
| Mbpp/138 | 20 | 17 | 1 | 2 | 0 | 85.0% | 90.0% | +5.0% |  |
| Mbpp/139 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/140 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/141 | 20 | 17 | 0 | 3 | 0 | 85.0% | 85.0% | +0.0% |  |
| Mbpp/142 | 10 | 9 | 1 | 0 | 0 | 90.0% | 100.0% | +10.0% |  |
| Mbpp/145 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/160 | 20 | 18 | 2 | 0 | 0 | 90.0% | 100.0% | +10.0% |  |
| Mbpp/161 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/162 | 20 | 16 | 1 | 3 | 0 | 80.0% | 85.0% | +5.0% |  |
| Mbpp/165 | 10 | 9 | 0 | 1 | 0 | 90.0% | 90.0% | +0.0% |  |
| Mbpp/166 | 20 | 15 | 1 | 4 | 0 | 75.0% | 80.0% | +5.0% |  |
| Mbpp/167 | 20 | 14 | 5 | 1 | 0 | 70.0% | 95.0% | +25.0% |  |
| Mbpp/168 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/170 | 11 | 11 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/171 | 7 | 7 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/172 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/222 | 2 | 0 | 1 | 1 | 0 | 0.0% | 50.0% | +50.0% |  |
| Mbpp/223 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| Mbpp/224 | 4 | 2 | 0 | 2 | 0 | 50.0% | 50.0% | +0.0% |  |
| Mbpp/226 | 4 | 4 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/227 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/230 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/232 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/233 | 17 | 17 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/234 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/235 | 9 | 8 | 0 | 1 | 0 | 88.9% | 88.9% | +0.0% |  |
| Mbpp/237 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/238 | 19 | 18 | 0 | 1 | 0 | 94.7% | 94.7% | +0.0% |  |
| Mbpp/239 | 20 | 17 | 0 | 3 | 0 | 85.0% | 85.0% | +0.0% |  |
| Mbpp/240 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/242 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/244 | 20 | 14 | 6 | 0 | 0 | 70.0% | 100.0% | +30.0% |  |
| Mbpp/245 | 20 | 17 | 0 | 3 | 0 | 85.0% | 85.0% | +0.0% |  |
| Mbpp/247 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/250 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/251 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/252 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/253 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/256 | 16 | 15 | 0 | 1 | 0 | 93.8% | 93.8% | +0.0% |  |
| Mbpp/257 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/259 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/260 | 20 | 12 | 1 | 7 | 0 | 60.0% | 65.0% | +5.0% |  |
| Mbpp/261 | 5 | 4 | 1 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
| Mbpp/262 | 4 | 4 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/264 | 20 | 16 | 3 | 1 | 0 | 80.0% | 95.0% | +15.0% |  |
| Mbpp/265 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/266 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/267 | 20 | 19 | 1 | 0 | 0 | 95.0% | 100.0% | +5.0% |  |
| Mbpp/268 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/269 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/270 | 16 | 15 | 0 | 1 | 0 | 93.8% | 93.8% | +0.0% |  |
| Mbpp/271 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/272 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/273 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/274 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/276 | 15 | 15 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/277 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/278 | 1 | 1 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/279 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/280 | 14 | 10 | 4 | 0 | 0 | 71.4% | 100.0% | +28.6% |  |
| Mbpp/281 | 5 | 4 | 0 | 1 | 0 | 80.0% | 80.0% | +0.0% |  |
| Mbpp/282 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/283 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/284 | 5 | 4 | 1 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
| Mbpp/285 | 6 | 5 | 0 | 1 | 0 | 83.3% | 83.3% | +0.0% |  |
| Mbpp/286 | 14 | 11 | 0 | 3 | 0 | 78.6% | 78.6% | +0.0% |  |
| Mbpp/287 | 20 | 19 | 1 | 0 | 0 | 95.0% | 100.0% | +5.0% |  |
| Mbpp/290 | 2 | 0 | 2 | 0 | 0 | 0.0% | 100.0% | +100.0% |  |
| Mbpp/292 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/293 | 15 | 15 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/294 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/296 | 17 | 14 | 0 | 3 | 0 | 82.4% | 82.4% | +0.0% |  |
| Mbpp/297 | 1 | 1 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/299 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/300 | 20 | 19 | 1 | 0 | 0 | 95.0% | 100.0% | +5.0% |  |
| Mbpp/301 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/305 | 1 | 1 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/306 | 20 | 15 | 4 | 1 | 0 | 75.0% | 95.0% | +20.0% |  |
| Mbpp/308 | 8 | 8 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/309 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/310 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/311 | 20 | 14 | 2 | 4 | 0 | 70.0% | 80.0% | +10.0% |  |
| Mbpp/312 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/388 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/389 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| Mbpp/390 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/391 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/392 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/394 | 5 | 4 | 0 | 1 | 0 | 80.0% | 80.0% | +0.0% |  |
| Mbpp/395 | 8 | 7 | 0 | 1 | 0 | 87.5% | 87.5% | +0.0% |  |
| Mbpp/397 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/398 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/404 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/405 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/406 | 14 | 13 | 0 | 1 | 0 | 92.9% | 92.9% | +0.0% |  |
| Mbpp/409 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/410 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/412 | 14 | 13 | 0 | 1 | 0 | 92.9% | 92.9% | +0.0% |  |
| Mbpp/413 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/414 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/415 | 14 | 14 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/418 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/419 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/420 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/421 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/422 | 16 | 15 | 0 | 1 | 0 | 93.8% | 93.8% | +0.0% |  |
| Mbpp/424 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/425 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/426 | 14 | 13 | 0 | 1 | 0 | 92.9% | 92.9% | +0.0% |  |
| Mbpp/427 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/428 | 20 | 17 | 0 | 3 | 0 | 85.0% | 85.0% | +0.0% |  |
| Mbpp/429 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/430 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/432 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/433 | 5 | 3 | 2 | 0 | 0 | 60.0% | 100.0% | +40.0% |  |
| Mbpp/435 | 15 | 11 | 2 | 2 | 0 | 73.3% | 86.7% | +13.3% |  |
| Mbpp/436 | 7 | 5 | 2 | 0 | 0 | 71.4% | 100.0% | +28.6% |  |
| Mbpp/437 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/439 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/440 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/441 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/445 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/446 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/447 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/448 | 20 | 14 | 6 | 0 | 0 | 70.0% | 100.0% | +30.0% |  |
| Mbpp/450 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/451 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/453 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| Mbpp/454 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/455 | 20 | 11 | 9 | 0 | 0 | 55.0% | 100.0% | +45.0% |  |
| Mbpp/456 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/457 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/458 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/459 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/460 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/462 | 19 | 18 | 0 | 1 | 0 | 94.7% | 94.7% | +0.0% |  |
| Mbpp/463 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/465 | 6 | 5 | 0 | 1 | 0 | 83.3% | 83.3% | +0.0% |  |
| Mbpp/468 | 20 | 8 | 10 | 2 | 0 | 40.0% | 90.0% | +50.0% |  |
| Mbpp/470 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/471 | 10 | 10 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/472 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/473 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/474 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/475 | 3 | 3 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/476 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/477 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/478 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/479 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/554 | 14 | 13 | 0 | 1 | 0 | 92.9% | 92.9% | +0.0% |  |
| Mbpp/555 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/556 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/557 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/558 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/559 | 20 | 14 | 4 | 2 | 0 | 70.0% | 90.0% | +20.0% |  |
| Mbpp/560 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/562 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/563 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/564 | 17 | 14 | 0 | 3 | 0 | 82.4% | 82.4% | +0.0% |  |
| Mbpp/565 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/566 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/567 | 9 | 8 | 1 | 0 | 0 | 88.9% | 100.0% | +11.1% |  |
| Mbpp/568 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/569 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/572 | 7 | 6 | 0 | 1 | 0 | 85.7% | 85.7% | +0.0% |  |
| Mbpp/573 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/576 | 20 | 14 | 4 | 2 | 0 | 70.0% | 90.0% | +20.0% |  |
| Mbpp/577 | 20 | 14 | 4 | 2 | 0 | 70.0% | 90.0% | +20.0% |  |
| Mbpp/578 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/579 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/580 | 16 | 15 | 0 | 1 | 0 | 93.8% | 93.8% | +0.0% |  |
| Mbpp/581 | 19 | 19 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/583 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/585 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/586 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/587 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/588 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/589 | 20 | 11 | 6 | 3 | 0 | 55.0% | 85.0% | +30.0% |  |
| Mbpp/590 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/591 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/592 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/593 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/594 | 20 | 14 | 2 | 4 | 0 | 70.0% | 80.0% | +10.0% |  |
| Mbpp/596 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/597 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/598 | 5 | 4 | 1 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
| Mbpp/599 | 14 | 13 | 1 | 0 | 0 | 92.9% | 100.0% | +7.1% |  |
| Mbpp/600 | 14 | 12 | 1 | 1 | 0 | 85.7% | 92.9% | +7.1% |  |
| Mbpp/602 | 17 | 13 | 1 | 3 | 0 | 76.5% | 82.4% | +5.9% |  |
| Mbpp/603 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/604 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/605 | 20 | 7 | 13 | 0 | 0 | 35.0% | 100.0% | +65.0% |  |
| Mbpp/606 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/607 | 7 | 6 | 0 | 1 | 0 | 85.7% | 85.7% | +0.0% |  |
| Mbpp/608 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/610 | 16 | 16 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/611 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/612 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/614 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/615 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/616 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/618 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/619 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/620 | 20 | 16 | 0 | 4 | 0 | 80.0% | 80.0% | +0.0% |  |
| Mbpp/622 | 20 | 17 | 2 | 1 | 0 | 85.0% | 95.0% | +10.0% |  |
| Mbpp/623 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/624 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/626 | 13 | 12 | 1 | 0 | 0 | 92.3% | 100.0% | +7.7% |  |
| Mbpp/628 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/629 | 14 | 13 | 0 | 1 | 0 | 92.9% | 92.9% | +0.0% |  |
| Mbpp/630 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/631 | 10 | 9 | 0 | 1 | 0 | 90.0% | 90.0% | +0.0% |  |
| Mbpp/632 | 20 | 19 | 1 | 0 | 0 | 95.0% | 100.0% | +5.0% |  |
| Mbpp/633 | 16 | 13 | 0 | 3 | 0 | 81.2% | 81.2% | +0.0% |  |
| Mbpp/635 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/637 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/638 | 20 | 19 | 1 | 0 | 0 | 95.0% | 100.0% | +5.0% |  |
| Mbpp/639 | 7 | 5 | 2 | 0 | 0 | 71.4% | 100.0% | +28.6% |  |
| Mbpp/641 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/643 | 6 | 5 | 0 | 1 | 0 | 83.3% | 83.3% | +0.0% |  |
| Mbpp/644 | 18 | 18 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/720 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/721 | 20 | 17 | 2 | 1 | 0 | 85.0% | 95.0% | +10.0% |  |
| Mbpp/722 | 15 | 11 | 3 | 1 | 0 | 73.3% | 93.3% | +20.0% |  |
| Mbpp/723 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/724 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/725 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/726 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/728 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/730 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/731 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/732 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/733 | 20 | 14 | 3 | 3 | 0 | 70.0% | 85.0% | +15.0% |  |
| Mbpp/734 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/735 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/736 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/737 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/739 | 16 | 16 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/740 | 15 | 15 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/741 | 11 | 3 | 6 | 2 | 0 | 27.3% | 81.8% | +54.5% |  |
| Mbpp/742 | 12 | 12 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/743 | 9 | 9 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/744 | 6 | 5 | 0 | 1 | 0 | 83.3% | 83.3% | +0.0% |  |
| Mbpp/745 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/748 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/749 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/750 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/751 | 20 | 11 | 8 | 1 | 0 | 55.0% | 95.0% | +40.0% |  |
| Mbpp/752 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/753 | 4 | 4 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/754 | 10 | 8 | 2 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
| Mbpp/755 | 10 | 8 | 2 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
| Mbpp/757 | 11 | 7 | 4 | 0 | 0 | 63.6% | 100.0% | +36.4% |  |
| Mbpp/758 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/759 | 6 | 5 | 0 | 1 | 0 | 83.3% | 83.3% | +0.0% |  |
| Mbpp/760 | 7 | 4 | 0 | 3 | 0 | 57.1% | 57.1% | +0.0% |  |
| Mbpp/762 | 20 | 16 | 4 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
| Mbpp/763 | 20 | 16 | 0 | 4 | 0 | 80.0% | 80.0% | +0.0% |  |
| Mbpp/764 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/765 | 20 | 19 | 1 | 0 | 0 | 95.0% | 100.0% | +5.0% |  |
| Mbpp/766 | 4 | 4 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/767 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/769 | 15 | 15 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/770 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/771 | 20 | 12 | 4 | 4 | 0 | 60.0% | 80.0% | +20.0% |  |
| Mbpp/772 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/773 | 4 | 4 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/775 | 20 | 19 | 0 | 1 | 0 | 95.0% | 95.0% | +0.0% |  |
| Mbpp/777 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/778 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/780 | 2 | 2 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/781 | 20 | 16 | 0 | 4 | 0 | 80.0% | 80.0% | +0.0% |  |
| Mbpp/782 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/784 | 20 | 12 | 4 | 4 | 0 | 60.0% | 80.0% | +20.0% |  |
| Mbpp/785 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/786 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/787 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/788 | 5 | 5 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/790 | 19 | 17 | 2 | 0 | 0 | 89.5% | 100.0% | +10.5% |  |
| Mbpp/791 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/792 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/793 | 14 | 14 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% | zero-plus-inputs |
| Mbpp/794 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/796 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/797 | 20 | 20 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/798 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/799 | 7 | 2 | 1 | 4 | 0 | 28.6% | 42.9% | +14.3% |  |
| Mbpp/800 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/801 | 20 | 18 | 0 | 2 | 0 | 90.0% | 90.0% | +0.0% |  |
| Mbpp/803 | 20 | 16 | 4 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
| Mbpp/804 | 14 | 12 | 1 | 1 | 0 | 85.7% | 92.9% | +7.1% |  |
| Mbpp/805 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | n/a | no valid mutants (excluded from headline) |
| Mbpp/806 | 19 | 13 | 4 | 2 | 0 | 68.4% | 89.5% | +21.1% |  |
| Mbpp/807 | 14 | 13 | 0 | 1 | 0 | 92.9% | 92.9% | +0.0% |  |
| Mbpp/808 | 6 | 6 | 0 | 0 | 0 | 100.0% | 100.0% | +0.0% |  |
| Mbpp/809 | 5 | 4 | 1 | 0 | 0 | 80.0% | 100.0% | +20.0% |  |
