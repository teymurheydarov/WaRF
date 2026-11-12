# Lever "beforeafter": old and new code instead of a diff (2026-11-09)

**Asked.** One Jev System One call per dev item (132 items, model jev-latest, served as `typesafe/jev-1.14-20261014`)
with the frozen questions of `../run_narrow.py` (verdict + the 7 generic YES/NO checks), on a JSON state
`{"task", "domain", "file", "code_before", "code_after"}` with
`task = "Compare code_before and code_after; questions are about what the change introduces."`

`code_before` / `code_after` are the changed file at `<commit>^` and `<commit>` (gismo6, `git show`, read only), cut
to each hunk's changed lines plus 40 lines on each side, located through the diff's hunk headers and joined with a
`...` line. Choices made while building:
- Only the diff part of the item's code is mapped. 119 of the 132 items carry a `# Full function context` appendix
  after the diff (WaRF's function-aware diff), which the reference states include and these states do not.
- Every context, `-` and `+` line of every hunk was checked against the git file text; all 132 items matched.
- Regions overlapping in the old or the new file are merged so no line appears twice: 189 hunks give 179 regions.
- A new file's `code_before` is "(the file does not exist before the change)".
- State size: median 7.3k chars (the whole-diff states: 7.0k).

**Files.** `build_states.py` -> `states.jsonl`; `run_beforeafter.py` (imports `run_narrow.ask/questions`, 4 workers,
resumable) -> `answers_beforeafter.jsonl`, `run.log`; `score_beforeafter.py` (imports `jevscore`) -> `score.log`.

**Cost.** 132 calls (2 smoke + 130), 0 errors, $0.0199 (sum of `usage.cost`).

**Scores**, fixed before the results were seen; primary BA7.
BA = before/after state, W = whole-diff state of `../answers.jsonl` (whole only), N = `jevscore.ref_N()`.
d = AUC difference with 95% stratified bootstrap (`jevscore.boot_diff`).

| Score | AUC | Within thirds | LOO size + score | d vs ref_N | d vs W7 |
|---|---|---|---|---|---|
| **BA7: 7 checks, mean logit (primary)** | 0.847 | 0.833 | 0.901 | −0.045 [−0.095, +0.000] | −0.037 [−0.088, +0.011] |
| BAV: verdict P(REJECT) | 0.834 | 0.776 | 0.874 | −0.058 [−0.111, −0.007] | −0.050 [−0.105, +0.001] |
| BA7+W7: mean of the two | 0.885 | 0.856 | 0.900 | −0.007 [−0.032, +0.018] | +0.001 [−0.025, +0.025] |
| BA7+N: mean of the two | 0.887 | 0.852 | 0.912 | −0.005 [−0.030, +0.017] | +0.003 [−0.025, +0.031] |
| W7: whole diff, 7 checks (reference) | 0.884 | 0.831 | 0.904 | −0.008 [−0.028, +0.009] | 0 |
| WV: whole diff, verdict (reference) | 0.856 | 0.775 | 0.872 | −0.036 [−0.074, −0.002] | −0.028 [−0.060, +0.001] |
| ref_N | 0.892 | 0.830 | 0.910 | 0 | +0.008 [−0.009, +0.028] |
| added lines | 0.834 | 0.602 | 0.785 | | |

**Reading.**
- Before/after code ranks worse overall than the diff: BA7 0.847 vs W7 0.884 and ref_N 0.892 (d vs ref_N −0.045, the
  interval touches 0). Among changes of similar size it ties them (0.833 vs 0.831 / 0.830), and with size in a
  LOO model it ties too (0.901 vs 0.904 / 0.910). So the loss is in the size-tracking part of the score: without
  `+`/`-` markers Jev no longer sees how much was added.
- The verdict on before/after is no better than on the diff (0.834 vs 0.856).
- Averaging BA7 with a diff score gives the highest within-thirds AUC seen so far (0.856, 0.852), but the AUC and LOO
  gains are ≤ 0.003 with intervals ±0.03, and BA7 and W7 rank alike (Spearman 0.84). Within-thirds differences of
  ~0.02 have been noise in every earlier lever; this is not a result.
- Per check, "missing" loses most (0.788 vs 0.864 AUC), "memory" gains (0.858 vs 0.832). One run, no repeat, so the
  per-check differences have no noise estimate.
- `jevscore.loo_size` takes a logit of any score inside [0, 1]; 5 (BA7), 7 (W7) and 7 (ref_N) mean-logit values fall
  there. Fitting the Jev scores as they are (`LOOraw` in `score.log`) moves their LOO numbers by ≤ 0.012:
  BA7 0.905, W7 0.899, ref_N 0.905, BA7+W7 and BA7+N 0.912, all ties at this n.
