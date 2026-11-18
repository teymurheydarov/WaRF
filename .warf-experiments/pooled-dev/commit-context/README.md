# Commit context: show each file's reviewers the rest of its commit

Written 2026-11-17, before any Jev call with commit context. Not changed after the first such call, except
where marked; later changes are added below with their date and never enter the primary result.

## Why

WaRF's `review-commit` reviews each changed file on its own, and no seat is shown the commit's other files.
On the two fresh sets the three-seat panel (PANEL3) catches 77-84% of the defects the judges call visible from
the diff, but only 57-64% of those that need another file to be seen (about 30% of all defects); judges often
name that file as "the same commit's X.cpp" (`../fewlabel/misses.log`). A reviewer of the commit has it.

The few-label question was looked at first (`../fewlabel/curve.log`, RocksDB and DuckDB only): WaRF without any
label from the project is within 0.7-2.4 points of full calibration and reaches it at about 20 labels per
class; a calibration prior from the other project does not help. That line was dropped.

## The feature (WaRF, uncommitted: `warf/commit_context.py`, `review-commit --commit-context`)

For each reviewed file, the commit's other files as a compact diff (`git show -U3`, WaRF's own `get_diff` and
`_parse_diff`), in diff order, whole while they fit in 8,000 characters; the first that does not fit is cut
after its last whole line (if at least 500 characters are left), every later one is only named. Every seat
sees it in its own block between the project context and the input; a LOCATE seat's options stay the reviewed
file's added lines. Tests: `tools/test_commit_context.py` (13/13 mutants killed).

## The test

- **Sets:** the frozen DuckDB and PPSSPP sets (800 changes each, `../../ddb-set/`, `../../pp-set/`), unchanged.
  Each item's commit context is built by `build_cc.py` with WaRF's code (`cc_ddb.jsonl`, `cc_pp.jsonl`,
  `build_cc.log`): DuckDB 701 items have other files, PPSSPP 614.
- **Arms:** PANEL3 as stored (BOUNDARY jev-1.13, LOCATE and CHECKLIST jev-1.14, each project's context, defect
  profile and checks) against **PANEL3+CC**: the same seats, the same context, plus the commit context.
  Items without other files have the same input in both arms, so PANEL3+CC uses the stored answers there.
- **Rule and calibration:** WaRF `logodds`, every seat asked, calibration within each set by stratified 10-fold
  cross-validation (seed 300 + repetition) from the arm's own answers, as in the fresh tests.
- **A call that fails** (for instance the input exceeding the model's context) is retried once by the runner's
  resume; a seat answer that still fails takes the stored answer without commit context, and is reported.

## Primary analysis

Balanced accuracy of PANEL3+CC and PANEL3 on the 1,600 changes of both projects (repetition 0), exact two-sided
McNemar test on the changes only one arm gets right, summed over both projects. **CC wins** if PANEL3+CC is
ahead and p < 0.05; **not shown** if ahead with p >= 0.05; **no case** otherwise.

## Secondary

- Each project alone, the same test.
- Catch rate on the defects the judges call needs_other_file, and on those visible from the diff; false alarms
  on clean changes; each arm on the items that have a commit context.
- Each seat's AUC with and without commit context.

## Disk

The two clones are partial (no checkout, blobs fetched only as needed: 174 MB and 82 MB) and are deleted after
the run; the commit contexts are stored here.

## Status

- 2026-11-17: preregistration written; feature and tests in WaRF; commit contexts built. No Jev call yet.
- 2026-11-17, found while building the contexts: `warf.vcs.get_diff` and `enrich_patch` lost a whole git output
  that was not valid UTF-8 (stdout None on Windows); fixed with lenient decoding (`errors="replace"`), test
  `tools/test_vcs.py` (fails without either half of the fix). The frozen items keep the code they were built
  with (10 PPSSPP candidates had the plain patch for this reason, `../../pp-set/README.md`).
- 2026-11-17: Jev run (`run_cc.py`): 1,315 reviews (DuckDB 701, PPSSPP 614), 3 seats each, no errors,
  27.1 M input tokens.

## Result (2026-11-17, `score_cc.py`, `score_cc.log`, `score_cc.json`)

| | DuckDB | PPSSPP |
|---|---|---|
| PANEL3 | 76.5% | 70.8% |
| PANEL3+CC | 78.4% | 69.0% |
| right only with CC / only without | 51 / 36, p 0.13 | 44 / 58, p 0.20 |
| needs_other_file defects caught | 85 -> 92 of 132 | 63 -> 56 of 111 |
| false alarms (of 400 clean) | 97 -> 93 | 119 -> 117 |

- **Primary: not shown.** Both projects: right only with CC 95, only without 94, exact McNemar p = 1.0. The
  two projects go opposite ways.
- **Seat AUCs (secondary):** the commit context helps LOCATE on both projects (DuckDB 0.837 -> 0.851, PPSSPP
  0.766 -> 0.782) and hurts the verdict seats (BOUNDARY 0.847 -> 0.836 and 0.777 -> 0.747; CHECKLIST 0.830 ->
  0.827 and 0.769 -> 0.749). A seat asked whether to merge seems to judge the whole commit, a question other
  than the label (this file); LOCATE's question stays tied to the file's own lines.
- **Exploratory, chosen after the result (`explore_locate.py`, no calls):** commit context for LOCATE only:
  DuckDB 77.4% (13 vs 6), PPSSPP 71.1% (19 vs 16), both 32 vs 22, p = 0.22. Positive on both but small; a
  test able to confirm an effect of this size would need several thousand changes.
- The two partial clones were deleted after the run (the commit contexts are stored here).
- 2026-11-17, after the run, from a cold review (fresh-reviewer): the closing "Also changed" line was not
  counted against the 8,000 characters (318 DuckDB and 189 PPSSPP contexts were longer, up to 76,381 for a
  1,384-file commit; Jev took them without error). WaRF now keeps 400 characters for that line and names files
  while they fit, then "and N more", so the whole context stays within the budget; the basis of the constants is
  stated in `warf/commit_context.py` and the spec. This test ran with the earlier rule, as preregistered; its
  result stands for that rule. The vcs test's enrich_patch check could not fail (the plain patch already holds
  the function's text) and now checks for the context block; the commit-context test gained checks for the new
  rule: 19/19 mutants killed (`tools/test_commit_context.py`).
