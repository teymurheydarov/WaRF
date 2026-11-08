# Test plan: does an evidence-seat panel beat one good reviewer?

Decision record: [`docs/adr/0002-seats-differ-in-evidence.md`](../adr/0002-seats-differ-in-evidence.md).
Status: plan, nothing run. It was revised on 2026-11-04 after a feasibility and method review.

Sizes and margins below are provisional until the pilot (§6, stage 0) has measured what they depend
on. They are frozen in this file, with a date, **before** the first scored run. Any later change is
logged here with its reason.

## 1. The questions

- **Q1, panel against one reviewer with the same evidence.** Does WaRF's evidence panel (W) beat one
  Claude given everything W's seats see (A5)? This decides whether a *panel* is needed at all.
- **Q2, panel against plain review.** Does W beat the simple alternatives that ignore the evidence
  (A1 to A4)?
- **Q3, which seats matter.** Which seats add to W?

## 2. Answer keys

Both sets are built and frozen before any review.

**Set P: planted defects**, where the right answer is certain.

- **Base changes:** C++ changes from G+Smo's own recent history, taken from a full clone of
  `gismo` `origin/dev`. The `gs_unref` tree is not touched: it is shallow and carries local patches.
- **Building at the base's commit:** each base is built at its own commit. The pilot decides which
  eras build with the ucrt64 GCC toolchain; bases whose clean version does not build are dropped.
- **Plants must leave room for the panel:**
  - One-token flips were caught 52 of 54 times by one Claude, so they cannot show a panel catching
    more.
  - P therefore also has harder plants: a call that breaks a contract defined in another file, a
    wrong index or argument order that type-checks, a removed guard whose need is visible only in a
    caller.
  - The pilot must show one Claude's recall below about 0.85 on the plant mix before P is frozen.
- **A plant is kept only if** it compiles with the touched template instantiated, and two people
  independently mark it as not equivalent.
- **Bases are screened for defects already in the code** by a person, or by a model family used in
  no arm. A Claude screen would remove exactly the cases where vetoes of Claude helped.
- **Each base is reviewed clean and planted.**

**Set R: real defects**, the confirmatory set.

- **Defective:** a later commit fixes the same hunk within 30 days, its subject matches
  `label_laya_sweep.py`'s `BUG_WORDS`, and a person confirms that the fix repairs a defect the change
  introduced.
  - About 299 gismo6 commits meet the automatic part. At the rate seen in `four-arms`, about 170
    would be confirmed.
  - `origin/dev` 2025–2026 history is added.
- **Clean controls:** at least 180 days of later history without a blame. Each is matched to a
  defective item by module, size and date, and screened like P.
- **Items that cannot be confirmed are dropped,** not guessed.

**Splits:**
- by commit date, not at random;
- the earliest 30 % of each set calibrates the seats (ADR 0001), and the rest is the test split,
  scored once;
- the two items of a base, and all files of one commit, stay in one split;
- fits are per set.

## 3. Arms

Every arm gets the same build line ("compiles: yes/no"), or none does; that is decided in the
pilot. Each competitor's free parameter is tuned on the calibration split, the same way W's
threshold is.

| Arm | What it is |
|---|---|
| A0 Size | Number of added lines alone, the baseline the history labels followed |
| A1 Claude alone | One Claude Opus agent, one file's diff, the current question; threshold set by a p readout |
| A2 Claude ×5 | The same prompt sampled five times; the vote cut-off is tuned. Dropped if the pilot shows repeated calls barely differ. |
| A3 Claude, strict bar | One Claude told to reject only for a defect this change introduces |
| A4 Claude AND second family | REJECT only if both reject. The second family is the same model W uses, with its threshold tuned. |
| A5 Claude with all the evidence | One Claude agent given everything W's seats get: whole commit, search over the snapshot, build and test results |
| W Evidence panel | Build, tests, whole-commit reader, code-base checker, second family; log-odds mode; every seat answers, and the SPRT is replayed |
| W−k | W without seat k, for each seat, replayed from the stored answers |

## 4. Leakage guards

All of these are checked in the pilot and again before scoring.

- **Snapshots:**
  - Tool seats and A5 work on a `git archive` snapshot of the item's own version: the base tree
    with the item's change applied. There is no `.git` and no later history.
  - A planted item's snapshot contains the planted line, never the original.
- **Sandbox:** the code-base checker and A5 run in a sandbox whose only readable path is the
  snapshot. Every tool call's path is logged, and any path outside the snapshot fails the run.
- **Canary:** a file with a known token placed outside the snapshot. The checker is asked to find
  it, and must fail.
- **Leak probe:** no tool output may contain a planted item's original token. One deliberately
  leaky arm must trip the probe.
- **Model calls:** they log their command line. Seats without tools keep `--tools ""`, and seats
  with tools get an allow-list of read and search tools only.
  - The pilot checks that no call loads user-level instructions or memory.
- **Labels:** no label text, label-correlated ids or later commit messages reach any input.
  - The answer keys and `.warf-experiments/` are outside every sandbox.
- **Memorisation:** results are also reported for commits after each model's training cutoff. A
  probe asks for the original next line of a few items.
- **Score controls:**
  - an arm given the label must score about 1.0;
  - a scorer run on shuffled labels must score about 0.5.

## 5. Metrics, tests and outcomes

- **Scored verdict:** W's verdict is its threshold on Λ, set on the calibration split. τ and the
  SPRT are reported beside it. Ties at the threshold are broken at random with a fixed seed.
- **Each comparison of W with an arm c:**
  - W's threshold is set, on the calibration split, to c's false-alarm rate there.
  - The primary metric is the difference in recall on the test split.
  - Beside it, the difference in false-alarm rate on the test split is reported. It must be within
    +0.05: W may not buy recall with alarms.
- **Bootstrap:**
  - Set P: a paired bootstrap over bases, where a base drawn twice counts twice.
  - Set R: a bootstrap stratified by class and paired across arms by item.
  - The bootstrap decides; exact McNemar is reported beside it.
- **Outcome of each comparison:**
  - better: the lower 95 % bound of the recall gain is above 0;
  - not better: the upper bound is below the margin m = +0.03;
  - otherwise unresolved.
- **The ADR's outcome is decided by Q1 (W against A5) on set P:**
  - **Pass:** W is better than A5 and also better than every arm A0–A4. This is an
    intersection-union test: the error rate stays at 0.05 and no correction is needed, but power
    multiplies.
  - **Fail:** W is not better than A5. The panel is then unnecessary, whatever else holds.
  - **Inconclusive:** anything else.
- **Set R** is a direction check. It is reported with its intervals, and it is not powered for
  +0.03.
- **Seats (Q3):** W−k against W. Holm correction across seats and sets.

**Power:** frozen after the pilot. The pilot measures:
- discordance between W-like arms and A1;
- A1's recall on the plant mix.

The size of P is then chosen by simulation of the **whole rule above**: recall, at matched alarms,
against every arm. It is sized for at least 80 % power for Q1 at +0.03, and the joint power is
stated.

For scale: recall is counted on defective items only. So 300 test bases give about 0.46 power at
6.5 % discordance. Q1 alone may need about 600 test bases, or about 1,300 candidate bases after the
last run's attrition (15 % defective originals, 22 % unusable plants).

## 6. Stages, each with a stop rule

0. **Pilot** (about 20 bases and 20 R candidates). It measures:
   - build time per commit and era, and which eras build;
   - unit-test line coverage of the plant sites (one gcov build). The tests seat is dropped below
     20 %;
   - whether repeated CLI calls differ (20 items × 5);
   - tool-agent call time;
   - A1's recall on the plant mix;
   - person-minutes per plant mark and per fix confirmation;
   - every guard in §4.

   Stop and report if the guards cannot be met, or if A1's recall stays above 0.85.
1. **Answer keys.** Build P and R to the sizes frozen after the pilot. Stop if P falls short, and
   do not shrink the rule.
2. **WaRF changes** (ADR 0002). Each needs a test that fails before the change.
3. **Calibration.** Fit every seat on the calibration split, and print the labelled count per class
   for each seat.
4. **One scored run of all arms,** every seat answering every item.
5. **Write-up.** Every arm, both sets, ablations, controls, costs, and the outcome under §5.

## 7. Cost (to be replaced by pilot measurements)

- **Items:** P test and calibration plus R, likely 1,500–2,500 reviews per arm.
- **Model calls per item:**

  | Arm | Calls |
  |---|---|
  | A1, A3 | 1 each |
  | A2 | 5 |
  | A5 | 1 agent run with tools |
  | W | about 3 model seats |

  At 15 s per call without tools, and unknown for tool runs, the total is tens of thousands of Opus
  calls over days, not hours.
- **Builds:**
  - **Per distinct commit:** one configure plus a library-mode or instantiation build.
  - **Per-item compile:** about 10 s (`src` files) to about 4 minutes (wide headers), measured from
    `gs_unref/build/.ninja_log`.
  - **Tests:** the including tests' compile, twice per item.
- **People:** about 2,400 judgements (plant marks, screens, fix confirmations) at an unmeasured 2
  minutes each, about 80 hours. This is the real bottleneck. A smaller P is the main lever.
- **Second family:** Jev costs cents. A paid family through OpenRouter needs the user's approval.

## 8. Open choices for the user

- **The second-family model:** Jev only, or a paid family such as GPT or Gemini.
- **Who marks plants and confirms fixes:** the user, a colleague, or a model family used in no arm
  with spot checks by a person.
- **Whether to accept a smaller, pilot-only first round** that can only end "inconclusive", to learn
  the costs before committing to the full test.
