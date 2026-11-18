# Spec: question seats and learned aggregation (`--aggregate learned`)

Decision record: [`docs/adr/0003-question-seats-and-learned-weights.md`](../adr/0003-question-seats-and-learned-weights.md).
Builds on [`logodds-aggregation.md`](logodds-aggregation.md); notation as there (positive evidence favours
APPROVE, `y = +1` clean, `p` a decision seat's p(REJECT)). Status: implemented 2026-11-14; ADR 0003 is
proposed.

## 1. Scope

- **Question seats** (§2) apply in every aggregation mode.
- **Learned aggregation** (§3–§6) applies to `run_review(..., aggregate="learned")` and to `warf review` and
  `warf review-commit` with `--aggregate learned`. The MCP server keeps `vote` mode.
- **Unchanged:** `vote` and `logodds` behave as before for panels without question seats, and the weight
  update (`apply_oracle`, ω).

## 2. Question seats

- **What:** a seat whose profile sets `question` is asked something other than WaRF's verdict. Values
  (`warf.questions.QUESTIONS`):

  | `question` | What Jev is asked | Options | `p` (p(REJECT)) |
  |---|---|---|---|
  | unset | the persona, as now | APPROVE / REJECT | p(REJECT) |
  | `check` | each question of the persona, as YES/NO about the changed lines | YES / NO | `1 − Π_q (1 − p_q(YES))` |
  | `locate` | each question of the persona, as "which added line has this problem?" | `L1` ... `Ln`, NONE | `1 − min_w Π_q p_qw(NONE)` |

- **Several questions in one seat:** a question seat's questions are the non-empty lines of its persona,
  stripped (`warf.questions.persona_questions`); one line is one question, exactly as before. All of a
  seat's questions are asked in one call (ids `q1`, `q2`, …; a single question keeps the id `verdict`).
  They are pooled as "any question finds a problem": for `check` the chance that at least one answers YES,
  for `locate` a window's p(NONE) is the product over the questions. A seat is still one reviewer (one
  persona fingerprint), calibrated and grouped as one.
  - **Why:** the panel is limited to a few seats. On the RocksDB answers, one call asking the seven project
    checks ranks the changes at AUC 0.782 (after the two-decimal readout), and one call asking the build and
    the runtime locate questions at 0.785, against 0.766 and 0.756 for the best single question of each.
    The plain mean of the checks' p(YES) ranks as well before rounding (0.783) but loses to the readout's
    two decimals (0.780), because its values are small.

- **Locate input:** every added line of the diff is tagged `+[Lk] ` in the seat's input, in order. An added
  line is a `+` line inside a hunk, within the line counts of its `@@ -a,b +c,d @@` header: a file header
  `+++ b/...` is never one, an added line whose own text starts with `++` is, and an input without hunks
  has none. The function context WaRF appends after its separator is not tagged. An option repeats the
  first 50 characters of its line; NONE reads "None of these added lines has this problem."
- **Windows:** at most 60 line options per request (`LOCATE_WINDOW`). A longer diff is asked in windows of
  60 on the same state, each with its own NONE; `p = 1 − min_w p_w(NONE)` (the most suspicious window),
  tokens are summed, and the readout names the most probable line over all windows.
  - **Why the minimum, not `1 − Π_w p_w(NONE)`:** the windows share one state and are not independent, and a
    product grows p with the size of the diff. On the RocksDB answers (`.warf-experiments/pooled-dev/locate/`)
    the clean changes' mean p(REJECT) for the build question was 0.47 / 0.73 / 0.84 with one / two / three or
    more windows under the product, and 0.47 / 0.59 / 0.55 under the minimum, with the same ranking over all
    800 changes (AUC 0.766 minimum, 0.757 product).
- **Readout:** the provider renders every answer in the verdict's shape, so §7 of the log-odds spec reads
  it unchanged: `REJECT|APPROVE` (REJECT when `p > 0.5`), then
  `p(APPROVE)=…  p(REJECT)=…  answer=YES|yes=k/n|line=Lk  [model: decision model, no reasoning]`
  (`answer` for one check question, `yes=k/n` for several: how many have p(YES) > 0.5), and for `locate` a
  last line `[Lk] <line>` with the likeliest line over all questions and windows.
- **Refusals (`ValueError`, before anything is asked):** an unknown question; a question seat on a text
  provider (only `jev` and `laya` can answer a typed question); a question seat in a debate round.
- **Abstention:** a `locate` seat whose input has no added lines (a file review, or a pure deletion) is
  not asked and casts no vote. In `logodds` mode it counts as answered for the early-stop test. A review in
  which no seat voted raises `RuntimeError` naming the seats that abstained.
- **A reviewer:** the question is part of a reviewer's identity, with the agent name, persona, model and
  evidence source: calibration (log-odds §5) counts a vote only for a seat asked the same question.
- **Groups (`logodds` mode):** a question seat forms its own group, `provider/model@question` (after a
  `#source` tag if any). Seats of one model asked the verdict on the same input still count once.
- **Log:** a question seat's vote carries `"question"`; verdict seats keep their shape.

## 3. Learned weights

- **Data:** the labelled sessions of the session log (or `log_path`), read as in log-odds §5: oracle type
  `DEVELOPER`, `y = x_star`, top-level votes only, domains pooled.
- **Features:** one per seat of the panel under review, matched by reviewer identity (§2). In a session,
  a seat's feature is `r = ln((1 − p) / p)` for a usable `p` that agrees with the vote (clamped to
  [0.01, 0.99]), its vote `±1` otherwise (a text seat), and `0` when the seat did not vote (no evidence).
- **Rows:** a session counts when at least one seat of the panel voted in it.
- **Enough labels:** at least 20 rows of each class (`MIN_PER_CLASS_LEARNED`); otherwise no fit (§5).
- **Fit:** MAP logistic regression of `y = clean` on `[1, r_1, …, r_k]`. Every seat weight `w_s ~ N(0, 1)`
  (`LEARNED_PRIOR_SD`); the intercept `b` has a flat prior. Newton's method with step halving, at most
  50 iterations; no convergence means no fit.
  - The flat intercept matters: a shrunk intercept carries only part of the training base rate, and the
    verdict of a panel trained on an imbalanced history would lean (measured: bias −0.40 instead of −0.14
    on an 80 %-clean synthetic history with one informative seat).
- **Bias:** `bias = b − logit(π)`, `π = (n_clean + 1) / (n + 2)` over the rows, so that Λ is evidence at
  prior odds 1:1, as τ expects (log-odds §4).
- **Correlated seats:** there is no group-mean rule. Seats that say the same thing share their weight
  through the prior; a seat that adds nothing gets a weight near 0.

## 4. Pooling and decision

- **Every seat is asked:** the weights hold for the panel's full answer, so there is no early stop, with
  or without `--no-early-stop`. A seat that abstains (§2), or a text seat whose call times out, adds 0. A
  decision provider's error, a read timeout included, fails the review, as in every mode.
- **Evidence:** `e_s = w_s · r_s` per vote, tag `learned`; the SAST vote (SECURITY with `--sast`) adds its
  fixed `SAST_OMEGA · LLR(vote)`, tag `fixed`.
- **Λ = bias + Σ e_s**, logged as `sprt_lambda`.
- **Decision:** APPROVE if Λ ≥ τ_d (log-odds §4), else REJECT.
- **Confidence:** HIGH when Λ ≥ A (+2.890) or Λ ≤ B (−2.251); LOW when `|Λ − τ| < ln 2`; MEDIUM otherwise.
  There is no disagreement rule: the weights already encode how far seats agree.
- **`normalised_score`:** `2 · σ(Λ − τ) − 1`, as in log-odds mode.

## 5. Too few labels

Without a fit (§3), the review runs exactly as `--aggregate logodds` and its result and record say
`"aggregate": "logodds"`. With `verbose`, WaRF prints why, from `Calibrator.learned_status`: too few
labelled sessions (with the counts), or a fit that did not converge.

## 6. Logging

A `learned` session record has the log-odds fields (`aggregate`, `tau`, and per vote `p_reject`,
`evidence`, `calibration`) and `"learned": {"bias", "n_clean", "n_defective"}`, the fit behind the verdict.
`sprt_fired` keeps its meaning (`confidence == "HIGH"`, a boundary crossed); in a learned session every
seat was asked regardless, as with `--no-early-stop` (`warf/policy.md`).

## 7. Configuring a panel

Question seats are profile entries (`warf/profiles/<name>.json`, or a path). The recommended panel (ADR
0003) is three seats in `logodds` mode: one persona seat, one locate seat with a build and a runtime
question, and one checklist seat with the project's checks. For example (questions shortened):

```json
[
  {"name": "LOCATE", "provider": "jev", "model": "jev-1.14", "question": "locate",
   "persona": "Which added line makes this change fail to build on a supported configuration: a compiler error, or a warning that -Werror turns into an error? Choose NONE if every added line builds everywhere.\nWhich added line introduces a runtime defect: a wrong result, a crash, a leak, a read of an uninitialised or freed value, a data race or deadlock, or a test that can hang or fail intermittently? Choose NONE if no added line does.",
   "weights": {"LOGIC": {"alpha": 1, "beta": 1}, "SECURITY": {"alpha": 1, "beta": 1}, "PERFORMANCE": {"alpha": 1, "beta": 1}},
   "last_updated": null},
  {"name": "CHECKLIST", "provider": "jev", "model": "jev-1.14", "question": "check",
   "persona": "Do the changed lines put a size_t, uint64_t or other wide or unsigned integer into a narrower or signed type, or compare signed with unsigned values?\nDo the changed lines read or write shared state without holding the mutex that guards it?",
   "weights": {"LOGIC": {"alpha": 1, "beta": 1}, "SECURITY": {"alpha": 1, "beta": 1}, "PERFORMANCE": {"alpha": 1, "beta": 1}},
   "last_updated": null}
]
```

The persona seat is any entry without `question` (RocksDB: BOUNDARY on jev-1.13). The full RocksDB panel is
`.warf-experiments/pooled-dev/five-seats/panel3_rocksdb.json`. A seat without `persona_hash` is stamped when
the profile is first loaded.

A check's question is a project's own; good ones come from the defects of the project's history
(`.warf-experiments/pooled-dev/history/`). The project context (`warf_context.md`) is shown to every seat.

## 8. Properties the tests check (`tools/test_learned.py`)

1. **Marking:** the added lines in order, tagged `[Lk]`; headers, removed and context lines unchanged; the
   function context after the separator untouched, also when a trimmed hunk runs into it; no added lines
   outside a hunk; the hunk's line counts decide (an added `++c;` is a line, a second file's `+++` header
   in a plain `diff -u` is not).
2. **`check`:** one YES/NO choice question with the persona as instructions; YES 0.8 is REJECT at
   p 0.80, NO 0.7 is APPROVE at p 0.30.
3. **`locate`:** options L1…Ln then NONE, naming their line; p(NONE) 0.3 is REJECT at 0.70 and the
   readout names the line; 70 lines are asked in two windows on one state, `p = 1 − min(0.8, 0.6) = 0.40`
   (a product would give 0.52); the readout names the likeliest line over both windows, numbered across
   them (L65); tokens summed; an answer without p(NONE) is refused.
   **Several questions:** a persona's questions are its non-empty lines, stripped; three check lines are
   three YES/NO questions in one call with `p = 1 − 0.8 · 0.5 · 0.9 = 0.64`; two locate lines are asked
   together in each window, a window's p(NONE) is their product (0.40 and 0.81), `p = 1 − min = 0.60`,
   and the readout names the likeliest line over questions and windows.
4. **Profiles and refusals:** `question` survives save/load and is omitted when unset; a question seat on
   a text model (with every model stubbed, so a failed refusal reaches no real model), an unknown question
   and a question seat in a debate are refused.
5. **`run_review` with question seats:** only the locate seat sees the tagged diff; two verdict seats of one
   model are one group, a check and a locate seat are groups of their own; the log records questions of
   question seats only; a locate seat abstains, unasked, on an input without added lines; a panel whose
   every seat abstains raises an error that says so.
6. **Calibration** keeps questions apart.
7. **The fit**, with bounds derived, not chosen:
   - the intercept is exactly ln 4 on 8-clean-of-10 rows without signal (flat prior);
   - a perfectly separating seat gets exactly the root of `w = 10 (1 − σ(w))` (its N(0, 1) prior);
   - a seat's feature: `ln((1 − p)/p)` for an agreeing p, the vote for a contradicting p or none;
   - another panel's sessions are not used;
   - the informative seat's weight is beyond three standard errors (from the fit's curvature), the
     uninformative seat's within three of 0;
   - on an 80 %-clean history with uninformative seats the intercept is ln 4 and the bias 0, within two
     standard errors of the intercept (`1 / sqrt(200 · 0.8 · 0.2)`);
   - an absent seat adds 0, and a seat that voted only on defective changes stays within three standard
     errors of weight 0;
   - 19 labels of a class give no fit, and `learned_status` says why.
8. **Decision** in LOGIC and SECURITY: HIGH beyond A or B, LOW within ln 2 of τ, MEDIUM otherwise.
9. **`run_review`, learned:**
   - every seat is asked;
   - Λ = bias + Σ w·r exactly, summed over seats, with two seats on one model;
   - the record carries the mode, the evidence per vote and the fit;
   - the SAST vote's fixed evidence is in Λ;
   - too few labels run as logodds, and a fit that does not converge falls back and is reported as such;
   - debate is refused for a verdict-only panel (the mode's own refusal);
   - the CLI accepts `--aggregate learned` and exits 2 with `--debate`.

`.warf-experiments/pooled-dev/warf-panel/mutants.py` breaks the change 27 ways, one at a time, in a copy of
the package. An unmutated copy passes first. The test catches 27 of 27, each by the check written for it.

The breaks cover:
- the group key and the calibration key;
- the bias, a penalised intercept, unpenalised weights;
- an early stop;
- p(NONE) read as p(REJECT), only the first window asked, windows multiplied, the best line numbered within
  its window;
- p(NO) read as p(YES);
- marking the context, ignoring hunk counts;
- no abstention, question seats on text models;
- absence counted as a vote, a p that contradicts its vote used;
- no fallback, the fallback reason not reported;
- the log without the question;
- learned allowed with debate;
- the SAST vote left out;
- Λ pooled by group means;
- several questions: only the first asked, checks pooled by their maximum, locate questions pooled by their
  minimum, question lines not stripped.

## 9. Known limitations

- **Sessions with an early stop** (vote or logodds mode) lack the seats that were not asked; their
  features are 0, which is "no evidence", not "the seat would have approved". Train a learned panel on
  sessions where every seat answered (`--no-early-stop`, or `learned` sessions).
- **A panel change resets weights:** a seat with another persona, model, evidence source or question is
  another reviewer and starts at weight 0 until it has labelled sessions; the panel falls back to logodds
  only when fewer than 20 sessions per class contain any of its seats.
- **ω follows the persona, not the question:** `reconcile_profiles` watches the persona text, so a seat whose
  `question` is changed in place keeps the ω it earned answering the old question (it matters for `vote`
  mode and for uncalibrated `capped` / `omega` evidence). Give a seat with a new question a new name or
  persona.
- **Laya reads only the start of the state** (512 or 1,024 tokens, README), so `[Lk]` options can name
  lines it never saw. Use `locate` seats on Jev.
- **An older WaRF ignores `question`** in a profile written by this one and asks such a seat the verdict
  with its YES/NO persona.
- **Domains are pooled**, as in log-odds §5.
- **Development numbers** (ADR 0003) come from one project's labels, cross-validated within it.
