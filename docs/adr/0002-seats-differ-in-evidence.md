# ADR 0002: Seats that differ in evidence, not in persona

- Status: **proposed**. It is decided by the test in
  [`docs/spec/evidence-seats-test-plan.md`](../spec/evidence-seats-test-plan.md), which has three
  possible outcomes (§5 there):
  - **pass:** accept;
  - **fail:** the gain is excluded by the stated margin. Retire the panel and keep the harness.
  - **inconclusive:** neither. The design stays proposed and nothing is claimed.
- Date: 2026-11-04. Revised the same day after a feasibility and method review.
- Builds on: [ADR 0001](0001-pool-calibrated-log-odds.md) (log-odds pooling)

## Context

WaRF's premise is that several reviewers, weighted by how reliable each has been, make fewer
mistakes than one. That has not been shown.

- **The default panel is one model with five persona texts.**
  - **On the planted set** (`.warf-experiments/planted/`, 54 changes, each clean and with one
    planted operator flip), five Claude Opus seats scored 0.861 against one Claude's 0.824.
    - That is 5 items against 1 (p 0.22).
    - Every clean-code REJECT the panel made was one that one Claude also made.
    - Whether the seats differ by strictness or by sampling noise is untested: no item was asked
      twice with the same prompt.
  - **On 100 gismo6 commits** (`.warf-experiments/four-arms/`):
    - the panel scored −0.020 [−0.110, +0.070] against one Claude, and 0.559 against 0.557
      without the 18 changes the labels can never mark defective;
    - it rejected 9 of the 50 later-fixed changes, against 26 for one Claude;
    - these history labels cannot measure review skill, so this shows a direction, not accuracy.
- **Five Jev personas correlate 0.86–0.96,** about 1.1 effective reviewers.
- **Learned weights did not help.** ω is accuracy and tracks the base rate. On the old corpus they
  changed 4 decisions, all to wrong (sign p 0.125).
- **Only different models ever gained, and only a little:**
  - **History labels:** Jev + Laya beat their mean member, but in log-odds mode they gained nothing
    over Jev (AUC 0.644 against 0.637).
  - **Planted set:** Jev vetoing Claude's false alarms gave +0.028, which is not significant. The
    plain rule "REJECT only if Claude and Jev both reject" did at least as well (0.861 against
    0.852).
- **The earlier positive results have no comparison behind them:**
  - on the 12-file set, AUDITOR alone matched the panel;
  - the G+Smo reviews in the corpus are unlabelled (102 of the 104 sessions that mention gismo).

Combining reviewers can only help as far as their errors differ. Text instructions give a seat no
information or ability the model lacks, so they cannot be relied on to make its errors differ.

## Decision (proposed)

Rebuild the panel from seats that differ in **evidence**: what each one sees or can check. Pool them
in log-odds mode (ADR 0001).

| Seat | Evidence it adds | Kind |
|---|---|---|
| Build | Does the item's version of the code compile, with the touched templates instantiated? | tool |
| Tests | Do the unit tests that exercise the changed code pass? Abstains where no test exercises it. | tool |
| Whole-commit reader | All files of the commit and its message, not one file's diff | text model |
| Code-base checker | Read-only search over a snapshot of the item's version of the tree, used to check claims ("not declared", "takes two arguments") before voting | text model with tools |
| Second model family | A model trained apart from Claude | text or decision model |

Changes this needs in WaRF. They are new code, not reuse of the Bandit path:

- **Group by evidence source, not by model.**
  - Today `orchestrator._evidence_group` groups by `provider/model`, so the reader and the
    checker, both Claude, would be averaged into one.
  - Each seat gets its own group key. Seats that share a model *and* an input still count once.
- **Tool seats become profiles.** Each gets an `AgentProfile` whose `persona_hash` is a hash of its
  tool command and toolchain version, so `warf.calibration` can calibrate it from labels.
  - **Abstaining** ("no coverage") is logged apart from a tool error, and neither one votes.
  - Bandit today is a fixed vote with no profile and is not calibrated.
- **A pre-seat hook for every domain.** It takes the item's tree and runs the tool seats before
  the model seats. Today's SAST pre-vote runs only in SECURITY and only on a file path.
- **Per-seat inputs.** `run_review` passes the same `code` to every seat. The reader needs the whole
  commit, and the checker needs a snapshot path.
- **A second CLI configuration** for seats that use tools, logged with its command line. The
  current isolation (`--tools ""`) is kept for seats without tools.

Rules:

- **No seat may see anything later than the change, or the clean original of a planted item.**
  - Tool seats work on a snapshot (`git archive`) of the item's own version: the base tree with the
    item's change applied, planted or clean, and no `.git`.
  - The checker runs in a sandbox whose only readable path is that snapshot, and every tool call's
    path is logged.
- **The early stop orders the cheap, decisive seats first.** In the test, though, every seat
  answers every item and the SPRT is replayed afterwards (see the test plan), so that seats can be
  dropped one at a time.

## Consequences

- **Pass:** WaRF becomes a combiner of independent checks, which its specification (§3.1, "fault
  domains") asked for. The persona panel and `default_profiles()` are replaced, and the old corpus
  and dashboards stay as history.
- **Fail:** WaRF's honest role is the harness: deterministic aggregation, per-reviewer track
  records, labelling, calibrated confidence, and the CI and MCP plumbing. The README and the talk
  material say so.
- **Inconclusive:** nothing is claimed either way, and the report states the size a decisive test
  would need.
- **In every case,** persona panels on one model stop being presented as protection against
  hallucination.

## Alternatives considered

- **More or better personas:** rejected, because five were measured and showed no independent
  errors.
- **The same prompt sampled n times:** kept as a competitor in the test. Whether repeated CLI calls
  even differ is measured first.
- **Debate between seats:** rejected for now. It changed 11 of 420 Jev votes and did not help Laya.
- **One strong reviewer given all the evidence:** this is the decisive competitor (arm A5 in the
  test). If it wins, the panel adds nothing over giving one reviewer the evidence.
