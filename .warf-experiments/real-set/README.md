# Real G+Smo defects: WaRF's strongest fair chance

2026-11-05. Planted defects that are visible in the diff are caught by every Claude arm (`../hard-set/`:
20 of 20, even by the most lenient persona). So leniency never costs recall there, and a panel can
only help by removing false alarms. Real defects are different: they are often subtle, so a lenient
panel can miss them. This set tests whether WaRF earns its cost when missing defects matters.

## The set (`build_real.py`, `build_clean.py`, `select_real.py`)

**Defective items:** real changes to C++ files under `src/` in G+Smo's history (the gismo6 clone),
mined by the Laya sweep (B-SZZ).
- A later fix of kind "defect" touched the lines this change added. The fix came within 60 days,
  changed at most 3 files, and its subject names a bug.
- 150 candidates were drawn, one file per commit. Commits reviewed in any earlier set are excluded.
- **Two independent judges** (Claude agents with read-only git, who see the fix) decide whether the
  fix repairs a real defect that **this** change introduced. Only candidates both confirm are kept.
- The reviewers never see the fix.

**Clean items:**
- One clean control per defective item, from `clean_pool.jsonl`. These are changes whose added lines
  all still survive unchanged at `origin/dev`, checked without Claude.
- Each control is matched by commit date, then by input size.

**The input** is what WaRF's review path shows: the file's diff with 30 lines of context and the
enclosing function bodies.

## Preregistration

Fixed on 2026-11-05, before any reviewer saw any item of this set.

**Arms.** All run through `../planted/run_planted.py --set .warf-experiments/real-set`, with Claude Opus
5.5 through the isolated CLI:

| Arm | Kind | What it is |
|---|---|---|
| `claude` | single call | One Claude, the sweep's question |
| `claude-strict` | single call | One Claude, `STRICT_PERSONA` |
| `claude-advocate` | single call | One Claude, WaRF's ADVOCATE persona |
| W1 `claude-standard` | WaRF | WaRF's default five personas, default review |
| W2 mixed log-odds | WaRF | CLAUDE + JEV in WaRF's log-odds mode (ADR 0001), with default early stopping |

For W2:
- **Its inputs:** the stored answers of the `claude` and `jev` arms, replayed through WaRF's real
  `run_review(aggregate="logodds")`, as in `../planted/score_planted.py`.
- **Its calibration:** learned out of fold, from 5 folds stratified by class with seed 7.
- `jev` is run only as W2's second seat. Laya is left out: it detected nothing on the planted set.

**Metrics:**
- **Primary:** balanced accuracy over defective and clean items.
- **Also reported:** recall on defective items, false-alarm rate on clean items, and the subset whose
  defect both judges call visible from the diff.

**Tests:**
- exact two-sided McNemar on the items only one arm gets right;
- a bootstrap stratified by class (2000 resamples, seed 4), paired across arms by item.

**When WaRF wins.** The case is made if a WaRF arm (W1 or W2) beats **each** single-call arm, with:
- McNemar p below the Holm threshold across the two WaRF arms (0.025 for the smaller p, 0.05 for the
  other);
- a bootstrap lower bound above 0.

**Otherwise:**
- a WaRF arm with a positive difference against every single-call arm is reported as "favours WaRF,
  not shown";
- anything else is reported as no case.

**Fixed now:**
- No relabelling after the run enters the primary result.
- Any re-score is reported separately.

## Status

**The set is frozen** (`select.log`):

| | Count |
|---|---|
| Candidates | 150 |
| Both judges confirm the change introduced the defect | 66 |
| The judges disagree (`disagreements.tsv`) | 10 |
| Both reject | 74 |

- **`items.jsonl`:** the 66 defective items plus 66 matched clean controls, 132 items in all. The
  median date gap between a defect and its control is 93 days.
- **Visibility,** as both judges call it: 41 defects are visible from the diff, 17 need another file,
  2 are not visible from code, and the judges split on 6.

## Result (`score_real.py`, `score.log`), 2026-11-05

All five arms answered all 132 items. A usage-limit stop left 27 errors; the affected reviews were
re-asked in full, and every arm has exactly one complete record per item.

| Arm | Calls | Balanced accuracy | Defects caught | False alarms |
|---|---|---|---|---|
| One Claude, strict bar | 132 | **0.856** | 52/66 | 5/66 |
| ADVOCATE alone | 132 | 0.841 | 55/66 | 10/66 |
| W1 WaRF five personas | 597 | 0.826 | 55/66 | 12/66 |
| W2 WaRF Claude + Jev log-odds | 264 | 0.795 | 56/66 | 17/66 |
| One Claude, plain question | 132 | 0.758 | 64/66 | 30/66 |
| Jev alone (W2's second seat) | 132 | 0.705 | 60/66 | 33/66 |

**Preregistered comparisons:**

| | vs one Claude | vs strict | vs ADVOCATE |
|---|---|---|---|
| W1 | +0.068 (p 0.12) | −0.030 (p 0.39) | −0.015 (p 0.73) |
| W2 | +0.038 (p 0.41) | −0.061 (p 0.24) | −0.045 (p 0.39) |

**Preregistered verdict: no case for WaRF.** Neither WaRF arm has even a positive difference against
every single-call arm.

**Verification** (`verify/audit-recompute/`, `verify/drivers/`, `verify/critic/`):
- **The numbers:** every number reproduces exactly, and W2 re-derived from the spec matches the
  replay on every item, with no fold leakage.
- **What W1 is:** on this set, a 3-of-5 majority vote.
  - Its decision equals its own ADVOCATE seat's vote on 128 of 132 items.
  - ADVOCATE alone does at least as well on both counts, with 4.5 times fewer calls.
- **How large a panel gain could be:** the 95 % upper bound for W1 over strict or ADVOCATE is about
  +0.02. That is the size of the noise from re-running one prompt: W1's ADVOCATE seat and the
  ADVOCATE arm agree on 124 of 132 items.
- **The gain over the plain question comes from the ADVOCATE persona, not the panel:** ADVOCATE
  alone is +0.083 over the plain question.
- **W2 is almost an AND of Claude and Jev.** Jev's frequent REJECTs carry little information.
- **No relabelling gives WaRF a case.** Of the plain question's 30 rejected clean controls, a Claude
  judge found:

  | Class | Count |
  |---|---|
  | Real defect the change introduced | 2 |
  | Real defect, in unchanged context lines | 5 |
  | Debatable | 5 |
  | False alarm | 18 |

  No WaRF arm beats every single-call arm under any relabelling, and none has p below 0.12.
- **Confounds, checked:**
  - Defective changes are larger: median added lines 20 against 2, and size alone gives AUC 0.83.
    Reweighting by size keeps the order: strict 0.852, ADVOCATE 0.849, W1 0.819.
  - Defects with more than 30 added lines have no clean control.
  - Claude's memory of G+Smo history shows no sign of helping.
- **Audit trail:** `score_real.py` was last edited, to fix the replay's call signature, after the
  first records were written. It still applies the README rule as written.

**What limits every arm is the single-file input.**
- It causes most of the plain question's false alarms: "the companion file or callers were not
  updated", when the same commit did update them.
- It causes most of the strict bar's misses: 9 of its 14 missed defects need another file. On
  defects visible from the diff it catches 38 of 41.
- These are exactly the gaps that ADR 0002's evidence seats target: the whole-commit reader and the
  code-base checker.

## Second preregistration: the whole-commit reader (ADR 0002)

Fixed on 2026-11-05 before either whole-commit arm ran. It uses the same 132 items and labels, which
are not changed.

**Input** (`build_commit_inputs.py`, `commit_inputs.jsonl`). It is a superset of the single-file view:
- the commit message;
- the item's own `code`, unchanged;
- the `-U10` diffs of every other file the commit touched.

Nothing later than the commit is included. Other files are cut at 60,000 characters, which happens in
4 of the 132 commits. The median input is 13.5k characters.

**WaRF change it needs**, test-first in `tools/test_logodds.py`:
- `AgentProfile.evidence` marks a seat that is shown other evidence.
- In log-odds mode, seats of one model with different evidence pool as separate sources (summed).
  Seats shown the same input still count once.
- Limitation: `run_review` still sends one input to every seat. So the panel below is scored by
  replaying each seat's stored answer, as W2 was, not by a live run.

**New arms** (Claude Opus 5.5, isolated CLI):

| Arm | What it is |
|---|---|
| `claude-commit` | One Claude shown the whole commit, the sweep's question |
| `claude-commit-strict` | One Claude shown the whole commit, `STRICT_PERSONA` |
| W3, the evidence panel | Two seats with the same strict question: `claude-strict` (single file) and `claude-commit-strict` (whole commit, `evidence="whole-commit"`) |

W3 runs in WaRF's log-odds mode with default early stopping. Its calibration is learned out of fold,
with the same 5 folds and seed as W2. It is scored by replaying the two stored answers through
`run_review(aggregate="logodds")`.

**When W3 wins.** It must beat **each** single-call arm (`claude`, `claude-strict`, `claude-advocate`,
`claude-commit`, `claude-commit-strict`) in balanced accuracy, with:
- exact McNemar p < 0.05 (one WaRF arm, so there is no Holm step);
- a bootstrap lower bound above 0.

**Decisive comparison:** W3 against `claude-commit-strict`, one reviewer given all the evidence. If W3
does not beat it, the panel adds nothing over giving one reviewer the evidence. In that case the
result is about evidence, not about WaRF.

## Result of the second preregistration (`score_commit.py`, `score_commit.log`), 2026-11-06

All 132 items in every arm. The 12 reviews hit by usage-limit stops were re-asked in full.

| Arm | Calls | Balanced accuracy | Defects caught | False alarms |
|---|---|---|---|---|
| **W3 WaRF evidence panel** | about 245 | **0.879** | 56/66 | 6/66 |
| One Claude, whole commit, strict | 132 | 0.864 | 52/66 | 4/66 |
| One Claude, strict (single file) | 132 | 0.856 | 52/66 | 5/66 |
| ADVOCATE alone | 132 | 0.841 | 55/66 | 10/66 |
| One Claude, whole commit | 132 | 0.773 | 64/66 | 28/66 |
| One Claude, plain question | 132 | 0.758 | 64/66 | 30/66 |

**Comparisons, W3 minus each single-call arm:**

| Single-call arm | Difference | McNemar p |
|---|---|---|
| plain question, single file | +0.121 | 0.011 |
| plain question, whole commit | +0.106 | 0.020 |
| strict, single file | +0.023 | 0.375 |
| ADVOCATE | +0.038 | 0.180 |
| strict, whole commit (the decisive comparison) | +0.015 | 0.688 |

**Verdict under this preregistration:** W3 does not win, and the decisive comparison fails. The
preregistration therefore says the result is about evidence, not about WaRF. `score_commit.py` prints
"favours W3, not shown", a label carried over from the first preregistration; this one does not
define it.

**What the recheck found** (`verify/audit-w3/`, `verify/what-drives-w3/`, `verify/critic3/`):
- **The numbers:** every number reproduces, and W3 re-derived from the spec matches WaRF's replay on
  every item. The two new arms really got the whole commit, with nothing later than the commit, which
  was checked against git for 10 items.
- **W3 is exactly "REJECT if either strict seat rejects"** on all 132 items.
  - Both strict seats raise few false alarms, so a calibrated REJECT always outweighs an APPROVE.
  - With two yes/no seats, log-odds pooling can only produce OR, AND or one seat's vote. WaRF's only
    part was picking OR, from the out-of-fold labels.
- **Its margin over the strict arms rests on 5 or 6 differing items.** Re-running one prompt flips
  4 to 8 items, so the margin is the size of rerun noise.
- **The whole commit itself is not shown to help:** strict with the whole commit against strict on
  one file is 6 items against 5.
- **Half of W3 was known when it was designed:** the `claude-strict` answers had already been seen,
  and this is the third WaRF arm tried on this set. Treat the p-values as optimistic.
- **Power:** showing +0.015 to +0.023 would take about 600 to 1,600 items.

**In short:** this is the first WaRF arm ahead of every single call, but only as anecdotal evidence.
The gain is "ask two strict reviewers, reject if either objects". This set cannot tell that apart from
asking one strict reviewer twice.

**The test that would settle it**, preregistered:
- about 600 fresh items, none used before;
- W3 against OR(strict, the same strict prompt asked again on the single file). This tests whether
  the different evidence adds anything over sampling twice;
- W3 against strict on the whole commit.

**Gaps in the WaRF change** (`AgentProfile.evidence`) found by the recheck, **fixed on 2026-11-06**,
each with a test written first:
- **Inputs:** `run_review` takes `seat_inputs`, and a tagged seat reviews its own input in both
  modes. Without that input it is refused rather than counted twice, and the debate round refuses
  tagged seats.
- **Logging:** tagged votes log `evidence_source`; untagged ones keep their shape.
- **Calibration:** keyed by the evidence source as well.
- **Tests:** early stopping with evidence seats is now tested.
- **Spec:** `docs/spec/logodds-aggregation.md` §2, §4, §5, §6 and §9 are updated.
- **Mutation checks:** `mutants_evidence.py` catches 10 of 10, and `mutants.py` 11 of 11.
- **Re-scoring:** `score_commit.py` passes the whole-commit input and tags that seat's training votes.
  Re-scoring gives a `score_commit.log` identical to the one above.
- **A cold review** found six further points, all addressed: a debate test that also passed when
  every debate was refused; vote mode untested; an unused read-back of the tag in
  `result_from_session`, now removed; untagged votes' log shape untested; CLI/MCP refusal
  undocumented; a stale definition of a reviewer.

**Still open:**
- Tagged seats work through the Python API only; `warf review`, `review-commit` and MCP refuse them.
- ω is not kept per evidence source.
- An ADR 0001 issue the cold review noted (not this change): the early-stop count is keyed by the
  planned model, but pooling uses the model actually used. If a provider falls back to another
  model, a partial model could trigger the early stop.
