# Developing LO, WaRF's log-odds Jev panel (2026-11-11, no new calls)

LO is the fifth confirm-set test's winner (`../confirm-set/README.md`): five persona seats (SKEPTIC,
ADVOCATE, AUDITOR on jev-1.14; TEST-FOCUSED, BOUNDARY on jev-1.13), WaRF's `aggregate="logodds"`,
Platt calibration per seat from labelled history, seats pooled per Jev version. 73.2% on the 220
confirm items after learning on the 132 dev items.

`lo_offline.py` rebuilds LO's decision from stored answers with WaRF's own Calibrator, grouping,
boundary and tau rule. It reproduces all 220 of WaRF's logged LO decisions. Variants are judged by
stratified 10-fold cross-validation, repeated 5 times, over all 352 judged items (dev + confirm),
calibrating on the training folds only, so no further look at the confirm set is spent.

| Cross-validated, 352 items | Balanced accuracy |
|---|---|
| one Jev seat in WaRF (usual question, jev-1.14, calibrated) | 73.8% |
| **LO, 5 personas (as tested)** | **76.3%** |
| LO + the usual question on both versions | 76.7% |
| LO + the 7 narrow checks of both versions (own source, ADR 0002) | 76.4% |
| LO + usual question + narrow checks | 75.5% |
| narrow checks of both versions only | 76.3% |

Repeats vary by about ±0.4 points. Adding more Jev seats does not move LO: they repeat what the
personas already say.

`learning_curve.py`: LO with 40, 80, 132, 200 and 317 labelled reviews scores 75.2, 75.9, 75.8, 76.3
and 76.2% (one calibrated Jev seat: 72.5-73.7%). Beyond about 80 labelled reviews more history does
not help. LO's lead over one calibrated Jev seat is a steady 2.5-2.7 points.

Cross-validated numbers are higher than the confirm-set ones because the dev items are easier for Jev.

## Context seat (2026-11-11, `lo_context.py`, `lo_context.log`; $0.038 in Jev calls)

The context seat is jev-1.14 shown the whole change plus the retrieved declarations of the names on the
changed lines (same revision, git only). Dev answers come from the earlier context lever
(`../real-set/jev-narrow/context/`); the 220 confirm answers are new (`../confirm-set/jev-context/`,
the dev lever's code with its paths pointed there). The seat is its own evidence source ("context",
ADR 0002). Two forms were fixed in advance.

| Cross-validated, 352 items | Right | Caught of the 44 needs-other-file defects |
|---|---|---|
| one Jev seat (usual question) | 73.8% | 63.6% |
| context seat alone (usual question) | 74.1% | 68.2% |
| **LO, 5 personas (as tested)** | **76.3%** | 70.5% |
| LO + context seat (usual question) | 75.2% | 65.9% |
| LO + context seats (7 checks) | 75.5% | 64.1% |

The context seat helps a little on its own, mostly on defects that need another file. Added to LO, it
lowers both the overall score and the catch rate on those defects. As its own source, its evidence is
summed with the two Jev-version groups, but it mostly repeats what they say, so the sum counts the
same opinion twice and moves decisions the wrong way.
