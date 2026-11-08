# A small answer key for the evidence-seat test

2026-11-04. This is a first, small set of G+Smo changes with a known right answer. It is built for
[`docs/spec/evidence-seats-test-plan.md`](../../docs/spec/evidence-seats-test-plan.md) and is meant
to try reviewers and seats on before the full test. No reviewer has seen it yet.

## What is in it (`items.jsonl`)

- **50 recent G+Smo changes, each in two versions:**
  - the change as committed: **clean**, right answer APPROVE;
  - the same change with one planted defect: **planted**, right answer REJECT.

  That makes 100 items.
- **Where the changes come from:**
  - non-merge commits on gismo's `origin/dev`, in the gismo6 clone;
  - dated 2024-01-15 to 2026-09-10;
  - one C++ file under `src/` per commit, one commit per base;
  - 4 of the commits are after Claude Opus 5.5's training cutoff.
- **The input:** each item's `code` is exactly what WaRF's review path shows a reviewer: the
  file's diff with 30 lines of context, followed by the enclosing function bodies
  (`../laya-five/run_five.py` `prepare`).
- **The plants are harder than the one-token flips of `../planted/`,** which one Claude caught 52
  of 54 times:

  | Kind | Bases | Example |
  |---|---|---|
  | Dropped statement | 16 | an added `m_deg = deg;` or `gethostname(...)` left out; the hunk header is corrected |
  | Removed `- 1` | 8 | `uu*(uu-1)` → `uu*(uu)` |
  | `.rows()` ↔ `.cols()` | 7 | `coefsSize()` returns `m_coefs.cols()` |
  | Loop start 0 ↔ 1 | 7 | `for (size_t q=1; ...)` skips patch 0 |
  | Argument swap | 6 | `acc_global(m_value, thValue)` |
  | Loop bound `<` ↔ `<=` | 5 | |
  | Index swap `(i,j)` → `(j,i)` | 1 | |

  A plant always replaces the same text in the appended function bodies too, so the diff and the
  bodies never disagree.

## How the plants were checked (`judgements.jsonl`, `select.log`)

- **The check:** two independent judges (Claude agents) looked at each of 120 candidates. They read
  the code at the commit with read-only git and decided:
  - does the planted version compile;
  - is it a real defect in code that runs;
  - is it visible from what the reviewer is shown.
- **Rule for keeping a plant:** both judges say it compiles and is a real defect.

| Candidates | Count |
|---|---|
| Both judges keep | 74 |
| The judges disagree | 11 (listed in `disagreements.tsv`) |
| Both reject | 35 (would not compile, harmless, or dead code) |

- **The set** is the first 50 of the 74 kept, in the builder's seeded order, with dropped
  statements held to a third. The other 24 are spares.
- **Visibility:** both judges call 48 of the 50 plants visible from the diff; 2 need another file.

## Known limits

- **The judges are Claude**, the same family as the reviewer under test. They judged with the
  original next to the plant, which is a different task from reviewing blind. Still, a person should
  spot-check a sample of the planted items, and the 11 disagreements.
- **The clean versions have not been screened** for defects that were already in the committed
  code. In `../planted/`, 8 of 54 had one. The test plan asks for a person, or a model family used in
  no arm, to do this screen.
- **Nearly all plants are visible from the one-file diff.** Cross-file plants, which the test plan
  asks for, are not in this set.
- **Nothing was compiled.** "Compiles" is the judges' reading of the declarations, not a build.
- **50 bases is a pilot size.** It can show large effects and measure costs, not settle +0.03.

## First run: one Claude against five Claudes (`score_set.py`, `score.log`)

2026-11-04.
- **Arms** (`../planted/run_planted.py --set .warf-experiments/evidence-set`):
  - one Claude Opus 5.5 agent with the sweep's question;
  - WaRF's default five personas on Opus, with WaRF's default review.
- **Calls:** 100 and 436.
- **Interruption:** ten five-Claude reviews failed when the usage limit hit. They were re-asked in
  full later, and no partial review was kept.

| | Balanced accuracy | Planted caught | Clean passed |
|---|---|---|---|
| One Claude | 0.740 [0.670, 0.810] | 49/50 | 25/50 |
| Five Claudes | 0.800 [0.730, 0.860] | 49/50 | 31/50 |

- **As labelled:** five minus one is +0.060 [+0.020, +0.110]. Only five Claudes were right on 6
  items, only one Claude on 0 (McNemar p 0.031).
- **Where the difference comes from:** both arms caught the same 49 plants and missed the same one
  (a dropped statement in `gsTensorDomainIterator.h`). The whole difference is in clean items.

**The clean labels are wrong for many items.** One Claude's 25 rejections of clean versions were
checked against the code and later history (`verify/`, Claude judges, not blind to the arm):

| Class | Items |
|---|---|
| Real defect in the committed code | 16, of which 12 were fixed later on `origin/dev` |
| Debatable | 4 |
| False alarm | 5 |

| Re-scored (`verify/critic/rescore.log`) | One | Five | Five minus one | Only five / only one | McNemar p |
|---|---|---|---|---|---|
| Labels as given | 0.740 | 0.800 | +0.060 | 6 / 0 | 0.031 |
| 16 real defects counted as right to reject | 0.860 | 0.926 | +0.066 [+0.008, +0.129] | 5 / 1 | 0.22 |
| Real and debatable counted as right to reject | | | +0.052 [−0.007, +0.122] | 4 / 2 | 0.69 |

- **What the panel overturned:** 6 of one Claude's REJECTs. 4 were false alarms, 1 was a slip with
  no effect, and 1 was a real but latent defect (`gsMatrix<>` in a `T` template, fixed 15 months
  later).
- **What it kept:** 15 of the 16 real defects.
- **So here its extra leniency mostly removed false alarms.** On the 100 real commits of
  `../four-arms/` it lost defects instead. The panel is a more lenient filter on the same
  judgements, and whether that helps depends on how blatant the defects are.
- **Five Claudes are ahead in every variant, but not shown to beat one** once the labels are
  corrected. Only 4 to 6 items differ between the arms.

**Next competitors**, to be written down in advance:
1. one Claude told to reject only for a defect this change introduces;
2. the same prompt sampled five times, majority vote, at the same cost;
3. "two samples must both reject".

**Before any claim:**
- a person, or a model family used in no arm, screens all 50 clean originals blind to the arm;
- the set grows to about 300 bases.

## Second run: the two cheaper competitors (`score_all.py`, `score_all.log`)

2026-11-05. Two more Claude Opus 5.5 arms, run the same way:
- **`claude-strict`:** one agent told to reject only for a defect the change introduces. The text is
  `STRICT_PERSONA` in `../planted/run_planted.py`, fixed before the run.
- **`claude-x5`:** the one-agent question asked by five identical seats, with WaRF's default review.

| | Calls | As labelled | Corrected: 16 real | 17 real (incl. fbcf2aa) | Defects the change introduced only |
|---|---|---|---|---|---|
| One Claude | 100 | 0.740 | 0.860 | 0.849 | 0.838 |
| One Claude, strict bar | 100 | **0.840** | 0.896 | 0.887 | 0.896 |
| Same question ×5 | 429 | 0.700 | 0.801 | 0.811 | 0.801 |
| WaRF five personas | 436 | 0.800 | **0.926** | 0.917 | 0.904 |

- **The panel does not beat the strict single Claude.**
  - Panel minus strict is −0.040 as labelled, and +0.008 to +0.030 on every corrected labelling
    (p 0.22–0.69).
  - Where the panel is ahead, it is on real defects: it rejects 15 of 17, against 11 for strict. In
    4 of its 5 misses, the strict prompt made Claude wave away a defect the change itself introduced,
    such as `gsMatrix<>` in a `T` template or `std::max(1e-10, tolerance)`. Only 1 of the 5 was the
    pre-existing issue the bar is meant to skip.
- **One persona seat alone does as well as the panel:** ADVOCATE 0.926 and SKEPTIC 0.918 on the 16
  real defects, each as one call. ADVOCATE was picked as the best after the fact, which flatters it.
- **Asking the same question five times is no use:**
  - It scores −0.06 to +0.00 against one call, at 4.3 times the calls.
  - The seats agree pairwise on 0.88 of clean items and on every planted item, so the majority repeats
    the shared judgement.
  - The replies always differ in wording, but the votes flip only on borderline clean items.
- **Why the persona panel beats the five identical seats:** leniency, not independent errors.
  - **Clean-item REJECT rates per seat:**

    | Persona panel | Rate | Identical seats | Rate |
    |---|---|---|---|
    | SKEPTIC | 0.36 | seat 1 | 0.55 |
    | ADVOCATE | 0.32 | seat 2 | 0.52 |
    | AUDITOR | 0.44 | seat 3 | 0.56 |
    | TEST-FOCUSED | 0.78 | seat 4 | 0.56 |

  - **Errors are positively correlated in both arms.**
  - **The panel's one "different" seat is outvoted.** TEST-FOCUSED differs from the others, and the
    majority overrules it.
  - **Every seat of every arm catches 49 of the 50 plants,** so on this set being lenient costs
    nothing.
- **Corrections from the recheck (`verify/x5-strict-audit/`, `verify/x5-only/`, `verify/critic2/`):**
  - The 4 clean items only the ×5 arm rejected are 1 real, 2 debatable and 1 false alarm;
    `score_all.py` counts all 4 as false alarms. Panel minus ×5 is therefore +0.06 to +0.125
    (p 0.002–1.0), not +0.10 to +0.125.
  - The planted half of `5c4f8f4` shows only an added blank line, because the plant removed the whole
    added line. Every arm misses it, so it should be dropped. That changes no difference between arms.
  - One ×5 review lost a seat to a timeout. The verdict is unchanged.

**Conclusion:**
- **On this set, WaRF's five-persona panel is a lenient reviewer at 4.4 times the cost.** One call
  with a lenient persona or a strict bar does about as well.
- **The next test needs a set where leniency costs recall:**
  - harder plants: the 11 disputed ones, cross-file plants, plants that ADVOCATE misses;
  - clean items screened before any arm runs;
  - preregistered one-call ADVOCATE and SKEPTIC arms.

## Rebuild

From `C:\workdir\warf\WaRF`, with `PYTHONIOENCODING=utf-8`:

    python .warf-experiments/evidence-set/build_set.py     # candidates.jsonl (seeded)
    python .warf-experiments/evidence-set/select_set.py    # items.jsonl from candidates + judgements

`judgements.jsonl` comes from the judging run and is not regenerated by these scripts.
