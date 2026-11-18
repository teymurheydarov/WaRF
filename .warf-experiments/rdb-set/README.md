# Fresh-set test: LO with a size seat (LO+SIZE) against LO on real RocksDB bugs

Written 2026-11-13 while the git-only mining ran, before any candidate was looked at, judged or
reviewed. It is not changed after the first judge call on this set, except for the one line marked
TARGET below, which is set before judging starts. Later changes are added below with their date and
reason and never enter the primary result.

## Why this test

Over the 844 labelled changes of G+Smo, MFEM and KeePassXC, deciding each project with a calibration
from the other two (`../pooled-dev/`), LO with a size seat was right 80.3% of the time, LO 77.7%: only
LO+SIZE right on 45, only LO on 23, p 0.010, with a gain on every project. All three sets had been
seen before, so the gain needs a fresh project.

The set comes from RocksDB (github.com/facebook/rocksdb, a C++ storage engine, cloned 2026-11-13 into
`C:\workdir\warf\repos\rocksdb`, read with git only).

## The frozen configuration (`freeze_rdb.py`, run before any RocksDB change is judged or reviewed)

Training data: all 844 labelled changes (G+Smo 352, MFEM 300, KeePassXC 192); nothing from RocksDB.

- **LO**: WaRF's `run_review(..., aggregate="logodds")` with the five persona seats (SKEPTIC, ADVOCATE,
  AUDITOR on jev-1.14; TEST-FOCUSED, BOUNDARY on jev-1.13), no debate, every seat asked, calibrated from
  `calib_sessions.jsonl`.
- **LO+SIZE** (candidate): the same five answers plus the size seat, p(REJECT) = sigmoid(ln(1 + added)
  - 3) with `added` the added-line count of the file's diff in WaRF's input, as its own group
  (provider `size`). Decided with WaRF's Calibrator (the persona seats' and the size seat's
  histories, `calib_sessions.jsonl` + `calib_size.jsonl`), pool_evidence, logodds_boundary and
  logodds_decision on the stored answers. The offline rebuild of LO must reproduce every logged LO
  decision, or the test stops.
- **SIZE** and **V1** (references): the size seat alone, and one Jev seat (the usual question on
  jev-1.14, `run_narrow.py --whole-only`), each Platt-calibrated on the 844 changes.

The input is what WaRF sends: the file's diff with 30 lines of context and the enclosing function
bodies, at most 20 000 characters.

## The set, as `../kpx-set/README.md`

- **Defective candidates** (`build_rdb.py`, git only): non-merge commits on `origin/main` whose subject
  names a bug and that touch at most 5 files are fixes; their deleted non-cosmetic C++ lines are blamed
  in the fix's parent (B-SZZ). A blamed (commit, file) is a candidate when the fix came within 180 days,
  the commit is not a merge or revert and was made before 2025-11-12. One file per commit, up to 900.
- **Judges** (`judge_prompt.md`, the same text with RocksDB's path): two independent Claude agents. Judge
  A sees candidates in list order; judge B sees only those A calls "yes", without A's verdict. Defective
  only if both say "yes".
- **TARGET**: **400** confirmed defects (set 2026-11-13 before judging, chosen by Teymur for power); judging
  stops there or when candidates run out.
- **Clean controls**: non-merge commits on `origin/main` made 2014-01-01..2025-11-12 whose every added
  non-blank line in the file is still blamed on that commit at `origin/main`; one per defect, matched
  by date, then input size (`select_rdb.py`).
- Neither the judges nor the selection see any Jev answer; Jev never sees a fix or a label.

## Primary analysis

Balanced accuracy of LO+SIZE and LO on all items of this set.
- **LO+SIZE wins** if its balanced accuracy is higher and the exact two-sided McNemar test on the items
  where exactly one is right gives p < 0.05.
- **Not shown** if LO+SIZE is higher but p >= 0.05. **No case** otherwise.

Power, if the pooled effect holds (8.1% of changes discordant, 2:1 for LO+SIZE): about 28% with
150 + 150 changes, 48% with 250 + 250, 71% with 400 + 400.

## Secondary, frozen now

LO+SIZE against SIZE (is it more than size?); LO against V1; LO+SIZE against V1; each arm's balanced
accuracy, caught and false alarms; the result on defects the judges call visible from the diff.

## Status

- 2026-11-13: RocksDB cloned; mining started (git only); this preregistration written; `freeze_rdb.py`
  run (844 training changes); `score_rdb.py` written and dry-run on KeePassXC's stored data.
- 2026-11-13, mining done (`build_rdb.py`, `build.log`; git only): all 3,272 fix commits visited, 869 defective
  candidates (median input 8.2k characters) and 700 clean controls. One git output with a byte that is not
  UTF-8 could not be read; that candidate was skipped. TARGET set to 400 before judging.
- 2026-11-13, judging done and set frozen (`judge.py`, `judgements/`, `select_rdb.py`, `select.log`): judge A
  judged all 869 candidates (475 yes); judge B judged those 475 (437 yes). The first 400 confirmed in list
  order are kept, with 400 clean controls: 800 items. Visibility: diff 250, needs_other_file 120,
  not_visible 3, split 27. No Jev call has been made on this set.
- 2026-11-13, **problem found before any Jev call**: the clean controls are much smaller changes than the
  defects. Median added lines 34 (defective) against 3 (clean); 54% of clean controls add at most 3 lines,
  9% of defects do; the added-line count alone separates them with AUC 0.859. The date matching is also
  poor (median gap 712 days), because the survival screen leaves few clean controls before 2017. The same
  added-line gap is in every earlier set (AUC 0.79-0.87; clean controls 55-68% with at most 3 added
  lines): the survival screen ("every added line still at HEAD") selects small changes. A size seat on
  this set would mostly measure how the set was built. Jev is not run until this is decided.

## Amendment (2026-11-13, before any Jev call on this set; decided by Teymur)

The clean controls are rebuilt so that they match the defects on the added-line count. The 400 confirmed
defects, the arms, the training data, the primary analysis and the decision rule stay as fixed above.

- **Clean pool** (`build_clean_matched.py`, git only): non-merge, non-revert commits on `origin/main` made
  before 2025-11-12 (no lower date bound, so the early years can be matched), one C++ file each, not the
  commit of any defective candidate and not a fix commit; the survival screen is unchanged (every added
  non-blank line still blamed on the commit at `origin/main`) and the input is at most 20 000 characters.
  (Commit, file) pairs are drawn in a seeded random order, pre-sorted into added-line bins
  1, 2, 3, 4-5, 6-8, 9-12, 13-18, 19-27, 28-40, 41-60, 61-90, 91-135, 136-200, 201+ by `git log --numstat`,
  and screened until each bin holds twice as many survivors as defects in it (or the bin's pairs run out).
  The bin of a survivor is taken from the added-line count of its WaRF input.
- **Matching** (`select_matched.py`): defects in date order; each takes the free control in its own bin
  with the nearest commit date (ties: nearest input size). If its bin is empty it takes the nearest
  non-empty bin.
- The first clean pool and items stay on disk as `clean_pool.jsonl` / `items_unmatched.jsonl` for
  reference; the test runs on the matched `items.jsonl`.
- Expectation written down now: on a set matched on added lines the size seat carries little information,
  so LO+SIZE is expected to gain little or nothing; the test now asks whether the size seat helps on
  changes of equal size.
- 2026-11-13, matched controls mined (`build_clean_matched.py`, `build_matched.log`; git only): 28,519
  (commit, file) pairs, 5,458 screened, 595 survivors kept. Large surviving changes are rare: the bins of
  91-135, 136-200 and 201+ added lines got 20, 6 and 2 controls for 37, 33 and 24 defects.
- 2026-11-13, matched set frozen (`select_matched.py`, `select.log`): 400 + 400 items; 109 defects took a
  control from a neighbouring (smaller) bin. Added lines median 34 (defective) against 30 (clean), AUC of
  the added-line count 0.558 (0.859 before). The price is the date matching: median gap 1,414 days, max
  4,378, since large surviving changes are mostly recent while the defects are mostly 2012-2016. No Jev
  call has been made on this set.

## Result (2026-11-13, matched set, `score_rdb.py`, `score.log`, `score.json`)

LO: 800 reviews through WaRF (`sessions_LO.jsonl`), all five seats and both Jev versions every time,
$0.499; V1: 800 calls, no errors, $0.116. The offline rebuild of LO gives all 800 logged decisions.

| 800 RocksDB items, matched on added lines | Right (BA) | Caught | False alarms |
|---|---|---|---|
| V1, one Jev | 66.6% | 228/400 | 95/400 |
| SIZE alone | 50.2% | 319/400 | 317/400 |
| **LO, WaRF log-odds panel** | **69.0%** | 243/400 | 91/400 |
| LO+SIZE | 64.8% | 309/400 | 191/400 |

- **Primary:** LO+SIZE − LO −4.2 points; only LO+SIZE right 75, only LO right 109; exact McNemar p 0.015.
  **Preregistered verdict: no case.** On changes of equal size the size seat hurts: calibrated on sets
  where clean meant small, it rejects large clean changes (false alarms 91 → 191).
- SIZE alone is at chance (50.2%), so the matching removed the size signal.
- LO − V1 +2.4 points (54 against 35, p 0.056): WaRF's panel stays ahead of one Jev on equal-size changes,
  but the gap and both levels are smaller than on the earlier, size-confounded sets (LO 73-82% there).
- The earlier sets' accuracies were inflated by the size gap between defects and clean controls; on this
  set Jev-based reviewing is right about two times in three.
- Correction (2026-11-14) to the last bullet above, which overstated it: restricted to changes with at least
  10 added lines (few clean ones: 21, 25 and 11), LO's logged decisions score G+Smo 66.1% (73.2% on all),
  MFEM 79.9% (80.0%), KeePassXC 78.1% (82.3%), RocksDB matched 71.0% (69.0%). The tiny clean controls
  made G+Smo and KeePassXC a few points easier, MFEM hardly; RocksDB is harder for Jev on its own, not
  only because of the matching.
