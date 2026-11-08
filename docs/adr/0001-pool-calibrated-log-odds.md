# ADR 0001: Pool calibrated log-odds instead of counting votes

- Status: accepted, implemented as an opt-in mode (`--aggregate logodds`); the default stays `vote`.
  Revised the same day after an independent review: calibration is per model, the boundary is
  tested on whole models, and readouts are checked.
- Date: 2026-11-03
- Spec: [`docs/spec/logodds-aggregation.md`](../spec/logodds-aggregation.md)

## Context

WaRF's panel has never beaten a single agent of the same model (SPECIFICATION.md §7.6: 5/7 against
SKEPTIC alone 6/7; old corpus 35/62 for both WaRF and the first agent asked; 100 gismo6 commits: Jev
balanced accuracy 0.53 for WaRF's defaults against 0.59 for one agent). The analyses in
`.warf-experiments/old-logs/` and `.warf-experiments/why-warf/` trace this to three properties of
the aggregation, not to the idea of a panel:

1. **Votes discard the probability.** A decision model's p(REJECT) of 0.51 and 0.99 enter as the same
   vote. On the stored 100 commits a Jev + Laya + Claude panel run through WaRF's votes ranks at
   AUC 0.616, below Claude alone (0.745). Summing the same agents' raw log-odds ranks at 0.732
   (+0.075 over the mean member); calibrating them out of fold, at 0.736 (+0.078)
   (`.warf-experiments/why-warf/mixed/`).
2. **Every vote is credited with fixed, assumed evidence.** `LLR_APPROVE = ln(0.80/0.30)` and
   `LLR_REJECT = ln(0.20/0.70)` assume a reviewer that approves 80 % of clean and 30 % of defective
   changes. Measured per-vote evidence was far weaker (Jev under personas about +0.12 / −0.28).
3. **Correlated seats are counted as independent.** Five personas on one model correlate 0.89
   (Jev) and 0.80 (Laya) within label: about 1.1 effective reviewers. The SPRT adds their five
   votes, so a shared error becomes REJECT [HIGH].

The weight ω (Beta mean of vote accuracy) does not repair this: accuracy tracks the label base
rate, not discrimination, and it cannot express that a reviewer is worse than chance.

## Decision

Add a second aggregation mode, `logodds`, selected per run (`warf review --aggregate logodds`,
`warf review-commit --aggregate logodds`, `run_review(aggregate="logodds")`):

- **Each vote contributes evidence in natural log-likelihood-ratio units** (positive = APPROVE):
  - a decision model (Jev, Laya) contributes its own log-odds, calibrated against the developer
    labels of its past votes (Platt scaling, minus the training base rate);
  - a text model contributes the measured likelihood ratio of its APPROVE/REJECT label from the
    same labelled history;
  - until an agent has enough labels, its evidence is capped at what its vote is worth in `vote`
    mode (ω · LLR), so an uncalibrated agent never weighs more than it does today.
- **Seats of one model count once.** Evidence is averaged within a model (same provider and model)
  and summed across models.
- **The decision threshold is the domain's θ mapped to log-odds**, `τ = logit((1 + θ) / 2)`. It is a
  threshold on evidence at prior odds 1:1. As in `vote` mode, no base rate is added; developer-labelled
  sessions are not a fair sample of it.
- **Confidence:**
  - **HIGH** when the pooled evidence crosses WaRF's SPRT boundaries A / B. The boundary is tested
    only on whole models (all seats of every model seen so far have answered), and never while
    models disagree.
  - **LOW** when the margin to τ is under ln 2, or when two models point in opposite directions by
    at least ln 2 each. Model disagreement becomes a reason to send the change to a human.
  - **MEDIUM** otherwise.
- Calibration is computed from the session log at review time, with no new state file. Only
  labelled votes cast by the same reviewer count: the same agent, persona text and model. The same
  persona on another model is another reviewer.

## Consequences

- `vote` mode is unchanged and remains the default, so the corpus, the dashboards and every
  earlier experiment reproduce exactly.
- In `logodds` mode a five-persona panel on one model behaves like one reviewer, as the data say it
  is. It reaches HIGH only when that model's calibrated evidence alone crosses a boundary.
- A panel of different models is where the mode can gain. The implementation was replayed out of
  fold on the 100 commits (`.warf-experiments/logodds-replay/replay.log`; full pools, with Claude's
  stored blinded probabilities standing in for a decision-style seat).
  - **Ranking:** Jev + Laya + Claude scores AUC 0.731 (balanced accuracy 0.61), against 0.616 for the
    same three in `vote` mode and 0.737 (0.65) for Claude alone. It keeps the averaging benefit over
    the mean member but does not beat the best member. A gain over the best member has not been
    shown and is not claimed.
  - **Confidence bands:** MEDIUM verdicts were right 42 of 57 times, LOW 16 of 39 and HIGH 3 of 4.
- WaRF's existing labelled corpus records no persona fingerprint or model on its votes, so it never
  calibrates: a profile starts uncalibrated in this mode.
- Calibration needs labels: at least 10 labelled votes of each truth class for a decision agent and
  5 for a text agent, per persona version. Before that the mode is only as aggressive as `vote` mode.
- Text agents state no probability, so their evidence is two-valued (one value per label). Asking a
  text agent for a probability is left open (it would change the reply format and so every text
  agent's prompt).
- `--debate` is not supported with `logodds` (the debate showed no measurable benefit, and its
  Round-2 votes are not independent of Round 1).
- The decision model's probability is read from WaRF's own readout line (`p(REJECT)=0.88`), which
  is rounded to two decimals; log-odds are therefore bounded at about ±4.6.

## Alternatives considered

- **Replace the default with `logodds`.** Rejected for now: it would change every verdict and break
  the reproducibility of the corpus and the talk's figures. Revisit when a held-out test shows a
  gain over the best single agent (SPECIFICATION.md §1, principle 3).
- **Keep votes, learn better ω.** Rejected: a probability-weighted vote still discards the
  per-review confidence, which is where the ranking information is.
- **Fit one logistic regression over all agents (stacking).** Handles correlation exactly, but needs
  far more labels than WaRF has (one weight per agent, jointly estimated). Averaging within a model
  is the robust small-sample version of the same idea.
- **Discount by an estimated effective number of reviewers.** Needs per-pair error correlations
  from labelled data; the model-identity rule needs none and matches what was measured (seats of
  one model ≈ one reviewer).
