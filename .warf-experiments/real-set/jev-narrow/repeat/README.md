# Lever "repeat": averaging repeated Jev calls (2026-11-09)

**Question.** Jev is not deterministic. Does averaging three identical calls per state beat the frozen
reference N (one run, `../answers.jsonl`)?

**What was run.** Two more identical runs of the frozen request: `../run_narrow.py` unchanged
(verdict + 7 generic checks, whole change + each hunk, 321 calls per run, 4 workers).
All calls went to `typesafe/jev-1.14-20261014`, the same model as run 1. No errors.

**Scores, fixed before the results were seen:**
- `N_mean3` (primary): mean of p over runs 1-3 for each call, then hmax over hunks and the mean logit of the 7 checks.
- `N_run2` and `N_run3`: the frozen N on one run each, to show how much the reference itself varies from run to run.
- `N_mean12`: runs 1 and 2 only, to see whether more runs help more.

## Files
- `smoke.jsonl`: 2-item smoke test (5 calls), not used in scoring.
- `run2.jsonl`, `run3.jsonl` (+ `.log`): the two repeat runs.
- `score_repeat.py` → `score_repeat.log`: noise and scores (no calls).
- `loo_diag.log`: a check of `jevscore.loo_size` on N (see the caveat below).

Rescore: `PYTHONIOENCODING=utf-8 C:\workdir\claudeVersuch\gs\cf\python.exe -B score_repeat.py`

**Cost:** $0.0778 in total (smoke $0.0006, run 2 $0.0386, run 3 $0.0386), from `usage.cost`.

## Call-to-call noise (3 pairs of runs × 321 calls)

| question | mean abs dp | max abs dp | same p | same choice (p ≥ 0.5) |
|---|---|---|---|---|
| verdict | 0.021 | 0.16 | 0.25 | 0.98 |
| offbyone | 0.009 | 0.12 | 0.64 | 0.99 |
| condition | 0.017 | 0.15 | 0.42 | 0.99 |
| wrongvar | 0.015 | 0.15 | 0.43 | 0.99 |
| missing | 0.022 | 0.22 | 0.25 | 0.98 |
| memory | 0.010 | 0.27 | 0.58 | 0.99 |
| interface | 0.023 | 0.24 | 0.29 | 0.97 |
| compile | 0.020 | 0.14 | 0.27 | 0.98 |

Between runs, an item's N changes by a mean of 0.09-0.10 logit (at most 0.37).

## Results (132 items)

| score | AUC | within thirds | LOO size + score | d vs ref_N [95% CI] |
|---|---|---|---|---|
| ref_N (run 1) | 0.892 | 0.830 | 0.910 | — |
| **N_mean3 (primary)** | 0.892 | 0.834 | 0.891 | −0.000 [−0.006, +0.006] |
| N_run2 | 0.888 | 0.831 | 0.905 | −0.004 [−0.014, +0.006] |
| N_run3 | 0.892 | 0.827 | 0.904 | −0.000 [−0.010, +0.009] |
| N_mean12 | 0.892 | 0.836 | 0.903 | +0.000 [−0.006, +0.006] |

**Reading.** Averaging changes nothing. The noise is small: about 0.02 in p, and the YES/NO choice
is the same in 97-99 % of calls. The reference itself moves only ±0.004 AUC between runs. The
0.892 is therefore not luck of one run, and repeated calls are not a lever.

**Caveat about `jevscore.loo_size`.** It passes the score through `lg()` when the value lies in
[0, 1], and otherwise uses it as it is. N is already a logit, and 6-8 items per run have N in [0, 1].
Those items get transformed twice, so the LOO column jumps around (0.891-0.910) for reasons that have
nothing to do with Jev. With the raw N as the feature (`loo([size, N])`, `loo_diag.log`), every
score gives 0.902-0.905: ref 0.905, mean3 0.904, run2 0.902, run3 0.903, mean12 0.903.
`jevscore.py` was not edited.
