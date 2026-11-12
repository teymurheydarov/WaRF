# Lever "locate": make Jev point at an added line (2026-11-09)

**What was asked.** Each hunk (`run_narrow.hunks`) of the 132 dev items is split into chunks of at most 25 added lines. A hunk with 25 added lines or fewer is one chunk shown whole. A longer chunk shows the file header, the `@@` line, and up to 10 hunk lines before and after its labelled lines, unlabelled. The added lines of a chunk get the labels L1..Lk, shown as a `[Lj] ` prefix, and the state is `run_narrow.frame(domain, chunk)`.

One System One call per chunk (model jev-latest, answered by `typesafe/jev-1.14-20261014`) asks:
- `locate`: a choice, "Which added line introduces a defect, if any?", with criteria `NONE` = "No added line introduces a defect." and `Lj` = the line's text (stripped, cut at 300 characters; a blank line becomes "(blank line)");
- the 7 generic YES/NO checks of `run_narrow.CHECKS`.

The 10 hunks that only delete lines get the checks without `locate`, and count 0 in the locate score. No item consists only of such hunks. Jev accepted k = 25, including duplicate criterion texts, so no smaller k was needed.

**Scores, fixed before the run.**
- `locate` (primary): the maximum over the item's chunks of 1 − P(NONE).
- `checks`: the mean over the 7 checks of logit(maximum over chunks of P(YES)), from this run. It is a re-run of the reference N, but over chunks rather than whole hunks, and with labels in the state.
- `maxline`: the maximum over chunks and lines of P(Lj).

**Files.**
- `run_locate.py`: the requests. It resumes and imports `run_narrow`.
- `answers_locate.jsonl`: 271 calls, 0 errors.
- `smoke.jsonl`: the 2-item smoke test, 8 calls, not used in scoring.
- `score_locate.py`, with its outputs `score.log` and `scores.json`.
- `run.log`.

**Cost.** $0.02618 for the full run plus $0.00064 for the smoke test, $0.0268 in all (sum of `usage.cost`).

## Results (132 items; d = AUC − AUC(ref N), 95% stratified bootstrap)

| Score | AUC | Within thirds | LOO size + score | d vs N [95% CI] |
|---|---|---|---|---|
| ref N (frozen) | 0.892 | 0.830 | 0.910 | — |
| **locate, max 1 − P(NONE)** (primary) | 0.874 | 0.820 | 0.895 | −0.018 [−0.058, +0.022] |
| 7 checks, mean logit, this run | 0.901 | 0.848 | 0.909 | +0.009 [−0.012, +0.031] |
| max single-line P | 0.704 | 0.764 | 0.880 | −0.188 [−0.266, −0.107] |

- **Pointing at a line does not beat the reference.**
  - The primary score is 0.018 below N; the interval includes 0.
  - Among changes of similar size it scores 0.820, against 0.830 for N.
- **Jev does react to the locate question.**
  - Its argmax is NONE in 187 of the 261 chunks that have the question.
  - Mean P(NONE) is 0.392 on chunks of defective items and 0.651 on chunks of clean items.
  - But the locate score tracks the checks: Pearson r = 0.859 over the items. So it carries little that the checks were not already saying.
- **The probability of a single line is a poor score (0.704).** Jev spreads its mass over several lines. In a long chunk, no single line gets much.
- **The re-run checks reproduce N within noise** (0.901 vs 0.892). The small rise may come from the finer chunking: a maximum over more states.
- **Not checked:** whether the line Jev points at is the defective line. That would need a line-level label, and `defect` is a description, not a line number.
