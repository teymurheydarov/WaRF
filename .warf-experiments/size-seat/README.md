# A size seat for LO: does the change size raise WaRF's accuracy?

Written 2026-11-12, before any number of this folder was computed. Offline only: no Jev or Claude
call; every answer used here is already stored.

## Why

Jev's ranking of changes is mostly their size. On MFEM the added-line count alone has AUC 0.866 and
LO's mean seat p 0.883 (`../mfem-set/score.log`). LO's calibration sees only each seat's p(REJECT),
not the size. If size carries information that Jev's answers lack, or tells where Jev's p misleads,
giving it to WaRF can raise the accuracy; if not, the size arms show that too.

## Arms (all decided with WaRF's own functions, as `../lo-dev/lo_offline.py`)

- **LO**: the five persona seats as tested (SKEPTIC, ADVOCATE, AUDITOR on jev-1.14; TEST-FOCUSED,
  BOUNDARY on jev-1.13), Platt per seat, groups averaged and summed, boundary after each group, tau.
- **V1**: one Jev seat (the usual question, jev-1.14), calibrated the same way. Reference only.
- **SIZE**: one seat whose readout is the added-line count, p = sigmoid(ln(1 + added) - 3), Platt
  calibrated like any seat, its own group (provider `size`). The size-only baseline.
- **LO+SIZE**: LO's seats plus the size seat as a third group. This is what WaRF would do with a
  size seat today (ADR 0002's evidence seats): it sums the groups as if independent.
- **JOINT**: one logistic regression (weak prior) of the label on three inputs: the mean Platt input
  of the jev-1.14 seats, that of the jev-1.13 seats, and -ln(1 + added). Its log-odds minus the
  training base rate is compared with the domain tau. This would be a new WaRF calibrator that
  fits the seats and the size together, so that shared information is not counted twice.

The added-line count is that of the file's diff in the item's input (above WaRF's separator).

## Measures

1. **G+Smo, development**: stratified 10-fold cross-validation, 5 repeats, over the 352 judged
   G+Smo items (dev 132 + confirm 220); calibration from training folds only. Balanced accuracy.
2. **MFEM, one look**: calibrate on all 352 G+Smo items, decide the 300 MFEM items. Balanced
   accuracy; exact McNemar against LO and against SIZE.
3. For information: the same cross-validation within MFEM.

## Decision rule (fixed now)

The candidate is whichever of LO+SIZE and JOINT has the higher cross-validated balanced accuracy on
G+Smo. On MFEM it **raises accuracy** if it beats LO with exact McNemar p < 0.05 **and** beats SIZE
(higher balanced accuracy), so that the gain is not size alone. Higher than LO with p >= 0.05 is
**not shown**. Otherwise **no gain**.

Caveat: MFEM is not fresh. LO's MFEM decisions and the AUC of the size there have been seen; only
the size arms' MFEM decisions are new. A gain here would still need a fresh set to be claimed.

## Result (2026-11-12, `size_seat.py`, `size_seat.log`, `size_seat.json`)

The offline LO gives all 300 of WaRF's logged MFEM decisions when calibrated as in the MFEM test.

| Balanced accuracy | G+Smo, cross-validated (352) | MFEM, calibrated on G+Smo (300) | MFEM, cross-validated |
|---|---|---|---|
| V1, one Jev seat | 73.8% | 75.3% | 77.0% |
| SIZE, the size seat alone | 74.6% | 79.3% | 79.2% |
| LO, five persona seats | 76.3% | 78.7% | 81.1% |
| LO+SIZE, size as a third group | 75.7% | 83.0% | 82.9% |
| **JOINT**, seats and size fitted together | **76.9%** | **84.3%** | **84.3%** |

- The candidate by G+Smo cross-validation is JOINT.
- On MFEM, JOINT beats LO by 5.7 points: only JOINT right on 27 items, only LO on 10, p 0.0076.
- It beats SIZE by 5.0 points: 22 against 7, p 0.0081.
- **Verdict by the rule above: RAISES ACCURACY.**

**Controls** (`controls.py`, `controls.log`; run after the result, outside the rule):

- **Most of JOINT's gain is the joint fit, not the size.**
  - JOINT without the size input already reaches 81.7% on MFEM, 3.0 of the 5.7 points over LO.
  - Its fitted weights are −0.03 for the jev-1.14 mean input, +0.53 for jev-1.13 and +0.66 for
    the size. Fitted together, the jev-1.14 seats add almost nothing once jev-1.13 is counted.
    LO's sum counts both versions in full.
- **The size adds 2.6 points**: 23 against 15 items, p 0.26, not significant on its own.
  - With the sizes shuffled across items, JOINT falls to 81.0–82.3%, the no-size value. So the
    size input works only through the real sizes.
- **Size alone beats one Jev** on both projects (74.6 against 73.8, 79.3 against 75.3).
  - Part of this may come from how the labels are made: B-SZZ blames lines that a later fix
    deletes, so larger changes are more likely to be called defective.
  - The clean controls are matched on input size, not on added lines.

What this means for WaRF: the candidate change is a calibrator that fits the groups' weights
together instead of summing separately calibrated groups. That is a change to ADR 0001's pooling,
and its gain needs a fresh set. Whether to give it the size is a second, weaker question.
