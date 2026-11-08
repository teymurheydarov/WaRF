# Spec: log-odds aggregation (`--aggregate logodds`)

Decision record: [`docs/adr/0001-pool-calibrated-log-odds.md`](../adr/0001-pool-calibrated-log-odds.md).
Status: implemented on branch `probability-pooling`, revised after an independent review (2026-11-03).
`vote` mode (SPECIFICATION.md §2) is unchanged and remains the default.

## 1. Scope

- **Applies to:** `run_review(..., aggregate="logodds")`, and `warf review` and `warf review-commit`
  with `--aggregate logodds`.
- **Not in scope:** the MCP server keeps `vote` mode, and there is no profile-level setting.
- **Unchanged:** the weight update (`apply_oracle`, ω). ω is still learned and still ranks the
  agents (§4).

## 2. Notation

- Sign convention as in WaRF: positive evidence favours APPROVE.
- `y` is the developer's label of a past session: `+1` APPROVE (clean), `−1` REJECT (defective).
- `logit(q) = ln(q / (1 − q))`.
- `p` is a decision agent's p(REJECT) for the change under review, read as described in §7 and
  clamped to `[0.01, 0.99]`.
- `r = logit(1 − p) = ln((1 − p) / p)` is the agent's raw log-odds for APPROVE.
- A **reviewer** is one agent name, persona text (`persona_hash`), model (`provider/model`) and
  evidence source (`AgentProfile.evidence`, empty for the common input). The same persona text on
  another model, or shown other evidence, is another reviewer.

## 3. Evidence per vote

Each vote `i` contributes evidence `e_i` in natural log-likelihood-ratio units:

| Agent kind | Calibrated? | Evidence `e_i` | `calibration` tag |
|---|---|---|---|
| Decision (usable `p`) | yes | `a + b · r − logit(π)` | `platt` |
| Decision (usable `p`) | no | `clip(r, ω · LLR_REJECT, ω · LLR_APPROVE)` | `capped` |
| Text, or decision without a usable `p` | yes | `ln(P(vote │ clean) / P(vote │ defective))` | `rates` |
| Text, or decision without a usable `p` | no | `ω · LLR(vote)`, exactly the `vote`-mode step | `omega` |

- `ω` is the agent's decay-adjusted weight in the review's domain.
- `LLR_APPROVE ≈ +0.981` and `LLR_REJECT ≈ −1.253` are the existing constants.
- **A usable `p` agrees with the vote it came with.**
  - `p > 0.5` must come with REJECT and `p < 0.5` with APPROVE; `p = 0.5` goes with either.
  - Otherwise the vote is treated as if it had no `p`, so a REJECT can never count as APPROVE
    evidence.
- **Platt fit:** `(a, b)` is the MAP logistic regression of `y = clean` on `r` over the reviewer's
  labelled history (§5).
  - The prior is `a ~ N(0, 1)`, `b ~ N(1, 1)`.
  - It is solved by Newton's method with step halving: the log posterior never decreases, at
    most 50 iterations, and no convergence means uncalibrated.
  - `π = (n_clean + 1) / (n + 2)` is the smoothed clean share of that history. Subtracting
    `logit(π)` turns the fitted posterior log-odds into a likelihood ratio, so the base rate is not
    counted once per agent.
- **Rates**, with Laplace smoothing:
  - `P(APPROVE │ clean) = (approve_on_clean + 1) / (n_clean + 2)`;
  - `P(APPROVE │ defective) = (approve_on_defective + 1) / (n_defective + 2)`;
  - the REJECT rates are their complements.
- **Calibrated** means at least `MIN_PER_CLASS` labelled votes of each truth class: 10 for a Platt fit
  (counting only votes with a `p`), 5 for rates.
- **The SAST vote** (Bandit): `e = SAST_OMEGA · LLR(vote)`, tag `fixed`.

## 4. Pooling, stopping, decision and confidence

- **Groups:** a vote's group is its `provider/model`, or the agent's name when it has no provider
  (SAST). A model's evidence is the mean of its seats' evidence. Different models' evidence is
  summed: `Λ = Σ_g mean_{i ∈ g} e_i`, logged as `sprt_lambda`.
- **Evidence sources (ADR 0002):** a seat whose profile sets `evidence` (for example
  `"whole-commit"`) forms its own group, `provider/model#evidence`.
  - Seats of one model shown the same input still count once; a seat shown other evidence counts
    separately.
  - **Input, in both modes:** such a seat reviews `seat_inputs[evidence]`, from
    `run_review(..., seat_inputs={evidence: input})`, instead of the common input.
  - **Refusals, in both modes:** a tagged seat without an input raises `ValueError` rather than
    reviewing the common input and, in this mode, counting it twice. The debate round, which shows
    every seat one input, refuses tagged seats.
  - **Python API only for now:** `warf review`, `warf review-commit` and the MCP server pass no
    `seat_inputs`, so a saved profile with a tagged seat is refused there.
  - **ω is not kept per source:** a seat's ω is learned from its votes whatever it was shown. Only
    the calibration of §5 keeps sources apart.
  - Every rule below (order, early stop on whole groups, disagreement) applies to these groups.
- **Order:**
  - agents are ranked heaviest ω first, as in `vote` mode;
  - the seats of one model are then asked together;
  - models are asked in the order of their heaviest seat.
- **Early stop:**
  - **when it is tested:** only when every model that has voted has answered with all its seats
    (a timed-out seat counts as answered). A mean, unlike a sum, can be pulled back by the same
    model's later seats, so a partial model never decides.
  - **what it gives:** Λ ≥ A (+2.890) returns APPROVE [HIGH], and Λ ≤ B (−2.251) returns REJECT
    [HIGH].
  - **no HIGH while models disagree:** if any model's mean is `≥ +ln 2` and another's `≤ −ln 2`,
    there is no HIGH; the review goes on, or ends at LOW.
  - **one model alone** whose calibrated evidence passes a boundary does stop the review. The next
    model is not asked, so disagreement cannot be known.
  - **with `no_early_stop`,** every agent is asked and the first crossing is the verdict, as in
    `vote` mode.
- **Threshold:** `τ_d = logit((1 + θ_d) / 2)`, which gives LOGIC 0, SECURITY +0.405 and PERFORMANCE
  −0.201.
  - τ is a threshold on evidence at prior odds 1:1. The base rate of clean changes is not added,
    just as `vote` mode's Λ starts at 0.
  - On a corpus that is mostly clean, a calibrated panel's decisions therefore lean toward REJECT
    compared with a full posterior. This is deliberate: developer-labelled sessions are not a fair
    sample of the base rate.
- **Pool exhausted:**
  - APPROVE if Λ ≥ τ, else REJECT;
  - LOW if `|Λ − τ| < ln 2` or the models disagree (as above), else MEDIUM.
- **What this means for an uncalibrated agent at ω = 0.5:** its evidence is at most `+0.490`
  (APPROVE) or `−0.627` (REJECT).
  - **LOGIC:** a single model stays at LOW. It reaches MEDIUM once ω > 0.553 (REJECT) or ω > 0.707
    (APPROVE).
  - **SECURITY:** a single model's unanimous REJECT is MEDIUM (`|−0.627 − 0.405| > ln 2`). Its
    unanimous APPROVE is at most LOW, and below ω ≈ 0.413 it becomes REJECT.
  - **PERFORMANCE:** REJECT stays LOW; APPROVE is LOW up to ω ≈ 0.501, then MEDIUM.
  - These follow from comparing weak, uncalibrated evidence with a non-zero τ and are intended: a
    reviewer without a track record cannot approve security code with confidence.
- **`normalised_score`:** `2 · σ(Λ − τ) − 1`, in [−1, 1] with its threshold at **0**, not at θ. The
  record logs `tau` next to `theta` (§6).

## 5. Calibration data

- **Source:** the session log that `paths.sessions_path()` resolves, or the `log_path` passed to
  `run_review`. It is read once per review; invalid UTF-8 is replaced, and lines that are not JSON
  objects with an oracle object and a vote list are skipped.
- **Labels:** sessions whose oracle has type `DEVELOPER`; `y = oracle.x_star`.
- **Votes:** a vote counts for a reviewer when its agent name, persona fingerprint, `provider`,
  `model` and evidence source all equal the reviewer's (§2). The provider and model are the ones the
  vote was actually cast with.
  - A vote with no `evidence_source` belongs to a seat on the common input, so a seat shown other
    evidence never calibrates from such votes.
  - This is **stricter than `apply_oracle`**, which accepts votes without a fingerprint. Votes
    without one (WaRF's labelled corpus before persona fingerprints and provider fields existed)
    never calibrate. That corpus therefore starts uncalibrated: its votes do not record which model
    cast them.
- **Round 1 only:** only top-level `votes`, never debate rounds.
- **The decision agent's `p`:** the vote's `p_reject` field (clamped) if numeric, otherwise the
  readout in `reasoning` (§7).
- **Domains are pooled:** labels are too few to split them.

## 6. Logging

In `logodds` mode the session record gains:

- `"aggregate": "logodds"`;
- `"tau"`, the decision threshold of §4;
- on each vote:
  - `"p_reject"` (`null` without a usable readout);
  - `"evidence"` (`e_i`, rounded to 4 decimals);
  - `"calibration"` (the §3 tag).

`vote`-mode records are unchanged.

In both modes, a vote cast by a seat shown other evidence carries `"evidence_source"`. Votes of
seats on the common input omit it. The calibration of §5 reads it from the log.

## 7. Reading a decision agent's probability

The decision provider renders its answer as:

```
REJECT
p(APPROVE)=0.12  p(REJECT)=0.88  confidence=0.76  [jev-1.13.0: decision model, no reasoning]
```

- `p` is read only when the text carries the provider's tag `decision model, no reasoning`, and only
  when **both** `p(APPROVE)` and `p(REJECT)` are present and sum to within 0.05 of 1. The provider
  renders a missing probability as `0.00`, so such an answer is not read as a probability.
- Text agents are never read.
- The readout has two decimals, so `|r| ≤ logit(0.99) ≈ 4.60`.

## 8. Errors and edge cases

- **`aggregate` not in {`vote`, `logodds`}:** `ValueError`.
- **`aggregate="logodds"` with `debate=True`:** `ValueError`. The CLI refuses the combination before
  reviewing anything: argparse error, exit 2.
- **No labelled history, or a missing or unreadable log:** every reviewer is uncalibrated
  (`capped` / `omega`), and the review runs.
- **Timeouts:** a timed-out agent contributes nothing, and its seat counts as answered for the
  early-stop test.
- **Retired personas and changed models:** a reviewer whose persona text or model changed starts
  uncalibrated.

## 9. Properties the tests check (`tools/test_logodds.py`)

1. **One model counts once.** Five uncalibrated REJECTs of one model at ω 0.5 pool to Λ ≈ −0.627:
   REJECT [LOW] in LOGIC. `vote` mode stops after 4 votes at Λ ≈ −2.51 with REJECT [HIGH].
2. **Models add up,** and agreeing models with a clear margin get MEDIUM.
3. **Uncalibrated decision evidence is capped** at the `vote`-mode step.
4. **The Platt fit learns the slope** (≈ 0.5) and **removes the base rate** (≈ 0 on an uninformative
   reviewer of an 80 %-clean history).
5. **Text rates** give exactly `ln 0.2` for a 9-of-10 rejector.
6. **Calibration is per reviewer:** retired persona votes and votes by another model are not used;
   only DEVELOPER labels count; `p_reject` from the vote field is used and clamped.
7. **Readouts:**
   - one without probabilities is not read;
   - prose is never read;
   - a `p` that contradicts the vote falls back to the vote.
8. **An unreadable log** (invalid bytes, non-object JSON lines) leaves agents uncalibrated.
9. **Decisions in all three domains:** τ, the SECURITY and PERFORMANCE cases of §4, and the
   normalised score measured from τ.
10. **Disagreement:**
    - it gives LOW even with a margin above ln 2;
    - a crossing reached while models disagree is not HIGH;
    - a single calibrated model beyond A stops alone.
11. **`run_review`:**
    - the boundary waits for whole models (seats +3, −1, −1 of one model are all asked, and the
      verdict does not depend on seat order);
    - two agreeing calibrated models reach HIGH;
    - the record carries the §6 fields;
    - `vote` mode is unchanged.
12. **Errors:** `logodds` with debate and an unknown mode raise `ValueError`; the CLI exits 2.
13. **Evidence sources (ADR 0002):**
    - two seats of one model with different evidence are summed, and the same two without a tag are
      averaged;
    - the tag survives save/load;
    - a tagged seat without an input is refused, and with one, each seat is shown its own input, in
      both modes;
    - debate refuses tagged seats, and still runs for untagged ones;
    - the log records the source of tagged seats only;
    - calibration keeps sources apart;
    - a file seat beyond B ends the review before the whole-commit seat is asked.

`.warf-experiments/logodds-replay/mutants.py` breaks the code eleven ways, one at a time, in a copy
of the package (calibration scope, the early-stop test, disagreement, readout check, contradiction
check, log decoding, mean versus sum, base rate, τ, persona filter, CLI check). The tests catch
11 of 11. `mutants_evidence.py` breaks the evidence-source change ten ways (pooling, early stop, refusal,
seat input, both again in vote mode only, debate refusing every seat, log write, a log key on
untagged votes, calibration); the tests catch all ten.

## 10. Known limitations

- **Dashboards:** `dashboard.html` and `slide06` draw every session as a `vote`-mode ω·LLR trace,
  so a `logodds` session's detail trace does not match its logged Λ. Its verdict, confidence and
  `sprt_lambda` are right.
- **Directory review** skips files that have already been reviewed, so `--aggregate logodds`
  cannot be applied to them without a new data directory.
- **Text agents state no probability,** so their evidence takes one of two values.
- **Out-of-fold replay on the 100 stored commits** (`.warf-experiments/logodds-replay/replay.log`,
  full pools, Claude's stored blinded probabilities standing in for a decision-style seat):
  - Jev + Laya + Claude: AUC 0.731, balanced accuracy 0.61;
  - Claude alone: AUC 0.737, balanced accuracy 0.65;
  - the same three in `vote` mode: AUC 0.616;
  - no gain over the best member.
