# ADR 0003: Question seats, and weights learned per seat

- Status: **proposed; a small gain, shown only when the two fresh projects are pooled** (2026-11-17). On
  RocksDB (development, cross-validated within it) the three question-panel seats beat five persona seats,
  73.6% vs 70.2% (p 0.002). On two fresh, preregistered sets with each project's own context and checks,
  neither alone shows it: DuckDB 76.5% vs 75.0% (30 vs 18 changes, p 0.11), PPSSPP 70.8% vs 69.0% (47 vs
  33, p 0.15). Pooled, as preregistered before PPSSPP was mined: 77 vs 51, p 0.027. See "Fresh tests" below.
- Date: 2026-11-14
- Builds on: [ADR 0001](0001-pool-calibrated-log-odds.md) (log-odds pooling),
  [ADR 0002](0002-seats-differ-in-evidence.md) (seats that differ in evidence)
- Spec: [`docs/spec/learned-aggregation.md`](../spec/learned-aggregation.md)

## Context

- **On RocksDB changes matched on size** (`.warf-experiments/rdb-set/`, 400 defective and 400 clean
  changes with the same number of added lines), WaRF with five Jev persona seats in `logodds` mode (LO) is
  right on 69.0% (balanced accuracy).
- **Persona seats are near-copies** (ADR 0002): five personas on one model are about one reviewer.
  Changing what a seat is shown (declarations of the changed names, the whole commit, single hunks) did
  not change Jev's ranking (`.warf-experiments/pooled-dev/README.md`).
- **Changing what a seat is asked did:**
  - **"Which added line breaks a supported build / introduces a runtime defect, or NONE"**, with the
    added lines numbered as options. One call ranks the changes at AUC 0.777, against 0.770 for WaRF's
    question on the same input and context.
  - **Seven YES/NO checks** written from the 37 RocksDB defects outside the test set (integer types,
    format specifiers, warnings that -Werror makes fatal, assert side effects, lifetime, locking, edge
    cases): AUC 0.59–0.75 each.
- **WaRF could not ask either.** A decision seat is asked APPROVE/REJECT with its persona as instructions.
  A YES/NO question in that frame is a different question, and options cannot depend on the input.
- **Pooling is fixed by construction:** seats of one model are averaged and models summed. An offline
  logistic stacker over all stored Jev views reached 73.7%. The question was whether learned weights are
  where that gain came from.

## Decision (proposed)

1. **Question seats.** `AgentProfile.question` = `check` (the persona as YES/NO) or `locate` (which added
   line, or NONE; the input's added lines tagged `[Lk]`, asked in windows of 60). The decision provider
   asks the typed question and renders the answer as a verdict readout with p(REJECT) = p(YES) or
   1 − min over windows of p(NONE). The minimum, not a product over windows: a product made clean
   changes look worse the longer they were (spec §2). Everything downstream (calibration, pooling,
   logging) is unchanged. A question seat is its own reviewer and its own pooling group,
   `provider/model@question`.
2. **`--aggregate learned`.** Λ = bias + Σ_s w_s · r_s over the panel's seats. The weights come from an
   L2-regularised logistic regression (w ~ N(0, 1), flat intercept) on the labelled session log, and the
   training base rate is removed from the bias. Every seat is asked. Below 20 labelled sessions per class,
   the review runs as `logodds`.
3. **Several questions in one seat** (added the same day, when panels were limited to five seats). A
   question seat's persona may hold several questions, one per line. They are asked in one call and pooled
   as "any of them finds a problem": `1 − Π(1 − p(YES))` for checks, and the product of p(NONE) over the
   questions within a locate window.

## Evidence

**Through WaRF's own `run_review`, on stored Jev answers.**
- 10-fold × 5 within RocksDB, 800 changes.
- Training folds are written as labelled session logs.
- Script: `.warf-experiments/pooled-dev/warf-panel/replay_learned.py`.

| Panel | `--aggregate logodds` | `--aggregate learned` |
|---|---|---|
| 5 persona seats with the project context | 70.2% | 69.6% |
| + 2 locate seats + 7 check seats (14 seats) | **72.5%** | **73.6%** |

Paired, exact McNemar on the decisions of one repetition (`paired.py`):

| Comparison | Right only in the first | Right only in the second | p |
|---|---|---|---|
| 14 seats `logodds` vs 5 persona seats `logodds` | 35 | 18 | 0.027 |
| 14 seats `learned` vs 14 seats `logodds` | 47 | 39 | 0.45 |
| 14 seats `learned` vs 5 persona seats `logodds` | 73 | 48 | 0.029 |

- **The shown gain is the question seats:** +2.3 points under the same pooling.
- **Learned weights add +1.1 on the 14 seats, but that is not shown** (p 0.45). They lose 0.6 on the five
  persona seats alone.
- **The offline stacker's 73.7%** is the same seats and labels, with one threshold for all domains.
- **An earlier version multiplied the locate windows' p(NONE):** 72.9% `logodds`, 73.1% `learned`. It was
  replaced because the product grows p(REJECT) with the size of the diff (spec §2), not for accuracy.
- **The eleven narrower build diagnostics** (sign-compare, -Wshadow, NDEBUG-only use, override, …) added
  nothing over the 14 seats (71.0–73.0% offline) and are not part of the panel.
- **Live** (`smoke_live.py`, real Jev, 10 changes, about $0.02):
  - every question seat answers end to end through the provider;
  - the locate readout names concrete lines (`[L59] MemTable* x __attribute__((unused)) = m->Unref();`);
  - live p(REJECT) differs from the stored stand-ins by 0.01–0.04 on average per seat, and by up to
    0.07 for the check seats, whose stand-ins were asked without the project context.
- **Tests:** `tools/test_learned.py` (68 checks). `mutants.py` breaks the change 27 ways and the test catches
  all 27, each by its own check. The first version missed five of the breaks a cold review then made; the
  checks were added.

### At most five seats (decision 3)

Every number here comes from answers WaRF itself recorded:
- **Persona seats:** `history/sessions_LO_ctx.jsonl`.
- **The question seats, live on all 800 changes:** `five-seats/run_live.py`, about $0.99, every seat with the
  project context.
- **Method:** replayed through `run_review`, 10-fold × 5 within RocksDB, `--aggregate logodds`
  (`five-seats/replay_live.py`).

| Panel | Seats (calls) | Accuracy | Against LO with context, paired |
|---|---|---|---|
| LO with context (5 persona seats) | 5 | 70.2% | |
| **BOUNDARY + LOCATE + CHECKLIST** | **3** | **73.6%** | 49 vs 22 changes, p 0.002 |
| SKEPTIC + BOUNDARY + DEFAULT + LOCATE + CHECKLIST | 5 | 73.5% | 42 vs 17, p 0.002 |
| the same, both question seats on jev-1.13 | 5 | 72.1% | 38 vs 24, p 0.098 |

- **What the two question seats ask:**
  - LOCATE (jev-1.14) asks the build and runtime questions in one call.
  - CHECKLIST (jev-1.14) asks the seven project checks in one call.
  - BOUNDARY is the persona seat on jev-1.13.
- **Live AUC:** CHECKLIST 0.794, LOCATE 0.789. The checklist's stand-in, asked without the project
  context, had 0.782.
- **Three seats reach what fourteen did** (72.5% `logodds`, 73.6% `learned`). Two more persona seats add
  nothing.
- **Things that did not help** (offline, stand-ins, `five-seats/`):
  - splitting the question seats in two: 72.0–72.4% against 72.8% for the same three seats;
  - eleven narrower diagnostics in the checklist: AUC 0.782 → 0.759;
  - a whole-commit seat: 71.4%.
- **A fourth seat shown retrieved declarations** adds about half a point offline: 73.4–73.5% against 72.8%.
  It would need retrieval in WaRF and seat inputs on the CLI.
- **`learned` is worse than `logodds` on small panels:** 71.3% vs 72.8% with three seats, 72.2% vs 73.2%
  with five (stand-ins).
- **Selection:** the three seats were chosen by a rule fixed before panel scores were looked at: the best
  single seat of each kind by its own AUC. The search over about 1,500 panels found nothing clearly better
  (73.0–73.3%).

### Fresh tests (DuckDB and PPSSPP, preregistered in `.warf-experiments/ddb-set/README.md` and `pp-set/README.md`)

- **The sets:** per project, 400 defects confirmed by two Claude judges, with 400 clean controls matched on
  added lines. The 40 defects before them in list order wrote the project's defect profile and checks, each
  written by a fresh agent that saw only its input. (Apache Arrow was tried as the third project and dropped
  before any judging: too few of its fixes touch C++; `arw-set/README.md`.)
- **The arms:** the panel structure fixed beforehand, run through WaRF with a project context written from
  the project's own build files. Calibration came from the other nine folds.

| Panel (`logodds`) | DuckDB | PPSSPP | Paired against LO-ctx (DuckDB; PPSSPP) |
|---|---|---|---|
| LO-ctx (5 persona seats) | 75.0% | 69.0% | |
| BOUNDARY + LOCATE + CHECKLIST | 76.5% | 70.8% | 30 vs 18, p 0.11; 47 vs 33, p 0.15 (each not shown) |
| SKEPTIC + BOUNDARY + DEFAULT + LOCATE + CHECKLIST | 76.2% | 70.8% | 26 vs 16, p 0.16; 39 vs 25, p 0.10 |

- **Pooled (the secondary fixed before PPSSPP was mined):** 77 vs 51 changes, exact McNemar p 0.027.
- **Matched pairs only:** on the pairs matched within their own added-line bin, DuckDB 74.7% vs 74.3%
  (14 vs 12), PPSSPP 70.5% vs 68.9% (35 vs 25, p 0.25).
- **Seat AUCs:** every seat ranks at 0.82–0.85 on DuckDB and 0.72–0.78 on PPSSPP (the added-line count
  0.61 and 0.55). The persona seats are as good as the question seats (DuckDB SKEPTIC 0.851, CHECKLIST
  0.830; PPSSPP TEST-FOCUSED 0.778, CHECKLIST 0.769). The question seats' lead on RocksDB did not carry
  over seat by seat; the panel's gain comes from combining them.

## Consequences

- **The question seats' gain is small and shown only pooled.** On each fresh project the three-seat panel
  was 1.5 to 1.8 points ahead of five persona seats, with fewer calls, but not shown on either alone;
  pooled over both it is (p 0.027). What follows describes the RocksDB development result.
- **Question seats are a way to add a project's knowledge to a Jev panel;** on RocksDB they were the gain.
  - The recommended panel is three seats in `logodds` mode: one persona seat, one locate seat
    (build + runtime) and one checklist seat (the project's checks, written from its own defect history).
    The RocksDB panel is `.warf-experiments/pooled-dev/five-seats/panel3_rocksdb.json`.
  - On RocksDB this is 73.6% against 69.0% for LO as first tested, and 70.2% for LO given the same
    project context (p 0.002).
- **`learned` is available, not the default, and not claimed to help.**
  - 73.6% on the 14 seats, against 72.5% in `logodds` mode; p 0.45.
  - It fits panels whose seats are not exchangeable within a model, which equal group weights assume.
    A fresh set has to show whether that buys anything.
- **A fresh set decides.** All numbers above are development on the set they were found on. The checks'
  wording was written from RocksDB defects outside the test set, but the choice of seats was made on it.

## Alternatives considered

- **More persona seats, or personas carrying the checks as instructions:** these keep WaRF's verdict
  criteria, so the seat answers "is this mergeable", not the check.
- **Weights per group instead of per seat:** one weight for the seven checks averaged. This is the
  `logodds` rule with one free scale per group. It was not measured separately.
- **File-type priors (test / header / source):** +0.4–0.8 offline. Rejected, because they learn the set's
  composition, the same kind of artefact as the size seat.
- **Retrieved declarations as extra input:** no change in ranking (verdict AUC 0.739 → 0.733).
