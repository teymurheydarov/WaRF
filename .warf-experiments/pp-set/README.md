# Second fresh test: the three-seat question panel against LO with the same context, on PPSSPP

Written 2026-11-16 after PPSSPP was cloned and its candidate yield measured on 200 fix commits, before any
PPSSPP candidate was mined for the set, judged or reviewed. It is not changed after the first judge call, except
where marked; later changes are added below with their date and reason and never enter the primary result.

## Why this test

On DuckDB (`../ddb-set/`, the first fresh test) the three-seat panel (PANEL3: BOUNDARY, LOCATE, CHECKLIST) was
right on 76.5%, WaRF's five persona seats with the same context (LO-ctx) on 75.0%: 30 against 18 changes,
p 0.111, not shown. On RocksDB, where the panel was developed, 73.6% against 70.2%, p 0.002. The direction
replicated, the size did not. Teymur asked for a third project and left the choice open. Apache Arrow was
tried first and dropped before any judging for its low yield (`../arw-set/README.md`, "Abandoned"). PPSSPP
(github.com/hrydgard/ppsspp, a C++ PSP emulator for Windows, Linux, macOS, Android and iOS; Claude's pick) was
cloned 2026-11-16 into `C:\workdir\warf\repos\ppsspp` (default branch only, no checkout, 390 MB), read with
git only. Criteria: mostly C++, an active history of fixes with plain subjects ("Fix ..."), a clone that fits
Teymur's free disk space, and a yield sufficient for 440 confirmed defects (47 candidates per 100 fix commits
in the probe; 4,457 fix commits).

## The set: DuckDB's procedure (`../ddb-set/README.md`), with these settings fixed now

- **Defective candidates** (`build_pp.py`): `../rdb-set/build_rdb.py`'s rules unchanged (the subject rule for
  fixes as written, with no prefix handling; at most 5 files, B-SZZ blame, 180 days, one file per commit, input
  at most 20 000 characters, seeded order), branch `origin/master`, cutoff **2025-11-16** (one year before the
  clone), up to **1,600** candidates, written one by one as they are found (`candidates_stream.jsonl`).
  Excluded paths: vendored code, which in PPSSPP is everything under `ext/` except `ext/native/` (PPSSPP's own
  former base library).
- **Judges:** DuckDB's prompt with PPSSPP's repository (`judge_prompt.md`), two independent Claude agents, A in
  list order, B on A's yes without A's verdict, batches of 40 (`judge_agent_brief.md`).
- **History and test:** in list order, the first 40 confirmed defects are the history, the next 400 the test.
  Judging stops at 440 or when candidates run out.
- **Clean controls:** DuckDB's procedure (matched on added-line bins, survival screen, nearest date), excluded
  paths as above.
- **Project context** (`pp_context.md`), **defect profile** (`defect_profile.md`) and **checks** (`checks.md`):
  written by fresh agents exactly as for DuckDB (`profile_prompt.md`, `checks_prompt.md` with "PPSSPP" for
  "DuckDB"); none sees a test item.

## The arms (as DuckDB's, `panel.py`)

PANEL3 (BOUNDARY jev-1.13; LOCATE jev-1.14 with the build question naming "a configuration PPSSPP supports";
CHECKLIST jev-1.14 with `checks.md`) and LO-ctx (the five persona seats), every seat shown the project
context, WaRF `run_review` with `logodds`, every seat asked. Calibration within PPSSPP by stratified 10-fold
cross-validation (seed 300 + repetition), as for DuckDB.

## Primary analysis

Balanced accuracy of PANEL3 and LO-ctx on the 800 test changes, repetition 0 (5-repetition means reported).
**PANEL3 wins** if it is higher and the exact two-sided McNemar test on the discordant changes gives p < 0.05;
**not shown** if higher with p >= 0.05; **no case** otherwise.

## Secondary, fixed now

- **Pooled over the two fresh projects:** the discordant counts of DuckDB's primary (30 for PANEL3, 18 for
  LO-ctx) added to PPSSPP's, one exact two-sided McNemar on the sums; "pooled wins" if PANEL3 is ahead and
  p < 0.05.
- DuckDB's secondaries: FIVE against LO-ctx, the defects visible from the diff, the pairs matched in their own
  added-line bin, each seat's AUC against the added-line count's AUC.

## Disk space

Teymur has about 41 GB free. The PPSSPP clone has no checkout; once the set is judged and the Jev run is done,
the clones downloaded for these tests (PPSSPP, DuckDB) are deleted, since the frozen sets carry everything the
scoring needs. The Arrow clone was deleted when Arrow was dropped.

## Status

- 2026-11-16: preregistration written. Scripts generated from `../arw-set/` (`make_from_arw.py`), which came
  from DuckDB's; `build_pp.py` written by hand. Nothing mined for the set, judged or reviewed.
- 2026-11-16: mining started (`build_pp.py`, 4,457 fix commits; 100 candidates after 183 fixes). The judge brief
  carries DuckDB's escape sentence from the first batch. Judge A started on the first 120 candidates (A_00-A_02);
  the context agent (`context_agent_brief.md`) started at the same time.
- 2026-11-16: `pp_context.md` written by the context agent (798 characters; two claims spot-checked against
  CMakeLists.txt and Common/Log.h). Unlike RocksDB, DuckDB and Arrow, PPSSPP's CI builds Release only and no
  warning fails the build except -Werror=return-type. The LOCATE seat's build question stays as fixed (it names
  -Werror and /WX generically); the context tells every seat which warnings PPSSPP treats as errors.
- 2026-11-16: judge A 360 judged, 147 yes; judge B 80 judged, 76 confirmed. `write_history.py`: the first 40
  confirmed defects lie within the first 106 candidates, every one of which has both verdicts it needs, so
  `history_defects.md` is fixed. The profile agent started on it (`profile_prompt.md`).
- 2026-11-16: `defect_profile.md` (1,294 characters, six kinds covering the 40) and `checks.md` (seven
  questions; JIT/HLE contracts split into two) written by fresh agents; `panel.py` loads all three arms.
  Status: judge A 400 judged, 165 yes; judge B 120 judged, 114 confirmed; 1,330 candidates mined.
- 2026-11-16: mining done: 1,600 candidates from 3,725 of the 4,457 fix commits (`build.log`); the stream is
  identical to `candidates.jsonl`. 24 candidates carry the plain patch instead of the enriched one, as WaRF's
  own fallback gives: 14 from `enrich_patch`'s known IndexError, 10 from files that are not UTF-8 (WaRF's
  context extractor decodes git output as UTF-8; its reader thread printed the tracebacks in `run_build.log`).
  DuckDB had 3 such candidates. Nothing was changed for this.
- 2026-11-16/17: a usage limit stopped judges A_20, A_21, A_22 and B_07 before any wrote its file; each was
  resumed with its own context after the reset (as for DuckDB). Status then: judge A 800 judged, 332 yes;
  judge B 280 judged, 269 confirmed. From B_05 on, every B batch is checked (`b_guard.py`) to draw only on
  finished A batches, so no B judge sees a verdict that its A judge could still change.
- 2026-11-17: judging done (A_00-A_28, B_00-B_13): judge A 1,160 candidates, 475 yes; judge B all 475, 454
  confirmed (95.6%; DuckDB 93%). `select_defects.py`: history 40 (its `history_defects.md` is byte-identical to
  the one fixed early), test 400, 14 beyond; 440 candidates not judged. Test defects' visibility: diff 253,
  needs another file 111, not visible 13, judges split 23. Clean-control mining started (`build_clean_pp.py`).
- 2026-11-17: clean controls (`build_clean_pp.py`): all 44,845 (commit, C++ file) pairs drawn, 8,523 screened,
  622 kept; the bins above 41 added lines stay short (41+ 28/68, 61+ 12/54, 91+ 9/44, 136+ 3/30, 201+ 0/34), as
  on DuckDB (28+ 46/88 ... 201+ 0/16). `select_matched_pp.py`: 800 items; 98 defects took a control from a
  neighbouring bin (DuckDB 159); added lines median 18 for both kinds, AUC of added lines 0.549 (DuckDB 0.610);
  date gap median 1,126 days (DuckDB 292). The set is frozen; no Jev call before this point.
- 2026-11-17: Jev run (`run_pp.py`): 800 reviews, 8 seats each, no errors, 27.2 M input tokens (about $1.1).

## Result (2026-11-17, `score_pp.py`, `score.log`, `score.json`)

| arm | balanced accuracy (rep 0) | mean of 5 | caught | false alarms |
|---|---|---|---|---|
| PANEL3 | 70.8% | 70.8% | 285/400 | 119/400 |
| LO-ctx | 69.0% | 69.2% | 278/400 | 126/400 |
| FIVE | 70.8% | 70.6% | 286/400 | 120/400 |

- **Primary: not shown.** PANEL3 is right on 47 changes LO-ctx gets wrong, LO-ctx on 33 that PANEL3 gets wrong;
  exact McNemar p = 0.146.
- **Secondary, pooled with DuckDB (fixed before mining): pooled wins.** 30 + 47 = 77 against 18 + 33 = 51,
  exact McNemar p = 0.027. The same direction on all three projects: RocksDB (where the panel was built) +3.4
  points, DuckDB +1.5, PPSSPP +1.8.
- FIVE against LO-ctx: 39 vs 25, p = 0.103. Defects visible from the diff (with every clean change): PANEL3
  73.7%, LO-ctx 71.6%. The 302 pairs matched in their own added-line bin: 70.5% vs 68.9%, 35 vs 25, p = 0.245
  (on DuckDB 14 vs 12): the gain is not a size artefact here.
- Every seat's AUC is far above the added-line count's (0.549): seats 0.715-0.778, best TEST-FOCUSED 0.778,
  BOUNDARY 0.777, SKEPTIC 0.772. PPSSPP is harder than DuckDB for every seat (DuckDB 0.816-0.851).
- The scorer was dry-run on DuckDB's stored answers before scoring and reproduced DuckDB's result exactly.
- 2026-11-17: the PPSSPP and DuckDB clones and 581 WaRF scratch folders in %TEMP% (84 MB) were deleted
  (1,383 MB freed; 44 GB free). Scoring needs only `items.jsonl` and `sessions.jsonl`; re-mining needs a new
  clone of the same branch.
