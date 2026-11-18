# Pooled development of LO over three projects (offline)

Written 2026-11-12 before any number of this folder was computed. Offline only: every Jev answer used
here is already stored; no Jev or Claude call.

## Data

All 844 labelled changes so far, with the five persona seats as WaRF logged them:
G+Smo 352 (dev 132 + confirm 220), MFEM 300, KeePassXC 192. All three sets have been looked at before,
so nothing here is a confirmation; a lever that helps goes to a fresh set.

## Measure

**Leave one project out**: calibrate on two projects, decide the third, for each of the three. This
is the situation of a new WaRF user whose project is unlike the training history. Balanced accuracy
per project and the mean of the three; exact McNemar against LO over all 844 changes (each is
decided once, by a calibration that never saw its project).

## Arms (WaRF's own Calibrator, pool_evidence, logodds_boundary, logodds_decision)

- **LO**: as tested. After each complete group (the jev-1.14 seats, then the jev-1.13 seats) WaRF
  stops if the pooled evidence crosses A or B; otherwise the domain tau decides.
- **LO-full**: the same seats and calibration, but the boundary is not checked before the last
  group: every group's evidence enters before the decision. In the runs every seat was asked anyway,
  so this costs nothing; the question is whether stopping after the first group throws away evidence.
- **LO+SIZE**: LO plus the size seat of `../size-seat/` (p = sigmoid(ln(1 + added) - 3), Platt
  calibrated) as a third group.
- **LO+SIZE-full**: both changes.
- References: **V1** (one Jev seat, the usual question, calibrated) and **SIZE** (the size seat alone).

## Error analysis (LO)

LO's wrong decisions by their distance |Lambda - tau|: near the threshold (< ln 2, where WaRF already
reports LOW confidence) or confidently wrong. Confident errors cannot be fixed by aggregation.

## Result (2026-11-12, `pooled.py`, `pooled.log`, `pooled.json`)

| Leave one project out | G+Smo | MFEM | KeePassXC | Mean | All 844 |
|---|---|---|---|---|---|
| V1, one Jev seat | 71.3% | 75.7% | 77.6% | 74.9% | 74.3% |
| SIZE alone | 73.6% | 79.3% | 80.2% | 77.7% | 77.1% |
| LO, as tested | 73.3% | 80.0% | 82.3% | 78.5% | 77.7% |
| LO-full, no early stop | 73.3% | 80.0% | 82.3% | 78.5% | 77.7% |
| **LO+SIZE** | **76.1%** | **82.7%** | **84.4%** | **81.1%** | **80.3%** |
| LO+SIZE-full | 76.1% | 82.7% | 84.4% | 81.1% | 80.3% |

- **Early stop costs nothing.** LO stops after the jev-1.14 group on 139 of 844 changes, and the full pool
  decides every one of them the same way. LO-full is dropped.
- **LO+SIZE beats LO on every project.**
  - Over all 844 it gains 2.6 points: only LO+SIZE right on 45, only LO on 23, p 0.010.
  - G+Smo: 17 against 7, p 0.06.
  - MFEM: 17 against 9, p 0.17.
  - KeePassXC: 11 against 7, p 0.48.
- **The two kinds of evidence add up.**
  - LO+SIZE beats SIZE alone: 79 against 52, p 0.023.
  - LO beats one Jev: 51 against 22, p 0.0009.
- **LO alone is no better than the size alone** (101 against 96, p 0.78). Jev's answers and the change
  size carry much the same information, yet each adds to the other.
- Within-G+Smo cross-validation (`../size-seat/`, about 317 training changes) had LO+SIZE slightly below LO
  (75.7% against 76.3%). Here G+Smo is decided with 492 training changes from MFEM and KeePassXC, and LO+SIZE
  is above LO (76.1% against 73.3%).
- **Errors (LO).** 188 of 844 decisions are wrong:
  - 56 lie inside WaRF's LOW band (|Lambda - tau| < ln 2, 47% wrong there);
  - 63 lie between ln 2 and 2;
  - 69 are confidently wrong (|Lambda - tau| >= 2, 13.8% of those decisions).

  Outside the LOW band LO is right on 81.8% (balanced, 725 changes). The confident errors are Jev's own
  view of the change, so aggregation cannot reach them.

All three sets had been looked at before; LO+SIZE needs a fresh set before it is claimed.

## 2026-11-14: levers on the RocksDB matched set (development; the set has been used once for its test)

Where LO goes wrong there (800 changes, LO 69.0%): it catches 68% of the defects visible from the diff but
49% of those needing another file; 53% of the 199 defects the judges describe as build breaks (warnings
as errors on clang/MSVC/macOS, format specifiers, missing override, unused variables in release builds,
etc.); 36% of the defects in test files. Jev's ranking there: AUC 0.758 (LO mean p), 0.740 (one Jev).

| Lever (offline unless noted) | RocksDB balanced accuracy |
|---|---|
| LO as tested (calibrated on the other three projects) | 69.0% |
| + test files calibrated separately (`rdb_dev.py`) | 69.0% |
| learned on RocksDB's own labels, 10-fold CV, + test-file calibration | 70.1-70.6% |
| one Jev seat with WaRF's project context (`context/`, $0.52 for 3,200 calls) | 68.4% (plain 68.0%); AUC +0.017 [+0.006, +0.029] |
| one Jev seat shown the whole commit | 66.4%; AUC -0.027 |
| LO + a project-context seat (CV) | 69.5% (LO 69.5% in the same CV) |
| LO + a whole-commit seat (CV) | 70.5% |
| one Jev seat with a defect profile written from the 37 defects outside the test set (`history/`, $0.23) | AUC 0.771 (plain 0.740); with build rules 0.770; one seat in CV 70.6% |
| seven project-learned YES/NO checks (`history/run_checks.py`, whole change and hunks, $0.26) | AUC 0.59-0.75 each, mean 0.783; alone in WaRF 71.0% |
| LO through WaRF with the project context (build rules + profile; `history/run_lo_ctx.py`, $0.58) | AUC 0.773 vs 0.758 (+0.015 [+0.004, +0.026]); CV 70.2% vs 69.2% |
| learned weights over all stored Jev views (`history/stack.py`, L2 logistic, CV) | 72.8% |
| + retrieved declarations of the changed names (`decl/`, $0.33) | no gain: verdict AUC 0.739 -> 0.733, stack 72.5% |
| + the maximum per-hunk verdict; + file type alone | 72.4%; 72.7% |
| line localisation: "which added line breaks a build / causes a runtime defect, or NONE" (`locate/`, $0.34) | one call AUC 0.777 (WaRF's question, same context: 0.770); its two numbers alone 70.0-70.3% |
| eleven specific build/runtime diagnostics (same calls) | AUC 0.55-0.70 each |
| learned weights over all views + localisation + diagnostics | 73.6-73.8% |
| the same with weights per file type (test / header / source) | 74.2-74.6% (not counted: a base rate of the set, like size) |

Learning curve of the 73.7% stacker (training changes per fold subsampled): 180 -> 71.3%, 360 -> 72.4%,
540 -> 73.0%, 720 -> 73.7%. Still rising, about +1.3 points per doubling: more labelled RocksDB history is a
lever. Asking per hunk instead of on the whole change changes no AUC (verdict 0.739 whole, 0.736 hunks).
jev-1.13 ranks a little better than jev-1.14 inside LO (0.766 vs 0.743) but the two correlate at 0.89.

What the best stacker still misses (out of fold): 26% of the defects visible in the diff, 42% of those
needing another file, and 23% of the clean changes are flagged (40% of clean changes to non-test source
files). The misses are mostly strict-build breaks (sign-compare, NDEBUG-only variables, missing override,
64-to-32 narrowing, ROCKSDB_LITE / custom namespace) and uninitialised members or leaks.

All numbers on this page are development on the RocksDB matched set (CV within the set, choices such as
the prior width made on the same CV): they need a fresh set before they are claimed.

## 2026-11-14: built into WaRF (question seats, `--aggregate learned`; ADR 0003)

`warf-panel/select_panel.py` (offline, one feature per seat, every seat with the project context): the five
persona seats 69.4-69.9%; + 2 locate seats 71.4%; + 7 project checks **73.7%** (14 seats; the same as all
45 stored views); + the 11 diagnostics instead of or besides the checks 71.0-73.2% (dropped).

WaRF now asks these questions itself (`AgentProfile.question` = `check` / `locate`, `warf/questions.py`) and
has a learned aggregation mode. Through WaRF's own `run_review`, stored Jev answers stubbed in, training
folds written as labelled session logs (`warf-panel/replay_learned.py`, 10-fold x 5):

| Panel | `--aggregate logodds` | `--aggregate learned` |
|---|---|---|
| 5 persona seats with the project context | 70.2% (= the CV of `score_lo_ctx.py`) | 69.6% |
| 14 seats: + LOCATE-BUILD, LOCATE-RUNTIME, 7 CHECK seats | **72.5%** | **73.6%** |

Locate's p(REJECT) is 1 - min over windows of p(NONE) (the provider's rule since the cold review; with the
first version's product: 72.9% / 73.1%, `replay_learned_product.log`). Paired, exact McNemar on one
repetition (`paired.py`): 14 seats vs the 5 persona seats, both logodds, 35 vs 18 changes, p 0.027; learned
vs logodds on the 14 seats 47 vs 39, p 0.45. The question seats carry the shown gain; learned weights are not
shown to add.
`warf-panel/smoke_live.py`: the 14-seat panel live through WaRF on 10 changes (about $0.02) works end to
end; live p(REJECT) is within 0.01-0.04 of the stored answers per seat on average (checks up to 0.07: their
stored answers were asked without the context). `warf-panel/mutants.py`: tools/test_learned.py catches 23
of 23 breaks of the change (15 at first; a cold review found five it missed, now covered). The panel profile
is `warf-panel/panel.json`.

Two items of the RocksDB set share their code (f5cdf93 and 30742e1, `util/ldb_cmd.cc`, both defective):
the same change landed in two commits.

## 2026-11-14: at most five seats (`five-seats/`)

The user's limit after the 14-seat panel. A question seat now asks several questions in one call (one per
line of its persona, pooled as "any of them finds a problem"; ADR 0003 decision 3). One-call seats from the
stored answers (`views.py`, AUC): locate build + runtime 0.785, the seven checks 0.782 (after the readout's
two decimals; the mean of p(YES) 0.780), the best persona seat 0.770. Panels of at most five seats, offline
(`search.py`, about 1,500 panels, stand-ins): the best at 73.0-73.3% `logodds`; picked by a rule fixed
before looking (`structured.py`, the best seat of each kind): BOUNDARY + LOCATE + CHECKLIST 72.8%, with
SKEPTIC and WaRF's default question 73.2%.

Live through WaRF (`run_live.py`, the five question-seat variants on all 800 changes, every seat with the
project context, 23.6M input tokens, about $0.99), replayed with WaRF's run_review (`replay_live.py`,
10-fold x 5, `logodds`):

| Panel | Accuracy | vs LO with context (70.2%), exact McNemar, rep. 0 |
|---|---|---|
| BOUNDARY + LOCATE + CHECKLIST (3 seats) | **73.6%** | 49 vs 22, p 0.002 |
| SKEPTIC + BOUNDARY + DEFAULT + LOCATE + CHECKLIST (5) | 73.5% | 42 vs 17, p 0.002 |
| the same with LOCATE-13 + CHECKLIST-13 (jev-1.13) | 72.1% | 38 vs 24, p 0.098 |

Live AUC: CHECKLIST 0.794 (stand-in without context 0.782), LOCATE 0.789, CHECKLIST-13 0.789, LOCATE-13
0.779, DEFAULT 0.765. The panel is `five-seats/panel3_rocksdb.json`.

Tried and not kept (offline, stand-ins): splitting the question seats in two (`split.py`, 72.0-72.4% vs
72.8%); the eleven diagnostics inside the checklist (AUC 0.759); a whole-commit seat (`evidence.py`, 71.4%);
`learned` instead of `logodds` on small panels (71.3% vs 72.8% with three seats). A fourth seat shown the
retrieved declarations adds about half a point (73.4-73.5% vs 72.8%) but needs retrieval in WaRF and seat
inputs on the CLI.

## 2026-11-15: after the DuckDB test, both projects together (`cross-project/`, development: both seen)

Stored WaRF answers, the same eight seats on both projects (persona seats, DEFAULT, LOCATE, CHECKLIST; each
project's own context and checks), WaRF's `logodds` rule, 10-fold x 5 (`cross.py` reproduces the WaRF replays
exactly: LO-ctx 70.2% / 75.1%, PANEL3 73.6% / 76.6%).

| Lever | RocksDB | DuckDB |
|---|---|---|
| PANEL3 (BOUNDARY + LOCATE + CHECKLIST) | 73.6% | 76.6% |
| best of all panels of at most 5 seats, by the worse project (`cross.py`) | PANEL3 itself; the next 11 within 0.5 points | |
| calibration shared with the other project (`pooling.py`) | 71.1% | 77.0% |
| learned per-seat weights trained on both projects | 71.2% | 77.2% |
| a fourth seat shown retrieved declarations (`run_decl_seat.py`, live on RocksDB, $0.15) | 73.9% (DECL AUC 0.762 vs DEFAULT 0.765) | not run: one item takes 4.5 min of git grep on DuckDB |
| all eight seats (`logodds`; learned weights) | 73.2%; 72.7% | 76.8%; 77.5% |

PANEL3 is at the level of everything the eight Jev seats hold together. Each project needs its own
calibration (sharing it costs RocksDB 2.4 points). What PANEL3 still misses on DuckDB: 36% of the defects that
need another file (diff-visible 16%), 31% of the build breaks; false alarms on 30% of clean source changes
(headers 12%).
