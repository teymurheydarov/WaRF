# A harder answer key, where leniency should cost caught defects

2026-11-05. On `../evidence-set/`, every reviewer arm caught 49 of 50 planted defects, so a lenient
reviewer lost nothing. That made WaRF's five-persona panel look as good as a strict single Claude,
or as one lenient persona alone. This set is built so that missing a defect has a price.

## How it differs from `../evidence-set/` (`build_hard.py`)

- **Clean versions are screened without Claude, before any reviewer runs.**
  - A base is kept only if every added non-blank line of the reviewed file is still attributed to its
    commit by `git blame origin/dev`, gismo dev as of 2026-10-01. Nothing it added was later changed
    or fixed.
  - Bases are committed between 2021-01-01 and 2026-04-01, so each has at least six months of later
    history.
  - Survival is evidence, not proof: a latent defect can survive.
- **The plants are subtler:**

  | Kind | What changes |
  |---|---|
  | `wrong_var` | One variable becomes its sibling from the same code: `i`/`j`, `u`/`v`, `m`/`n`, `nc`/`nr`, `ps`/`pc`, `dir`/`dim`. Never in a declaration. |
  | `accumulate` | `+=` becomes `=` |
  | `first_second` | `.first` ↔ `.second` |
  | `plus_one` | A binary `+ 1` is removed |

- **The two sets are disjoint:** bases used by `../evidence-set/` are excluded.
- **The same two-judge check:** two independent Claude judges per plant decide whether it compiles,
  whether it is a real defect and whether it is visible. A plant is kept only if both say it compiles
  and is a real defect (`judgements.jsonl`, `select_hard.py`).

## Preregistration

Fixed on 2026-11-05, before any reviewer saw any item of this set.

**Split** (`select_hard.py`, in the builder's seeded order):
- **pilot:** the first 20 kept bases, in `pilot/items.jsonl`;
- **test:** the next up to 50, in `items.jsonl`.

**Stage gate (pilot):**
- Run one Claude (`claude`) and ADVOCATE alone (`claude-advocate`) on the pilot.
- If ADVOCATE alone catches 18 or more of the 20 planted pilot items, the plants are not hard enough
  for this test. Then stop, report, and do not run the test split.
- The pilot is never pooled with the test.

**Arms on the test split.** All are Claude Opus 5.5 through `../planted/run_planted.py --set`, with
the CLI isolated as before:

| Arm | What it is |
|---|---|
| `claude` | One agent, the sweep's question |
| `claude-strict` | One agent, `STRICT_PERSONA` |
| `claude-advocate` | One agent, WaRF's ADVOCATE persona |
| `claude-skeptic` | One agent, WaRF's SKEPTIC persona |
| `claude-standard` | WaRF's five default personas with WaRF's default review: the panel |

The same question asked five times (`claude-x5`) is not run: on `../evidence-set/` it was no better
than one call.

**Metrics:**
- recall on planted items;
- false-alarm rate on clean items, against the survival-screened labels;
- balanced accuracy.

**Tests:**
- 2000 paired bootstrap resamples over bases, in which a base drawn twice counts twice;
- exact McNemar on the items only one arm gets right.

**The claim "the panel beats a single call"** needs the panel to beat **every** single-call arm in
balanced accuracy with McNemar p < 0.05. Anything less is reported as not shown.

**Corrections after the fact:** any relabelling of clean items after the run is reported as a
separate, secondary analysis next to the preregistered one.

## Status: stopped at the stage gate (2026-11-05)

- **The final build:** 116 candidates from 2017–2026, of which both judges kept 62.
  - Variable swaps often failed to compile until a sibling had to be in use within 15 lines.
  - The test split holds 42 bases, under the 50 allowed.
- **The pilot** (`pilot/`, 20 bases, 40 items per arm):

  | Arm | Planted caught | Clean rejected |
  |---|---|---|
  | One Claude | 20/20 | 6/20 |
  | ADVOCATE alone | 20/20 | 2/20 |

- **The gate:** ADVOCATE alone catches 20 of 20, at or above the threshold of 18. The plants are not
  hard enough, so **the test split was not run**, as preregistered.

**What this shows.** Claude Opus 5.5 found every planted defect that is visible in the diff:
- a wrong sibling variable, `+=` turned into `=`, `.first`/`.second`, a dropped `+ 1`;
- the operator flips and the `rows`/`cols` and loop-bound plants of the earlier sets.

That holds even for its most lenient persona. On defects of this kind, being lenient costs no recall,
so a panel can only help by removing false alarms, and one lenient persona already does that in one
call.

To put any pressure on recall, a test needs defects a diff-only reviewer can miss:
- real defects with confirmed fixes, the plan's set R. On the 100 real commits of `../four-arms/`,
  the panel's leniency cut the share of later-fixed changes it rejected from 52 % to 18 %;
- or defects whose wrongness depends on another file.

The test split (`items.jsonl`) is kept unreviewed.

## Rebuild

From `C:\workdir\warf\WaRF`, with `PYTHONIOENCODING=utf-8`:

    python .warf-experiments/hard-set/build_hard.py      # candidates.jsonl (seeded)
    python .warf-experiments/hard-set/select_hard.py     # pilot/items.jsonl and items.jsonl from candidates + judgements
