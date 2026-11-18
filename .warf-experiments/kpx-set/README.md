# Fresh-set test: the jointly fitted calibrator (JOINT) against LO on real KeePassXC bugs

This file was fixed on 2026-11-12, before any item of this set existed and before any judge or reviewer
saw any of it. It is not changed after the first Jev call on this set. Later changes are added below
with their date and reason and never enter the primary result.

## Why this test

On MFEM, a calibrator that fits the seats and the change size together (JOINT, `../size-seat/`)
was right 84.3% of the time, LO 78.7% (27 against 10, p 0.008). MFEM was not fresh: LO's decisions
there had been seen. The controls showed that most of the gain came from fitting the two Jev
versions' weights together; the size added 2.6 points (p 0.26). This test asks both questions on
a set nobody has seen.

The set comes from KeePassXC (github.com/keepassxreboot/keepassxc, a C++/Qt password manager, cloned
2026-11-12 into `C:\workdir\warf\repos\keepassxc`, read with git only). It is not numerical code, unlike
G+Smo and MFEM.

## The frozen configuration (`freeze.py`, run before any KeePassXC item exists)

The training data is every labelled item so far: 352 G+Smo (dev 132, confirm 220) and 300 MFEM, 652
in all, with their five persona seats as WaRF logged them.

- **LO**: WaRF's `run_review(..., aggregate="logodds")` with the five persona seats (SKEPTIC, ADVOCATE,
  AUDITOR on jev-1.14; TEST-FOCUSED, BOUNDARY on jev-1.13), no debate, every seat asked, calibrated
  from `calib_sessions.jsonl` (the 652 items' votes and labels).
- **JOINT** (primary candidate): from the same five seats' answers, one logistic regression with
  inputs [1, mean ln((1-p)/p) of the jev-1.14 seats, the same for jev-1.13, -(ln(1 + added) - 3)],
  weights fitted on the 652 items and frozen in `frozen.json`; APPROVE if its log-odds minus the
  training base rate is at least the domain tau. The added-line count is that of the file's diff in
  WaRF's input (above its separator).
- **JOINT-noSize** (secondary): the same without the size input, weights frozen too.
- **SIZE** (secondary): the size input alone, Platt-calibrated as a WaRF seat on the 652 items.
- **V1, one Jev** (secondary): the usual question on the whole change, jev-1.14
  (`../real-set/jev-narrow/run_narrow.py`, whole change only), Platt-calibrated on the 652 items.

The input is what WaRF sends: the file's diff with 30 lines of context and the enclosing function
bodies (`../laya-five/run_five.py prepare`), at most 20 000 characters.

## The set (built before any Jev call), as `../mfem-set/README.md`

- **Defective candidates** (`build_kpx.py`, git only): non-merge commits on `origin/develop` whose
  subject names a bug and that touch at most 5 files are fixes; their deleted non-cosmetic C++ lines are
  blamed in the fix's parent (B-SZZ). A blamed (commit, file) is a candidate when the fix came within
  180 days, the commit is not a merge or revert and was made before 2025-11-12. One file per commit.
- **Judges** (`judge_prompt.md`, MFEM's text with KeePassXC's path): two independent Claude agents. Judge
  A sees candidates in list order; judge B sees only those A calls "yes", without A's verdict. Defective
  only if both say "yes". Judging stops at **150 confirmed defects** or when candidates run out.
- **Clean controls**: non-merge commits on `origin/develop` made 2014-01-01..2025-11-12 whose every
  added non-blank line in the file is still blamed on that commit at `origin/develop`; one per defect,
  matched by date, then input size (`select_kpx.py`).
- Neither the judges nor the selection see any Jev answer; Jev never sees a fix or a label.

## Primary analysis

Balanced accuracy of JOINT and LO on all items of this set.
- **JOINT wins** if its balanced accuracy is higher and the exact two-sided McNemar test on the items
  where exactly one is right gives p < 0.05.
- **Not shown** if JOINT is higher but p >= 0.05. **No case** otherwise.

If fewer than 150 defects are confirmed, the result is reported with the actual size.

## Secondary, frozen now

JOINT-noSize against LO (is the joint fit alone enough?); JOINT against JOINT-noSize (does the size
add?); JOINT against SIZE (is the gain more than size?); each arm's balanced accuracy, caught and false
alarms, including V1; the offline rebuild of LO must reproduce WaRF's logged LO decisions.

## Status

- 2026-11-12: preregistration written; KeePassXC cloned; no item built yet.
- 2026-11-12, mining done (`build_kpx.py`, `build.log`; git only): all 844 fix commits visited, only 200
  defective candidates (median input 7.0k characters; mostly src/gui, src/core) and 500 clean controls.
  At MFEM's rate of confirmation this gives about 80 defects, fewer than the target of 150; all 200 are
  judged, and the result is reported with the actual size, as fixed above.
- 2026-11-12, judging done and set frozen (`judge.py`, `judgements/`, `select_kpx.py`, `select.log`): judge A
  judged all 200 candidates (100 yes); judge B judged those 100 (96 yes). All 96 confirmed are kept, with 96
  clean controls (date gap median 96 days, max 1057): 192 items. Visibility: diff 56, needs_other_file 31,
  not_visible 1, split 8. No Jev call has been made on this set. With 96 + 96 items the power is lower than
  planned; the result is reported at this size.

## Result (2026-11-12, `score_kpx.py`, `score.log`, `score.json`)

LO: 192 reviews through WaRF (`run_jev.py LO`, `sessions_LO.jsonl`), every review with all five seats and both
Jev versions, $0.110; the calibration log was unchanged after the run. V1: 192 calls (`answers_V1.jsonl`),
no errors, $0.026. The offline rebuild of LO gives all 192 of WaRF's logged decisions.

| 192 KeePassXC items | Right (BA) | Caught | False alarms |
|---|---|---|---|
| V1, one Jev | 77.6% | 72/96 | 19/96 |
| SIZE alone | 80.2% | 73/96 | 15/96 |
| LO, WaRF log-odds panel | 82.3% | 80/96 | 18/96 |
| JOINT-noSize | 79.2% | 81/96 | 25/96 |
| **JOINT** | **83.9%** | 83/96 | 18/96 |

- **Primary:** JOINT − LO +1.6 points; only JOINT right 13, only LO right 10; exact McNemar p 0.68.
  **Preregistered verdict: not shown.**
- Secondary: JOINT-noSize − LO −3.1 points (3 vs 9, p 0.15): the joint fit of the two versions, which
  carried most of the MFEM gain, does not carry over; JOINT − JOINT-noSize +4.7 (14 vs 5, p 0.064);
  JOINT − SIZE +3.6 (15 vs 8, p 0.21); LO − V1 +4.7 (14 vs 5, p 0.064).
- So on a fresh project the gain over LO is small and not significant; what JOINT adds there comes from
  the size input, not from refitting the seats. LO, unchanged and calibrated on G+Smo and MFEM, is right
  82.3% of the time on a non-numerical C++ project, 4.7 points above one Jev.
