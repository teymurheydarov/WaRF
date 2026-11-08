# Planted defects: Claude alone against a mixed log-odds panel

2026-11-04. Does a panel of different models, combined by WaRF's new log-odds mode
(`--aggregate logodds`), beat its best member when the right answer is known?

## Setup

- **Items (`plant.py`, `items.jsonl`):** 54 gismo6 C/C++ changes that git history says were never
  fixed. Each is reviewed twice:
  - **clean**, as it was;
  - **planted**, with one operator flipped in an added code line: `==`/`!=`, `&&`/`||`, `<`/`<=`,
    `+`/`-`, `++`/`--`, `true`/`false`, and so on.

  That gives 108 items. Laya reads every item whole: 0 of 108 truncated.
- **Answers (`run_planted.py`):** each reviewer was asked once per item through WaRF's
  `run_review` as a single agent, with the same question:
  - Claude Opus 5.5, through the CLI with no tools, no MCP and an empty folder;
  - Jev (`typesafe/jev-1.14-20261014`);
  - Laya (local `multilingual`).
- **Arms (`score_planted.py`):**
  - **Claude alone:** Claude's own WaRF verdict.
  - **Mixed panel:** CLAUDE + JEV + LAYA through WaRF's real `run_review(aggregate="logodds")`
    with default early stopping. The stored answers are replayed, so the panel's Claude seat is
    exactly Claude alone's answer.
  - **Calibration:** learned out of fold, from 5 folds of bases. A cold start with no calibration
    is also reported.
- **Cost:** Jev $0.005. No errors.

## Result (`score.log`)

Balanced accuracy, with a 95 % paired bootstrap over bases:

| | Balanced accuracy | Planted caught | Clean passed |
|---|---|---|---|
| Claude alone | 0.824 [0.750, 0.889] | 52/54 | 37/54 |
| Mixed panel, calibrated | 0.852 [0.787, 0.917] | 50/54 | 42/54 |
| Mixed panel, cold start | 0.852 [0.778, 0.917] | 52/54 | 40/54 |
| Jev alone (member) | 0.648 | 54/54 | 16/54 |
| Laya alone (member) | 0.500 | 0/54 | 54/54 |

- **Calibrated panel minus Claude:** +0.028 [−0.009, +0.065]. The panel alone is right on 5 items,
  Claude alone on 2 (exact McNemar p 0.45).
- **Cold start minus Claude:** +0.028, with 3 against 0 (p 0.25).
- **Not shown.** About 300 bases would be needed to detect a gain of this size.

## What the panel does (`verify/`)

Three independent recomputations agree with `score.log`. One of them re-derives every panel verdict
from the spec by hand, with no differences from WaRF's output. Calibration has no leakage, and Claude's seat gets
the same message as Claude alone.

- **All of the gain is Jev vetoing Claude's REJECTs.** In every fold, Jev's evidence crosses zero
  near p(REJECT) 0.81–0.85, and its intercept outweighs one Claude REJECT. So the panel roughly
  means "REJECT only if Claude rejects and Jev's p is above about 0.55".
  - The fixed rule "REJECT if Claude and Jev both reject" scores 0.861 with no calibration: 4 items
    against 0.
  - All 7 flips are LOW confidence, and 3 sit within 0.04 of the threshold.
- **Laya detects nothing.** It voted REJECT on 0 of 108.
  - Calibrated, its evidence is about 0, and it cost one catch.
  - At cold start, its constant APPROVE is what makes the panel work. Without Laya, the cold-start
    panel drops to 0.685.
- **The "clean" labels are noisy.** 8 of Claude's 17 rejections of clean items point at defects
  that really are in the original code: an Eigen aliasing assignment, `new` assigned to a value,
  an inverted `mkdir` result, unbalanced braces. Two of the panel's five wins are on such items.
- **The plants by hand** (unblinded):

  | Plant | Count |
  |---|---|
  | Real visible defect | 42 |
  | Harmless | 5 |
  | Dead code | 2 |
  | Would not compile | 5 |

  Claude names the plant in every real planted item it rejects. It misses no real plant, so this
  set cannot show a panel catching what Claude misses.
- **On the cleaned set** (no harmless, dead or non-compiling plants, and no defective originals),
  panel minus Claude is between −0.014 and +0.012.

## In short

- **On planted one-token defects, the mixed log-odds panel does not measurably beat Claude alone.**
  The direction slightly favours the panel, but only through Jev vetoing Claude's false alarms. A
  trivial "both must reject" rule does as well.
- **Laya contributes nothing** but a bias term.
- **Claude already catches every real plant,** so the test has no room for a panel to find more.

## What would settle it

- Real defects with confirmed fixes.
- Clean changes screened for defects that were already in the code.
- Questions limited to the change itself.
- Simpler competitors written down in advance: Claude AND Jev, Claude with a tuned threshold,
  several Claude samples.
- Calibration from an independent labelled set.
- Drop-one-member ablations.
- About 300 or more bases.

## Five Claudes against one Claude (`score_five.py`, `score_five.log`)

2026-11-04, the same 108 items.
- **Arm (`run_planted.py --arm claude-standard`):** WaRF's default five personas, all on Claude
  Opus 5.5, with WaRF's default review: no debate, early stopping on, uniform weights. That makes
  481 calls, against 108 for Claude alone.
- **What the panel's rule comes to:** at uniform weights WaRF's vote mode is a plain majority vote.
  It stops early after four REJECTs.

| | Balanced accuracy | Planted caught | Clean passed |
|---|---|---|---|
| Claude alone | 0.824 [0.750, 0.889] | 52/54 | 37/54 |
| Five Claudes | 0.861 [0.796, 0.926] | 51/54 | 42/54 |

- **Difference:** +0.037 [+0.000, +0.083]. Five Claudes alone are right on 5 items, one Claude alone on 1
  (McNemar p 0.22). The difference is ≤ 0 in 6 % of resamples.
- **The gain depends on a scoring choice:**
  - **Cleaned set:** +0.029 (2 against 0, p 0.50).
  - **The 8 clean originals that hold a real defect counted as defective:** +0.009 (3 against
    3, p 1.0).
- **On real commits it does not hold.** `../four-arms/` ran the same comparison on 100 gismo6
  commits: −0.020. The panel rejected 15 changes where one Claude rejected 47, and 14 of the 15 were
  among the 47. Recall fell from 0.52 to 0.18.
- **What the panel removed:** only REJECTs of clean items. They were:
  - 3 of the 4 hand-classed false alarms (#3, #48, #54);
  - 2 alarms on defects really in the original (#7, #52).
- **What it kept:**
  - the false alarm #35, which comes from misremembering the code base;
  - all 4 judgement calls;
  - 6 of the 8 real defects in the originals.
- **What it added:** one new error, a harmless plant it approved. It caught nothing one Claude
  missed.
- **The panel is a more lenient filter on the same judgements.** 14 of its 15 errors are also
  Claude alone's errors, and the seats' clean-item REJECTs fall almost entirely inside Claude
  alone's.
  - On the planted set the plants are easy, so leniency costs no recall. On real commits it costs
    recall heavily.
  - Whether the removed alarms were one-off noise or only a stricter question's bar cannot be told
    from these data: no item was sampled twice with the same prompt.
- **Single seats** score 0.69 to 0.89 here and 0.51 to 0.57 on the real commits. The best seat on
  one set is near the worst on the other.

**In short:** five Claude personas are not shown to beat one Claude. They remove borderline alarms,
not shared mistakes, and on real commits that leniency loses defects. The competitors they must beat
are:
- the same prompt sampled five times with a majority vote, at the same cost;
- one Claude told to reject only for a defect the change introduces.

Neither has been run.

Verification: `verify/five-audit/` and `verify/critic5/`.

## Corrections during verification

- `score_planted.py`'s bootstrap counted a base drawn twice only once, which made the intervals too
  narrow (the reported +0.028 had read [+0.000, +0.059]). This is fixed, and the numbers above are
  the corrected ones.
- The boundary-swap subset was chosen before any result was looked at, but written after Jev's run
  had finished.

## Rerun

From `C:\workdir\warf\WaRF`, with `PYTHONIOENCODING=utf-8`. Laya needs laya-serve on 127.0.0.1:8000;
Jev needs `TYPESAFE_API_KEY` in the user's environment.

    python .warf-experiments/planted/plant.py
    python .warf-experiments/planted/run_planted.py --arm laya
    python .warf-experiments/planted/run_planted.py --arm jev
    python .warf-experiments/planted/run_planted.py --arm claude --workers 3 --worker 0 --claude-exe <claude.exe>
    python .warf-experiments/planted/score_planted.py

Run the Claude arm once per worker index. It took about 8 minutes.
