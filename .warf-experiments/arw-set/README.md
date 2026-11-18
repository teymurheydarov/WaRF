# Second fresh test: the three-seat question panel against LO with the same context, on Apache Arrow

Written 2026-11-16 while Arrow was being cloned, before any Arrow candidate was mined, judged or reviewed. It
is not changed after the first judge call, except where marked; later changes are added below with their date
and reason and never enter the primary result.

## Why this test

On DuckDB (`../ddb-set/`, the first fresh test) the three-seat panel (PANEL3: BOUNDARY, LOCATE, CHECKLIST) was
right on 76.5%, WaRF's five persona seats with the same context (LO-ctx) on 75.0%: 30 against 18 changes,
p 0.111, not shown. On RocksDB, where the panel was developed, 73.6% against 70.2%, p 0.002. The direction
replicated, the size did not. Teymur asked for a third project; Apache Arrow (github.com/apache/arrow, a C++
columnar data library; Claude's pick, Teymur left the choice open) was cloned 2026-11-16 into
`C:\workdir\warf\repos\arrow` (main branch only, no tags, no checkout, to spare disk space), read with git only.

## The set: DuckDB's procedure (`../ddb-set/README.md`), with these settings fixed now

- **Defective candidates** (`build_arw.py`): `../rdb-set/build_rdb.py`'s rules (the same subject rule for fixes,
  at most 5 files, B-SZZ blame, 180 days, one file per commit, input at most 20 000 characters, seeded order),
  cutoff **2025-11-16** (one year before the clone), up to **1,600** candidates (DuckDB's amended cap, set now),
  written one by one as they are found (`candidates_stream.jsonl`). Excluded paths: vendored or generated code
  (`cpp/thirdparty/`, any path containing `/vendored/` or `/generated/`).
- **Judges:** DuckDB's prompt with Arrow's repository (`judge_prompt.md`), two independent Claude agents, A in
  list order, B on A's yes without A's verdict, batches of 40 (`judge_agent_brief.md`).
- **History and test:** in list order, the first 40 confirmed defects are the history, the next 400 the test.
- **Clean controls:** DuckDB's procedure (matched on added-line bins, survival screen, nearest date), excluded
  paths as above.
- **Project context** (`arw_context.md`), **defect profile** (`defect_profile.md`) and **checks** (`checks.md`):
  written by fresh agents exactly as for DuckDB (`profile_prompt.md`, `checks_prompt.md` with "Arrow" for
  "DuckDB"); none sees a test item.

## The arms (as DuckDB's, `panel.py`)

PANEL3 (BOUNDARY jev-1.13; LOCATE jev-1.14 with the build question naming "a configuration Arrow supports";
CHECKLIST jev-1.14 with `checks.md`) and LO-ctx (the five persona seats), every seat shown the project
context, WaRF `run_review` with `logodds`, every seat asked. Calibration within Arrow by stratified 10-fold
cross-validation (seed 300 + repetition), as for DuckDB.

## Primary analysis

Balanced accuracy of PANEL3 and LO-ctx on the 800 test changes, repetition 0 (5-repetition means reported).
**PANEL3 wins** if it is higher and the exact two-sided McNemar test on the discordant changes gives p < 0.05;
**not shown** if higher with p >= 0.05; **no case** otherwise.

## Secondary, fixed now

- **Pooled over the two fresh projects:** the discordant counts of DuckDB's primary (30 for PANEL3, 18 for
  LO-ctx) added to Arrow's, one exact two-sided McNemar on the sums; "pooled wins" if PANEL3 is ahead and
  p < 0.05.
- DuckDB's secondaries: FIVE against LO-ctx, the defects visible from the diff, the pairs matched in their own
  added-line bin, each seat's AUC against the added-line count's AUC.

## Amendment (2026-11-16, after 19 candidates were mined and before any was judged)

The fix rule's `^fix` alternative tests the start of the subject, and every Arrow subject starts with an issue key
and component tags (`GH-48123: [C++][Parquet] Fix ...`), so the first run found only 552 fix commits of 19,548.
The rule is now applied to the subject after that prefix (`build_arw.subject`), which finds 2,870, as DuckDB's
and RocksDB's plain subjects did. Nothing else changes; the 19 streamed candidates were discarded and mining
restarted from the start of the same seeded order.

## Disk space

Teymur has about 41 GB free. The Arrow clone has no checkout; once the set is judged and the Jev run is done,
the clones downloaded for these tests (Arrow, DuckDB) are deleted, since the frozen sets carry everything the
scoring needs.

## Status

- 2026-11-16: preregistration written while the clone runs. Nothing mined, judged or reviewed.
- 2026-11-16: scripts written from DuckDB's before any judging (`make_from_ddb.py`, `make_from_ddb_2.py`,
  `panel.py`); `score_arw.py` adds the pooled secondary above. Mining restarted after the amendment.
  Expected size: DuckDB gave 0.32 candidates per fix commit and 34% of candidates were confirmed; Arrow's
  2,870 fix commits include much non-C++ work, so fewer than 440 confirmed defects are likely, and the test then
  holds every confirmed defect after the 40 of the history (the rule inherited from DuckDB).
- 2026-11-16: `arw_context.md` written by a fresh agent from Arrow's build and CI files (791 characters; DuckDB's
  798); it saw no candidate. Its one non-plumbing command was a `git status` on the clone (no working tree).

## Abandoned (2026-11-16, before any candidate was judged and before any Jev call)

Arrow's yield is too low for this test: 200 candidates from 1,891 of the 2,870 fix commits (11%; DuckDB 32%),
since most Arrow fixes touch Python, R, Java, Go or docs. About 300 candidates would give about 100 confirmed
defects, 60 of them in the test: too few to compare two arms. The third fresh project is PPSSPP instead
(`../pp-set/README.md`), chosen on the same criteria plus its yield on 200 fix commits (47 per 100). Nothing of
Arrow was judged or reviewed; the Arrow clone was deleted and the streamed candidates with it. The scripts here
stay as the record and as the source of `../pp-set/`.
