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

---

# Second test, preregistered 2026-11-09 before any call: Jev with narrow questions

A separate test on the same 220 items. The Opus result above is unchanged. The development lead is in `../real-set/DEV.md` (2026-11-09) and `../real-set/jev-narrow/`.

**Frozen setup.** `../real-set/jev-narrow/run_narrow.py` (questions and states unchanged; only `--items`/`--out` added), on this set's `items.jsonl` (the 30-line diff WaRF sends), model `jev-latest`.

| Arm | Score |
|---|---|
| **N, narrow checks** | Seven narrow YES/NO checks, asked per hunk. Take each check's highest p over the hunks, then the mean of their logits (p clipped to [0.01, 0.99]). |
| V, the usual question | The usual WaRF question's p(REJECT) on the whole change |

**Primary.** AUC of N minus AUC of V, with a paired bootstrap stratified by class (2000 resamples, seed 4).
- **N wins** if the lower bound of the 95% interval is above 0.
- **Not shown** if the difference is positive but the interval includes 0.
- **No case** otherwise.

**Secondary, frozen before the run.**
- Balanced accuracy at the development set's thresholds (`../real-set/jev-narrow/frozen.json`): V REJECT at p ≥ 0.79, N REJECT at score ≥ −1.734. Compared with exact McNemar.
- AUC within thirds of added-line count.

## Result of the second test (2026-11-09, `jev-narrow/score_jev_confirm.py`)

There were 524 calls (220 whole changes, 304 hunks), no errors, costing $0.066.

| | AUC | AUC within thirds of added lines | BA at the dev threshold | Caught | False alarms |
|---|---|---|---|---|---|
| V, the usual question | 0.753 | 0.650 | 0.677 | 73/110 | 34/110 |
| N, narrow checks | 0.771 | 0.688 | 0.714 | 67/110 | 20/110 |
| (added lines alone) | 0.790 | | | | |

- **Primary:** N − V = +0.017 [−0.016, +0.051]. **Preregistered verdict: not shown.**
- **Secondary:** only N right 18, only V right 10, McNemar p 0.185.
- **Jev does worse on this set than on the development set** (0.753 vs 0.856). Both arms rank below a simple count of added lines.

---

# Third test, preregistered 2026-11-11 before any call: WaRF Jev with two Jev versions as seats

A separate test on the same 220 items; the results above are unchanged. `jev-1.13` (`typesafe/jev-1.13-20260917`) has never been run on this set. Development: `../real-set/DEV.md` (2026-11-11), `../real-set/jev-narrow/versions/`.

**Frozen setup.** `../real-set/jev-narrow/versions/run_version.py jev-1.13 --items .warf-experiments/confirm-set/items.jsonl --out .warf-experiments/confirm-set/jev-narrow/answers_jev-1.13.jsonl`: the second test's request unchanged, only the model differs. The `jev-1.14` answers are the second test's `jev-narrow/answers.jsonl`, reused as they are.

| Arm | Score | REJECT when (fixed on dev) |
|---|---|---|
| **M, two-version WaRF Jev** | mean of N(jev-1.13) and N(jev-1.14); N as in the second test | M ≥ −1.916991419800014 (`frozen_mix.json`, dev BA 0.849) |
| N, WaRF Jev with jev-1.14 | as in the second test | N ≥ −1.7337654334212138 |
| V, one Jev | as in the second test | p ≥ 0.79 |

**Primary.** Balanced accuracy of M against N at the frozen thresholds.
- **M wins** if M's balanced accuracy is higher and the exact two-sided McNemar test gives p < 0.05.
- **Not shown** if M is higher but p ≥ 0.05. **No case** otherwise.

**Secondary.** M against V the same way; AUC of M minus AUC of N, paired bootstrap stratified by class (2000, seed 4); Spearman between N(jev-1.13) and N(jev-1.14). On dev the gain was +0.005 AUC and the versions correlated 0.969, so the expected result is "not shown"; this test exists because it costs about $0.07 and no judging.

## Result of the third test (2026-11-11, `jev-narrow/score_mix_confirm.py`)

524 calls to jev-1.13, no errors, $0.066. N(1.13) and N(1.14) correlate 0.964 (Spearman).

| | BA at the dev threshold | Caught | False alarms | AUC |
|---|---|---|---|---|
| M, two-version WaRF Jev | 0.718 | 70/110 | 22/110 | 0.773 |
| N, WaRF Jev (1.14) | 0.714 | 67/110 | 20/110 | 0.771 |
| V, one Jev | 0.677 | 73/110 | 34/110 | 0.753 |

- **Primary:** M − N = +0.005 BA; only M right 6, only N right 5, McNemar p 1.000. **Preregistered verdict: not shown.**
- Secondary: M − V = +0.041 BA, 20 vs 11, p 0.150, not shown. AUC M − N +0.002 [−0.009, +0.014].

---

# Fourth test, preregistered 2026-11-11 before any call: mixed-version Jev panels in WaRF

Teymur's design: a WaRF panel of personas on Jev, about half on `jev-1.14` and the rest on `jev-1.13`. Same 220 items; the results above are unchanged. WaRF does the job: `warf.orchestrator.run_review` with WaRF's default vote aggregation (SPRT), uniform priors, no debate, every seat asked (`no_early_stop`, which leaves WaRF's verdict unchanged). Input: each item's `code` (the 30-line diff WaRF sends) with its domain and context. Runner: `jev-panels/run_panels.py`.

| Arm | Seats (WaRF's default personas, in their default order) |
|---|---|
| **P5** | SKEPTIC, ADVOCATE, AUDITOR on jev-1.14; TEST-FOCUSED, BOUNDARY on jev-1.13 |
| **P3** | SKEPTIC, ADVOCATE on jev-1.14; AUDITOR on jev-1.13 |
| V, one Jev (from the second test) | the usual question, REJECT at p ≥ 0.79 (67.7%) |
| N, WaRF Jev narrow checks (from the second test) | REJECT at N ≥ −1.734 (71.4%) |

**Primary.** Balanced accuracy of WaRF's decision for P5 and for P3, each against V, exact two-sided McNemar, Holm-corrected over the two panels.
- A panel **wins** if its balanced accuracy is higher and its Holm-adjusted p < 0.05.
- **Not shown** if higher but the adjusted p ≥ 0.05. **No case** otherwise.

**Secondary.** Each panel against N the same way (uncorrected, reported only); AUC of each panel's mean p(REJECT) over its seats; agreement between seats on different versions and on the same version; caught and false alarms.

## Result of the fourth test (2026-11-11, `jev-panels/score_panels.py`, `jev-panels/score.log`)

220 reviews per panel, no errors, both versions answering as assigned; cost P5 $0.133, P3 $0.078 (P3 includes a 2-item smoke test, the first two items of the run).

| | Right (BA) | Caught | False alarms |
|---|---|---|---|
| V, one Jev | 67.7% | 73/110 | 34/110 |
| N, WaRF Jev narrow checks | 71.4% | 67/110 | 20/110 |
| P5, WaRF: 3 personas on 1.14 + 2 on 1.13 | 69.5% | 85/110 | 42/110 |
| P3, WaRF: 2 personas on 1.14 + 1 on 1.13 | 68.6% | 86/110 | 45/110 |

- **Primary:** P5 − V +1.8 points (13 vs 9, p 0.523, Holm 1.000); P3 − V +0.9 points (13 vs 11, p 0.839, Holm 1.000). **Preregistered verdict: not shown for both.**
- Secondary: P5 − N −1.8 points (p 0.644), P3 − N −2.7 points (p 0.461). AUC of the mean seat p: P5 0.763, P3 0.756 (N 0.771, V 0.753).
- Seats on different versions agree no less than seats on the same version (66-88% vs 62-90%): the persona moves a seat's answer as much as the version does, and both move it little.

---

# Fifth test, preregistered 2026-11-11 before any call: the mixed-version Jev panel after WaRF has learned

The fourth test ran WaRF's panel untrained (uniform priors, no history). WaRF's design learns from labelled reviews, in two ways: vote mode updates each seat's reliability (`apply_oracle`, Beta posteriors per domain), and log-odds mode (ADR 0001) calibrates each seat's p(REJECT) with Platt scaling and pools the evidence per model group, so the jev-1.14 seats count as one source and the jev-1.13 seats as another. Runner: `jev-learned/run_learned.py`.

**Learning (development set only).** The P5 panel of the fourth test (SKEPTIC, ADVOCATE, AUDITOR on jev-1.14; TEST-FOCUSED, BOUNDARY on jev-1.13), starting from uniform priors, reviews the 132 items of `../real-set/items.jsonl` with `run_review` (vote mode, no debate, every seat asked). Each review is labelled with its known answer as WaRF's inline ground-truth path does: `apply_oracle(..., "DEVELOPER")` updates the profile, and `append_session` writes the labelled session to `jev-learned/dev_sessions.jsonl`. Nothing from the 220 items enters the learning.

**Arms on the 220 items** (no learning during the test; every seat asked):

| Arm | WaRF configuration |
|---|---|
| **LV** | vote mode with the learned profile |
| **LO** | `aggregate="logodds"`, calibration from `dev_sessions.jsonl` |
| P5 (fourth test) | vote mode, uniform priors (69.5%) |
| V, N | as in the second test (67.7%, 71.4%) |

**Primary.** Balanced accuracy of WaRF's decision for LV and for LO, each against V, exact two-sided McNemar, Holm-corrected over the two arms. Wins / not shown / no case as in the fourth test.

**Secondary.** Each arm against N and against untrained P5 (uncorrected); the learned seat weights; caught and false alarms.

The 220 items have now been used by four earlier Jev tests; the comparisons are new, but a reader should weigh this fifth look accordingly.

## Result of the fifth test (2026-11-11, `jev-learned/score_learned.py`)

Learning on dev: 132 reviews, $0.077 (`dev_sessions.jsonl`, `profiles/learned_frozen.json`). Test: 220 reviews per arm, no errors, $0.133 each. Checked: no confirm item or commit is in the dev log, and no test session carries a label.

| | Right (BA) | Caught | False alarms |
|---|---|---|---|
| V, one Jev | 67.7% | 73/110 | 34/110 |
| P5, untrained (fourth test) | 69.5% | 85/110 | 42/110 |
| LV, vote mode, learned weights | 69.1% | 85/110 | 43/110 |
| **LO, log-odds mode, calibrated on dev** | **73.2%** | 83/110 | 32/110 |
| N, WaRF Jev narrow checks | 71.4% | 67/110 | 20/110 |

- **Primary:** LV − V +1.4 points (13 vs 10, p 0.678, Holm 0.678): not shown. **LO − V +5.5 points (16 vs 4, p 0.012, Holm 0.024): LO WINS, the preregistered verdict.**
- Secondary: LO − untrained P5 +3.6 points (12 vs 4, p 0.077); LO − N +1.8 points (19 vs 15, p 0.608). LV − P5 −0.5 points.
- The seats' answers are the same in LV and LO (mean-p AUC 0.765 in both); what differs is WaRF's aggregation: calibrated evidence pooled per Jev version instead of counted votes.
- **Caveat:** this is the sixth primary comparison made on these 220 items for Jev (second test 1, third 1, fourth 2, fifth 2). Bonferroni over all six would put LO's p at 0.072. A fresh set is needed before calling LO better than one Jev with confidence.
