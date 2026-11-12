# Second-repository test: LO against one Jev on real MFEM bugs

This file was fixed on 2026-11-12, before any item of this set existed and before any judge or reviewer
saw any of it. It is not changed after the first Jev call on this set. Later changes are added below
with their date and reason and never enter the primary result.

## Why this test

On the 220 fresh G+Smo items (`../confirm-set/README.md`, fifth test), LO, WaRF's log-odds Jev panel,
beat one Jev: 73.2% against 67.7% balanced accuracy, only LO right on 16 items, only one Jev on 4,
exact McNemar p 0.012. It was the sixth comparison made on those items (Bonferroni over six: 0.072), so
it needs a new set. The G+Smo history is exhausted (`../power-set/README.md`). This set comes from
another C++ project, MFEM (github.com/mfem/mfem, cloned 2026-11-12 into `C:\workdir\warf\repos\mfem`,
read with git only).

## The frozen configuration

**LO, exactly as tested** (`../confirm-set/jev-learned/run_learned.py`): WaRF's default personas
SKEPTIC, ADVOCATE, AUDITOR on `jev-1.14` and TEST-FOCUSED, BOUNDARY on `jev-1.13`;
`run_review(..., aggregate="logodds", log_path=../confirm-set/jev-learned/dev_sessions.jsonl)`, no
debate, every seat asked. Its calibration is the one learned on the 132 G+Smo dev items; nothing from
MFEM enters it. So this test also asks whether a calibration learned on one project carries over to
another.

**V, one Jev, as tested**: `../real-set/jev-narrow/run_narrow.py` (verdict + seven narrow checks, whole
change and each hunk), the usual question's p(REJECT) on the whole change, REJECT at p ≥ 0.79
(`../real-set/jev-narrow/frozen.json`).

**N, WaRF Jev narrow checks** (secondary): from the same run, REJECT at N ≥ −1.7337654334212138.

The input is what WaRF sends: the file's diff with 30 lines of context and the enclosing function
bodies (`../laya-five/run_five.py prepare`), at most 20 000 characters.

## The set (built before any Jev call)

- **Defective candidates** (`build_mfem.py`, git only): non-merge commits on `origin/master` whose
  subject names a bug (the confirm set's regular expression) and that touch at most 5 files are fixes.
  Their deleted non-cosmetic lines in C++ files (not blank, punctuation or comment) are blamed in the
  fix's parent (B-SZZ). A blamed (commit, file) is a candidate when the fix came within 180 days, the
  commit is not a merge or revert, and it was made before 2025-11-12. One file per commit, shuffled
  with a fixed seed.
- **Judges** (`judge_prompt.md`, as `../power-set/judge_prompt.md` with MFEM's path): two independent
  Claude agents who see the change and the fix and may read the repository with git. Judge A sees
  candidates in list order; judge B sees only those A calls "yes", without A's verdict. A candidate is
  defective only if both say "yes". Judging stops at **150 confirmed defects** or when candidates run out.
- **Clean controls**: non-merge commits on `origin/master` made 2014-01-01..2025-11-12 whose every added
  non-blank line in the file is still blamed on that commit at `origin/master`. One per defect, matched
  by commit date, then input size, as `../confirm-set/select_confirm.py`.
- Neither the judges nor the selection see any Jev answer; Jev never sees a fix or a label.

## Primary analysis

Balanced accuracy of LO and V on all items of this set.
- **LO wins** if LO's balanced accuracy is higher and the exact two-sided McNemar test on the items where
  exactly one is right gives p < 0.05.
- **Not shown** if LO is higher but p ≥ 0.05. **No case** otherwise.

With 150 + 150 items, the power is about 95% if the G+Smo effect holds (16:4 of 9% of items) and about
55% if it is half as large; if fewer than 150 defects are confirmed, the result is reported with the
actual size.

## Secondary, frozen now

LO against N; N against V; AUC of the added-line count, of V and of LO's mean seat p; caught and false
alarms for each arm; the result on defects the judges call visible from the diff.

## Status

- 2026-11-12: preregistration written; MFEM cloned; no item built yet.
- 2026-11-12, mining done (`build_mfem.py`, `build.log`; git only): 600 defective candidates (median input
  8.2k characters; mostly fem/, mesh/, linalg/) and 500 clean controls. Judging in rounds of judge A, then
  judge B on A's "yes", until 150 are confirmed.
- 2026-11-12, judging done and set frozen (`judge.py`, `judgements/`, `select_mfem.py`, `select.log`): judge A
  judged the first 360 candidates (157 yes); judge B judged those 157 (151 yes). The first 150 confirmed in
  list order were kept (one more was confirmed beyond the target), with 150 clean controls (date gap median
  90 days, max 179): 300 items. Visibility: diff 87, needs_other_file 51, split 12. 240 candidates were never
  judged. No Jev call has been made on this set.

## Result (2026-11-12, `score_mfem.py`, `score.log`, `score.json`)

LO: 300 reviews through WaRF (`run_jev.py LO`, `sessions_LO.jsonl`), both Jev versions answering, $0.196;
the calibration log was unchanged after the run. V and N: 732 calls (`answers_narrow.jsonl`), no errors,
$0.096.

| 300 MFEM items | Right (BA) | Caught | False alarms |
|---|---|---|---|
| V, one Jev | 75.3% | 94/150 | 18/150 |
| N, WaRF Jev narrow checks | 74.3% | 88/150 | 15/150 |
| **LO, WaRF log-odds panel** | **80.0%** | 112/150 | 22/150 |

- **Primary:** LO − V +4.7 points; only LO right 23, only V right 9; exact McNemar p 0.020.
  **Preregistered verdict: LO WINS.**
- Secondary: LO − N +5.7 points (29 vs 12, p 0.012); N − V −1.0 points (11 vs 14, p 0.69).
- AUC: added lines 0.866, V 0.863, N 0.865, LO's mean seat p 0.883: Jev's ranking is still mostly change
  size; LO's gain is in the decision, not in a better ranking.
- The 87 defects visible from the diff: V 80.8%, N 80.1%, LO 85.2% (caught 64, 61, 74 of 87).
- LO's calibration was learned only on G+Smo, so it carried over to another project.
- LO asks five seats where V asks one: about $0.00065 against $0.00013 per review.
