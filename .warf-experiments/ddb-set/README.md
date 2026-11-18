# Fresh-set test: the three-seat question panel against LO with the same context, on DuckDB

Written 2026-11-14 while DuckDB was being cloned, before any DuckDB candidate was mined, judged or reviewed.
It is not changed after the first judge call, except where marked; later changes are added below with
their date and reason and never enter the primary result.

## Why this test

On the 800 RocksDB changes matched on size (`../rdb-set/`), WaRF with three Jev seats (BOUNDARY, LOCATE,
CHECKLIST; ADR 0003, `../pooled-dev/five-seats/`) was right on 73.6%, WaRF's five persona seats with the
same project context (LO-ctx) on 70.2%; exact McNemar 49 vs 22 changes, p 0.002. The panel was chosen and
developed on RocksDB only. RocksDB has only 33 defect candidates after that set's cutoff, so the test
needs a new project: DuckDB (github.com/duckdb/duckdb, a C++ analytical database), chosen by Teymur
together with the size, 400 + 400. Cloned 2026-11-14 into `C:\workdir\warf\repos\duckdb`, read with git only
afterwards. What is tested is the method: the panel's structure, and the procedure that turns a project's
own history into its context and checks.

## The set, as `../rdb-set/` with its amendment (matched on added lines)

- **Defective candidates** (`build_ddb.py`, git only): `../rdb-set/build_rdb.py`'s rules. Non-merge commits on
  `origin/main` whose subject names a bug, not a revert, touching at most 5 files, are fixes; their deleted
  non-cosmetic C++ lines are blamed in the fix's parent (B-SZZ). A blamed (commit, file) is a candidate when
  the fix came within 180 days, the commit is not a merge or revert, was made before **2025-11-14** (one
  year before the clone, as for RocksDB), its WaRF input is at most 20 000 characters, and the file is not
  under `third_party/` (vendored code is fixed upstream). One file per commit; fixes in a seeded random
  order; up to 1,100 candidates.
- **Judges** (`judge_prompt.md`: the RocksDB text with DuckDB's path): two independent Claude agents in
  batches of 40. Judge A sees candidates in list order; judge B sees only those A calls "yes", without A's
  verdict. Defective only if both say "yes".
- **History and test:** in list order, the first **40** confirmed defects are the project's history (they
  write its profile and checks, below) and the next **400** are the test defects. Judging stops at 440 or
  when candidates run out.
- **Clean controls** (`build_clean_ddb.py`, git only, after the test defects are fixed): the RocksDB
  amendment's procedure. Non-merge, non-revert commits before 2025-11-14, one C++ file each, not under
  `third_party/`, not the commit of any candidate and not a fix commit, every added non-blank line still
  blamed on the commit at `origin/main`, input at most 20 000 characters; drawn in a seeded random order
  into the added-line bins 1, 2, 3, 4-5, 6-8, 9-12, 13-18, 19-27, 28-40, 41-60, 61-90, 91-135, 136-200,
  201+ until each bin holds twice as many survivors as test defects in it. Each test defect (date order)
  takes the free control of its bin with the nearest commit date, else of the nearest non-empty bin.
- Neither the judges nor the selection see any Jev answer; Jev never sees a fix or a label.

## What the project's history writes (fixed now, before any judging)

- **Project context** (`ddb_context.md`): DuckDB's build rules written by a fresh agent from DuckDB's own
  build files at `origin/main` (CMakeLists.txt, Makefile, CI workflow files), with
  `../pooled-dev/context/rocksdb_context.md` as the template for what to cover (warning flags and
  -Werror, compilers and platforms, build configurations, debug/release differences, test frameworks,
  locking conventions if documented). It sees no candidate.
- **Defect profile** (`defect_profile.md`): written by a fresh agent from the 40 history defects (the two
  judges' one-sentence descriptions, the files and the dates; `history_defects.md`), with the prompt in
  `profile_prompt.md`. It sees no test item.
- **Checks** (`checks.md`): seven YES/NO questions about the changed lines, written by a second fresh agent
  from the profile alone, with the prompt in `checks_prompt.md`.
- The context shown to every seat is the build rules, then "Defects found in this project's past changes
  (from labelled reviews):" and the profile, as on RocksDB.

## The arms (frozen now)

Every seat on Jev through OpenRouter, every seat shown the context, WaRF's `run_review` with
`aggregate="logodds"`, every seat asked (`no_early_stop`), input label "Patch under review (unified diff)".

- **PANEL3** (candidate): BOUNDARY (persona seat of `../pooled-dev/history/profiles/uniform.json`,
  jev-1.13); LOCATE (jev-1.14, `question="locate"`, two questions: the RocksDB runtime question unchanged,
  and the RocksDB build question with "a supported RocksDB configuration" read as "a configuration DuckDB
  supports" and its RocksDB examples "a name unavailable under ROCKSDB_LITE, a custom ROCKSDB_NAMESPACE,
  Windows/MSVC or another platform" read as "a name unavailable on another platform, compiler or build
  configuration DuckDB supports"; texts in `panel.py`); CHECKLIST (jev-1.14, `question="check"`, the seven
  checks of `checks.md`, one per line).
- **LO-ctx** (comparator): the five persona seats of `uniform.json` (SKEPTIC, ADVOCATE, AUDITOR on
  jev-1.14; TEST-FOCUSED, BOUNDARY on jev-1.13). BOUNDARY's answers are shared by both arms.
- **Calibration:** within DuckDB by stratified 10-fold cross-validation, the folds of
  `../warf-panel/replay_learned.py` (seed 300 + repetition): each change is decided with WaRF's
  Calibrator fitted on the labelled sessions of the other nine folds, so no change calibrates its own
  decision. This is the procedure of the RocksDB result.

## Primary analysis

Balanced accuracy of PANEL3 and LO-ctx on the 800 test changes, repetition 0 (5-repetition means reported
next to it).
- **PANEL3 wins** if its balanced accuracy is higher and the exact two-sided McNemar test on the changes
  where exactly one arm is right gives p < 0.05.
- **Not shown** if PANEL3 is higher but p >= 0.05. **No case** otherwise.

Power, if RocksDB's effect holds (8.9% of changes discordant, 49:22): about 90% with 400 + 400.

## Secondary, frozen now

Each seat's AUC; PANEL3's caught and false alarms; the five-seat panel SKEPTIC + BOUNDARY + DEFAULT
(WaRF's default question, jev-1.14) + LOCATE + CHECKLIST against LO-ctx; the result on the defects the
judges call visible from the diff.

## Status

- 2026-11-14: preregistration written while the clone runs. Nothing mined, judged or reviewed yet.
- 2026-11-14: DuckDB cloned (`origin/main` b678afa, 2026-11-13; 605 MB). `judge_prompt.md`,
  `profile_prompt.md`, `checks_prompt.md`, `panel.py` (the arms) and `judge.py` (TARGET 440) written; mining
  (`build_ddb.py`) and the context agent (`ddb_context.md`, build files only) started. Still nothing judged
  or reviewed.
- 2026-11-14: `select_defects.py`, `build_clean_ddb.py`, `select_matched_ddb.py`, `run_ddb.py` and
  `score_ddb.py` written before any DuckDB data exists. Dry run of `score_ddb.py` on RocksDB's stored WaRF
  answers (`dryrun/`): it reproduces RocksDB's numbers exactly (PANEL3 73.6%, LO-ctx 70.2%, 49 vs 22 changes,
  p 0.0018; FIVE 73.5%).
- 2026-11-14: `ddb_context.md` written by the context agent from DuckDB's build and CI files at b678afa
  (CMakeLists.txt, Makefile, Main/OSX/Windows/Android workflows, CONTRIBUTING.md, and the assert,
  memory-safety and thread-annotation headers); it opened no candidate. Two of its facts checked by hand
  (`-Werror=thread-safety`, CMakeLists.txt:239; TREAT_WARNINGS_AS_ERRORS in Main.yml and OSX.yml).
- 2026-11-14: mining is slow (200 candidates in about 40 minutes) and `build_ddb.py` writes its list only at
  the end. `build_prefix.py` mines the start of the same list (same rules, same seeded order) and writes each
  candidate as it is found, so judging starts on it; when `build_ddb.py` finishes, the prefix must equal the
  start of `candidates.jsonl` (`build_prefix.check_prefix()`), or the judging of the prefix is redone.
- 2026-11-14: judging started: judge A on the first 120 candidates (batches A_00-A_02), one agent per batch
  with the brief in `judge_agent_brief.md`. Still no Jev call on this set.

## Amendment (2026-11-14, before any Jev call on this set): up to 1,600 candidates

Judge A said yes to 44 of the first 120 candidates (37%; RocksDB 55%). At RocksDB's rate for judge B the
preregistered cap of 1,100 candidates would give about 360 confirmed defects, short of the 440 needed. The
cap is raised to 1,600; the rules and the seeded order are unchanged, so the first 1,100 candidates are the
same. The mining run with the old cap (which wrote its list only at the end) was stopped and restarted as
`build_ddb.py 1600`, which writes each candidate to `candidates_stream.jsonl` as it is found; `judge.py`
uses the longer of that and `candidates_prefix.jsonl` after checking that one is the start of the other.
Nothing else changes.

- 2026-11-14/15: mining done: 1,600 candidates from 5,071 of the 9,021 fix commits (`build.log`);
  `candidates_prefix.jsonl` (520) is identical to the start of `candidates.jsonl`, and so is the stream
  (`build_prefix.check_prefix()`), so the judging that began on the prefix stands. Judging was interrupted by
  the account's usage limit with eight batches in progress (A_18-A_22, B_05-B_07); their agents resumed where
  they stopped. So far: judge A 757 judged, 285 yes; judge B 175 judged, 168 confirmed. No Jev call yet.
- 2026-11-15: the history was fixed before judging ended (`write_history.py`): every candidate up to the
  40th confirmed defect (candidate 114) had both judges' verdicts, so no later verdict can change which 40
  they are; `select_defects.py` must reproduce the same `history_defects.md`. The profile agent started on it.
- 2026-11-15: `defect_profile.md` (1,293 characters, six kinds covering the 40) written by the profile agent
  from `history_defects.md` alone; `checks.md` (seven questions) written by a second agent from the profile
  alone. Neither opened anything else. `panel.py` now builds all three arms. No Jev call yet.
- 2026-11-15, judging done (`judgements/`, 33 judge-A and 18 judge-B batches): judge A judged the first 1,320
  candidates (478 yes), judge B the 478 (446 both yes). `select_defects.py`: history 40 (its
  `history_defects.md` is byte-identical to the one `write_history.py` wrote for the profile), test 400,
  6 confirmed beyond. Test defects' visibility (both judges): diff 243, needs_other_file 132, split 25.
  Matched clean controls being mined (`build_clean_ddb.py`). No Jev call yet.
- 2026-11-15, set frozen (`build_clean_ddb.py`, `build_matched.log`, `select_matched_ddb.py`, `select.log`):
  15,943 pairs screened, 524 survivors. Large surviving changes are rare: bins 28-40 got 46 of 88 controls,
  41-60 11/76, 61-90 9/90, 91-135 4/56, 136+ none. 159 defects took a control from a neighbouring (smaller)
  bin. Added lines median 22 (defective) against 15 (clean), AUC of the added-line count 0.610 (RocksDB matched
  0.558); date gap median 292 days. 800 items. No Jev call yet.

## Secondary analysis added before any Jev call (2026-11-15)

Because the large bins could not be filled, the size gap is larger than on RocksDB. Both arms review the same
800 changes, so the gap does not favour an arm by itself, but an arm that reacts more to size could gain from
it. Added now, before any Jev answer exists: the primary comparison repeated on the pairs whose clean control
came from the defect's own added-line bin (the other pairs left out with their defect), and each seat's AUC
against the added-line count's AUC on the same items. The primary analysis is unchanged.

## Result (2026-11-15, `run_ddb.py`, `score_ddb.py`, `score.log`, `score.json`)

Jev: 800 reviews through WaRF (`sessions.jsonl`), all 8 seats every time, 22.7M input tokens, about $0.95,
no errors. Every change decided by WaRF's run_review (`logodds`) with calibration from the other nine folds.

| 800 DuckDB changes (400 + 400) | Right (BA), rep. 0 | mean of 5 | Caught | False alarms |
|---|---|---|---|---|
| **PANEL3** (BOUNDARY + LOCATE + CHECKLIST) | **76.5%** | 76.6% | 309/400 | 97/400 |
| LO-ctx (five persona seats) | 75.0% | 75.1% | 306/400 | 106/400 |
| FIVE (SKEPTIC, BOUNDARY, DEFAULT, LOCATE, CHECKLIST) | 76.2% | 76.2% | 308/400 | 98/400 |

- **Primary:** PANEL3 − LO-ctx +1.5 points; only PANEL3 right on 30 changes, only LO-ctx on 18; exact McNemar
  p 0.111. **Preregistered verdict: not shown.**
- FIVE vs LO-ctx: 26 vs 16, p 0.164. On the defects visible from the diff (with every clean change): PANEL3
  79.9%, LO-ctx 77.5%.
- On the 241 pairs matched in their own added-line bin (secondary, added before any Jev call): PANEL3 74.7%,
  LO-ctx 74.3%, 14 vs 12, p 0.845. The +1.5 points of the whole set sit in the pairs with the larger size gap.
- AUC per seat: SKEPTIC 0.851, BOUNDARY 0.847, TEST-FOCUSED 0.841, LOCATE 0.837, DEFAULT 0.835, CHECKLIST 0.830,
  ADVOCATE 0.821, AUDITOR 0.816; the added-line count alone 0.610. On RocksDB the question seats ranked above
  the persona seats (CHECKLIST 0.794, LOCATE 0.789 against 0.757-0.770); on DuckDB they do not.
- What holds: three seats did as well as five (PANEL3 76.5% against LO-ctx 75.0% with 3 instead of 5 calls per
  change, plus LOCATE's windows). What does not hold: the gain of RocksDB's development (73.6% against 70.2%,
  p 0.002) is not confirmed on a fresh project; Jev is much better on DuckDB than on RocksDB with every seat.

## Redaction (2026-11-19, after the result)

One item, `8715233:s3fs.cpp:defective`, shows DuckDB's `S3FileSystem::Verify()` (`extension/httpfs/s3fs.cpp`), which
hard-codes AWS temporary credentials dated 2021-09-04: expired since 2021 and public in DuckDB's history. GitHub's
push protection refused the push for them, so their key ID, secret and session token are replaced by
`REDACTED-AWS-KEY-ID`, `REDACTED-AWS-SECRET-KEY`, `REDACTED-AWS-SESSION-TOKEN` and `REDACTED` (the token's split
pieces) in the seven files that held them: `candidates.jsonl`, `candidates_prefix.jsonl`, `candidates_stream.jsonl`,
`defects.jsonl`, `items.jsonl`, `judge_inputs/A_09.md` and `B_04.md`. Nothing else in them changed (checked against
the committed blobs). The judges and Jev saw the original; `sessions.jsonl`, `score.log` and `score.json` are
unchanged, and a replay of that one item now sends the redacted text. AWS's documented example key (`...EXAMPLE`) in
the same function is left as it is.
