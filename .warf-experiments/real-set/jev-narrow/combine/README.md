# combine: better use of Jev answers already paid for (2026-11-09, no API calls, $0)

## What was asked
Can a different aggregation of answers already stored in `../` beat the frozen reference
`jevscore.ref_N()` (generic 7 checks, mean logit of each check's max over hunks, answers.jsonl:
AUC 0.892, within thirds 0.830, LOO size+score 0.910)? No new Jev calls.

## Pre-registered scores (fixed before any of them was computed)
At most 4 scores per lever, so one of the five suggested candidates was dropped beforehand:
"hunk max / log(1 + number of hunks)" divides by a hunk count that grows with change size, which
is the strongest known predictor of a defect here, so it was judged the least promising a priori.

| Name | Definition |
|---|---|
| **B_ridge_nested** (primary) | ridge logistic over 17 features: log(1 + added lines), lg of the 8 whole answers (verdict + 7 checks) and lg of the 8 hunk-max answers of `answers.jsonl`. Nested leave-one-out: in each outer fold the ridge is chosen from {0.3, 1, 3, 10} by inner LOO AUC on the 131 remaining items (ties go to the larger ridge), refitted on those 131 and applied to the held-out item. Score = held-out linear predictor. |
| A_noisyor | per generic check, noisy-OR over hunks, 1 - prod(1 - p_h), with each p_h clipped to [0.01, 0.99] as `lg` does; score = mean over the 7 checks of its logit (whole answer if an item had no hunk) |
| A_top2 | per generic check, mean of lg of the two largest hunk answers (one hunk: that one); score = mean over the 7 checks |
| C_mean_plain_json | (ref_N + N_json) / 2, N_json = mean lg of the 7 generic checks on the whole JSON-state call (`answers_json.jsonl`); all 132 ids are common to both files, so the comparison uses all 132 |

## Files
- `combine.py`: computes all scores (imports `../jevscore.py`), writes `combine.log` and `scores.json`
  (per-item scores, ridge chosen per outer fold, inner LOO AUCs). Runs in about 5.5 minutes (4 processes).
  `PYTHONIOENCODING=utf-8 C:\workdir\claudeVersuch\gs\cf\python.exe -B combine.py`
- Inputs (read only): `../answers.jsonl` (verdict + 7 generic checks, whole + hunks) and `../answers_json.jsonl`
  (whole only, JSON state; its records carry `probabilities` and no `state` field, which `jevscore.load` reads as whole).
  `answers_gismo.jsonl` was not used (its checks were written from the dev defect descriptions, so it is in-sample).

## Cost
No API calls; $0.

## Results (132 items; 42 have more than one hunk, so the hunk aggregations differ from ref_N only on those)

| Score | AUC | within thirds | LOO size+score | d AUC vs ref_N [95% CI] |
|---|---|---|---|---|
| ref_N (reference) | 0.892 | 0.830 | 0.910 | |
| **B_ridge_nested** (primary) | 0.883 | 0.777 | 0.882 | -0.009 [-0.043, +0.022] |
| A_noisyor | 0.882 | 0.810 | 0.895 | -0.010 [-0.028, +0.007] |
| A_top2 | 0.877 | 0.831 | 0.909 | -0.015 [-0.039, +0.007] |
| C_mean_plain_json | 0.895 | 0.842 | 0.903 | +0.003 [-0.007, +0.014] |
| N_json alone (component of C, not a candidate) | 0.891 | 0.846 | 0.901 | -0.001 [-0.022, +0.020] |

- **Primary (B) is worse than the fixed mean logit, not better.** With 17 features on 132 items, the inner LOO
  chose ridge 3 in 110 folds and 10 in 21 (1 in one); the held-out AUC 0.883 is below ref_N, and within thirds it
  drops to 0.777. Learned weights do not beat an equal-weight mean of the checks here.
- **No hunk aggregation beats the max.** Noisy-OR rewards many hunks (a size proxy) and loses within thirds;
  top-2 ties within thirds but loses overall AUC.
- **Averaging the two calls (C) is the only score above ref_N, by +0.003, CI [-0.007, +0.014]: noise.** The two
  calls correlate 0.973 (Pearson), so a second call on another input format is nearly a copy of the first.
- `loo_size` quirk (diagnostic only): `jevscore.loo_size` applies `lg` to every score value that falls in [0, 1],
  also for raw mean-logit scores (7 of ref_N's 132 values). `combine.log` also lists LOO size + raw score without
  that transform (ref_N 0.905, B 0.875, A_noisyor 0.899, A_top2 0.903, C 0.907, N_json 0.907); the conclusions do not change.

**Verdict:** using the answers already paid for better does not move the score; all four candidates are within
+-0.015 of ref_N, like every earlier lever.
