# Confirmation test: the effort panel against one Opus, on fresh real G+Smo bugs

This file was fixed on 2026-11-07, before any item of this set existed and before any reviewer saw any
of it. It is not changed after the first scored review. Any later change is added below with its date
and reason, and it never enters the primary result.

## Why this test

On the 132-item development set (`../real-set/`, `DEV.md`) the best panel found was one Opus reviewer
at three effort levels, rejecting a change if any level rejects it:

| Development set | Balanced accuracy |
|---|---|
| Panel: low + default + max effort, "reject if any rejects" | 0.939 |
| Best single reviewer: Opus at low effort | 0.917 |

The panel was picked as the best of 32 variants, and its lead was 3 items net. Only a fresh set can
show whether the lead is real.

## The frozen configuration

Every reviewer is Claude Opus 5.5 through the isolated CLI, run with
`../planted/run_planted.py --arm claude-commit-strict-tools`:
- the question is `STRICT_PERSONA` plus the snapshot sentence;
- the input is the whole commit (`commit_inputs.jsonl`, built as in `../real-set/build_commit_inputs.py`);
- read-only search of the repository at that commit (a `git archive` snapshot, no `.git`).

| Arm | What it is |
|---|---|
| **P, the effort panel** | REJECT if low, default or max effort rejects |
| S-low | the same reviewer at `--effort low` |
| S-default | the same reviewer at the CLI's default effort |

**Asking order for P (WaRF's early stop).** The panel gives the same verdict as asking all three seats,
but it asks in sequence:
1. low effort on every item;
2. default effort only where low approved;
3. max effort only where both approved.

S-low is P's first seat and S-default is its second. S-default is also run on the items low rejected,
so it is complete as a single arm.

## The set

Built before any review (`build_confirm.py`):
- **Defective items:**
  - changes in the gismo6 history, under `src/` or elsewhere in C++, that a later fix of kind "defect"
    blamed within 180 days;
  - the fix touches at most 5 files, and its subject names a bug;
  - no commit used by any earlier set;
  - two independent judges confirm that the change itself introduced the defect.
- **Clean items:** survival-screened, matched by date and size, and checked without Claude.

## Primary analysis

Balanced accuracy on all items.
- **P wins** if it beats **both** S-low and S-default, with exact McNemar p < 0.05 and a bootstrap
  (stratified by class, 2000 resamples, seed 4) whose lower bound is above 0.
- **Not shown** if P's difference against both is positive but either test fails.
- **No case** otherwise.

Reported beside the primary result: recall, false alarms, and the number of calls at each effort.

## Status

- **2026-11-07, Phase 1 done** (git only, no model calls): 366 defective candidates (217 under `src/`) and 700 clean controls.
- **Expected size:** at the development set's confirmation rate (66 of 150), about 160 confirmed defects, so about 320 items with their matched controls. That is fewer than the roughly 500 the power estimate wanted.
- **Next, after the weekly quota reset:** two judges per candidate, then the frozen panel and its rivals.
- **2026-11-07/08, judges and reviews done:** 110 defects confirmed by both judges (23 disagreements and 233 rejections dropped), plus 110 matched clean items, 220 in all. That is below the expected size. Low and default effort ran on all 220 items; max effort ran on the 110 items both approved.

## Result (2026-11-08, `score_confirm.py`; rechecked with separate code)

| Arm | BA | Caught | False alarms |
|---|---|---|---|
| **P, effort panel** | **0.868** | 100/110 | 19/110 |
| S-low | 0.827 | 87/110 | 15/110 |
| S-default | 0.855 | 91/110 | 13/110 |

| Comparison | Difference | 95% bootstrap | Only P right | Only rival right | McNemar p |
|---|---|---|---|---|---|
| P - S-low | +0.041 | [+0.005, +0.077] | 13 | 4 | 0.049 |
| P - S-default | +0.014 | [-0.018, +0.045] | 9 | 6 | 0.607 |

**Preregistered verdict: not shown.** P beats S-low, but its lead over S-default is within noise.

Not part of the verdict:
- Low or default alone, without max, scores 0.845, below S-default. All of P's gain over S-default comes from the max seat.
- On the 110 items both approved, max rejected 9: 7 of them defective, 2 clean.
- Calls per item: low 220, default 220, max 110. In sequence, default is asked only where low approved, 118 times.
