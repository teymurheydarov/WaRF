# Power test: WaRF Jev (narrow checks) against one Jev, on a larger fresh set of real G+Smo bugs

This file was fixed on 2026-11-11, before any item of this set existed and before any reviewer or judge
saw any of it. It is not changed after the first Jev call on this set. Any later change is added below
with its date and reason, and it never enters the primary result.

## Why this test

On the fresh 220-item set (`../confirm-set/README.md`, second test) the narrow checks beat the usual
question, but the result was not significant:

| 220 fresh items | Balanced accuracy at the dev threshold | Caught | False alarms |
|---|---|---|---|
| V, one Jev call, the usual question | 0.677 | 73/110 | 34/110 |
| N, WaRF Jev: seven narrow checks per hunk | 0.714 | 67/110 | 20/110 |

Only N right on 18 items, only V right on 10, exact McNemar p 0.185; AUC N − V +0.017 [−0.016, +0.051].
The development set pointed the same way (+0.037 AUC). With the same rate of disagreement (13%) and the
same split (64/36), about 740 items give an 80% chance of p < 0.05. This set is built to supply about 520
new items.

## The frozen configuration (unchanged from the second test)

`../real-set/jev-narrow/run_narrow.py`, model `jev-latest` via OpenRouter, questions and states
unchanged, run with `--items power-set/items.jsonl --out power-set/answers.jsonl`. The input is the
30-line diff with function context that WaRF sends.

| Arm | Score | REJECT when (thresholds from `../real-set/jev-narrow/frozen.json`, fixed on dev) |
|---|---|---|
| **N, WaRF Jev** | each of the 7 checks' highest p(YES) over the hunks, then the mean of their logits (p clipped to [0.01, 0.99]) | score ≥ −1.7337654334212138 |
| V, one Jev | p(REJECT) of the usual question on the whole change | p ≥ 0.79 |

## The set (built before any Jev call)

- **Defective candidates** (`build_power.py`, git only): changes to C++ files in the gismo6 history that
  a later fix of kind "defect" blamed (B-SZZ, `../laya-sweep/labels.jsonl`). One file per commit, input
  at most 20 000 characters, no commit of any earlier set (including all confirm-set candidates and
  controls). Two tiers, each shuffled with a fixed seed, tier 1 first:
  - tier 1, the confirm-set rules: fix within 180 days, at most 5 files, subject names a bug;
  - tier 2, looser: fix within 365 days, at most 10 files, any subject.
- **Judges** (`judge_prompt.md`): two independent Claude agents who see the change and the fix and may
  read the repository with git. In order of the candidate list, judge A sees every candidate; judge B
  sees only those A calls "yes" and does not see A's verdict. A candidate is **defective** only if both
  say "yes". Judging stops once 260 are confirmed or the candidates run out.
- **Clean items:** one control per defect from `clean_pool.jsonl` (every added non-blank line still
  blamed on its commit at origin/dev; `../hard-set/build_hard.py survives()`), matched by commit date
  and then input size exactly as in `../confirm-set/select_confirm.py`.
- Neither the judges nor the selection see any Jev answer. Jev never sees the fix or a label.

## Primary analysis (new items only)

Balanced accuracy of N and V at the frozen thresholds, on the new items of this set.
- **N wins** if N's balanced accuracy is higher and the exact two-sided McNemar test on the items where
  exactly one arm is right gives p < 0.05.
- **Not shown** if N is higher but p ≥ 0.05.
- **No case** otherwise.

At the expected 520 items the power is about 65%; it depends on how many defects the judges confirm.
The 220 confirm items are kept out of the primary because they were already looked at once for this
comparison.

## Secondary, frozen now

- AUC of N minus AUC of V, paired bootstrap stratified by class (2000 resamples, seed 4).
- AUC within thirds of added-line count, and AUC of the added-line count alone.
- The same McNemar on the pooled set (these items plus the 220 confirm items), reported with the note
  that it is a second look at a hypothesis already tested once.
- Caught and false alarms for each arm.

## Status

- 2026-11-11: preregistration written; no item built yet.
- 2026-11-11, mining done (`build_power.py`, `build.log`; git only): 454 defective candidates, all tier 2. The
  319 unused tier-1 commits all fail the input-size limit or the input build, which is why the confirm set
  had not taken them. Only 100 of the 454 fixes name a bug in their subject. Clean pool: 203, below the
  ~260 needed (the git history runs out after excluding every earlier set).
  Expected yield: the confirm-set rules confirmed 30%; with looser rules perhaps 15-20%, so roughly
  70-110 defects and 140-220 new items, against the 520 planned. The primary would then have about
  25-35% power. Stopped here before any judge or Jev call; `judge_inputs/A_00..A_09.md` were written
  but not sent.
