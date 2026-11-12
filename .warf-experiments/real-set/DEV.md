# Development log (the 132-item real set)

Nothing here is evidence. Every variant looked at is listed, so the number of looks is on record. A panel chosen here must be frozen and confirmed once on a fresh set.

## dev_explore.py, 2026-11-06 07:22: 414 variants looked at
best single call: claude-commit-strict 0.864; top 15:
  0.879  caught 56/66  false alarms 6/66  1-of-2 claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  2-of-3 claude+claude-strict+claude-commit-strict
  0.879  caught 56/66  false alarms 6/66  2-of-3 claude-commit+claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  2-of-3 claude-strict+claude-commit-strict+claude-standard
  0.879  caught 55/66  false alarms 5/66  3-of-4 claude+claude-commit+claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  3-of-4 claude+claude-strict+claude-commit-strict+claude-standard
  0.879  caught 55/66  false alarms 5/66  3-of-4 claude-commit+claude-strict+claude-commit-strict+claude-standard
  0.879  caught 56/66  false alarms 6/66  log-odds claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  log-odds claude+claude-strict+claude-commit-strict
  0.879  caught 56/66  false alarms 6/66  log-odds claude-commit+claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  log-odds claude-strict+claude-commit-strict+claude-standard
  0.879  caught 55/66  false alarms 5/66  log-odds claude+claude-commit+claude-strict+claude-commit-strict
  0.879  caught 55/66  false alarms 5/66  log-odds claude+claude-strict+claude-commit-strict+claude-advocate
  0.879  caught 55/66  false alarms 5/66  log-odds claude+claude-strict+claude-commit-strict+claude-standard
  0.879  caught 56/66  false alarms 6/66  log-odds claude-commit+claude-strict+claude-commit-strict+claude-standard

## finder + checker, 2026-11-06 07:32 (claude-verify on the 92 items claude-commit rejected; missing 0)
  0.773  caught 64/66  false alarms 28/66  finder alone (claude-commit)
  0.864  caught 56/66  false alarms 8/66  checker alone where asked
  0.864  caught 56/66  false alarms 8/66  finder AND checker
  0.864  caught 52/66  false alarms 4/66  best single: claude-commit-strict
  0.879  caught 56/66  false alarms 6/66  OR(strict, commit-strict) = W3
  0.886  caught 59/66  false alarms 8/66  OR(finder-checker, commit-strict)

## search checker: first 2 smoke answers discarded (the snapshot path used the 8.3 short name and the CLI refused it; fixed)
## finder + search checker, 2026-11-06 07:52
  0.894  caught 57/66  false alarms 5/66  finder AND search checker
  0.864  caught 56/66  false alarms 8/66  finder AND checker (no search)
  0.864  caught 52/66  false alarms 4/66  best single: claude-commit-strict
  0.902  caught 60/66  false alarms 7/66  OR(finder-search-checker, commit-strict)
  0.879  caught 59/66  false alarms 9/66  OR(finder-search-checker, strict)
  0.894  caught 61/66  false alarms 9/66  finder AND (checker OR search checker)
  0.864  caught 52/66  false alarms 4/66  finder AND checker AND search checker

## single strict reviewer with search, 2026-11-06 08:12
  0.894  caught 54/66  false alarms 2/66  one Claude, strict, whole commit + search
  0.894  caught 57/66  false alarms 5/66  finder AND search checker
  0.864  caught 52/66  false alarms 4/66  best single so far: commit-strict
  0.894  caught 58/66  false alarms 6/66  OR(finder-search-checker, strict+search)
  finder+search checker vs strict+search: only panel 5, only single 5, McNemar p 1.000

## effort levels (Opus, whole commit + search, strict), 2026-11-06 18:09
  0.939  caught 62/66  FA 4/66  1-of-3 low+default+max   vs best single (low): 6/3 p 0.508
  0.939  caught 62/66  FA 4/66  1-of-4 low+default+high+max   vs best single (low): 6/3 p 0.508
  0.932  caught 61/66  FA 4/66  1-of-2 low+max   vs best single (low): 5/3 p 0.727
  0.932  caught 61/66  FA 4/66  1-of-3 low+high+max   vs best single (low): 5/3 p 0.727
  0.924  caught 60/66  FA 4/66  1-of-3 default+high+max   vs best single (low): 6/5 p 1.000
  0.917  caught 56/66  FA 1/66  low   vs best single (low): 0/0 p 1.000
  0.917  caught 57/66  FA 2/66  1-of-2 low+default   vs best single (low): 1/1 p 1.000
  0.917  caught 59/66  FA 4/66  1-of-2 default+max   vs best single (low): 6/6 p 1.000
  0.917  caught 59/66  FA 4/66  1-of-2 high+max   vs best single (low): 5/5 p 1.000
  0.917  caught 58/66  FA 3/66  1-of-3 low+default+high   vs best single (low): 2/2 p 1.000
  0.909  caught 57/66  FA 3/66  1-of-2 low+high   vs best single (low): 1/2 p 1.000
  0.902  caught 54/66  FA 1/66  2-of-2 low+high   vs best single (low): 0/2 p 0.500
  single low: 0.917  caught 56/66 FA 1/66
  single default: 0.894  caught 54/66 FA 2/66
  single high: 0.894  caught 55/66 FA 3/66
  single max: 0.894  caught 56/66 FA 4/66
  pairwise disagreement (items): low-default 5, low-high 5, low-max 13, default-high 4, default-max 10, high-max 8
  (32 effort variants looked at)


## 2026-11-08: reviewer weights conditioned on the type of change (`dev_bytype.py`, no new calls)

The idea came from a lecture note: global weights can't say "reviewer A is good on module X and noise on module Y". Here the change type is the G+Smo module of the file (gsAssembler 28, gsCore 27, gsNurbs 12, the rest 9 or fewer). The pool is the 13 reviewers with all 132 answers. Everything is leave-one-out.

| Rule | BA |
|---|---|
| Best single reviewer, chosen globally (always picks Opus strict + commit + search at low) | 0.917 |
| Best single reviewer, chosen per module (falls back to global if fewer than 8 items) | 0.886 |
| Naive-Bayes pool of all 13, per-module rates shrunk to the global ones | 0.909 |

Conditioning makes things worse. The module winners in-sample differ (ADVOCATE on gsHSplines and gsIO, strict Opus on gsModeling), but those come from 7 to 9 items each and don't carry over to the held-out item.

## 2026-11-09: Jev's probability instead of its label (`dev_jev_threshold.py`, no new calls)

Jev's stored p(REJECT) on the 132 items.
- **AUC 0.854.** The label at p = 0.5 gives BA 0.705: the median p is 0.94 on defective items and 0.49 on clean ones.
- **A threshold chosen leave-one-out gives BA 0.833.** WaRF's log-odds mode would do much the same through its Platt fit.
- **Caveat:** the clean items here are not matched on added lines. Counting added lines alone gives AUC 0.834. Within thirds of added-line count Jev keeps AUC 0.75, 0.72 and 0.97 (the last third has only 3 clean items), so it has some signal beyond size, but most of the 0.854 is size.

## 2026-11-09: Jev with narrow questions, whole change and per hunk (`jev-narrow/`, $0.039)

**Setup:** one System One call per state asks the original question ("verdict") and seven narrow YES/NO checks: off by one, wrong condition, wrong variable, missing case, memory, interface, compile. There are two kinds of state:
- the whole change, exactly as WaRF sends it (same character count as the stored run);
- each hunk on its own, with its file header.

That is 321 calls in all, with no errors. The verdict re-asked reproduces the stored one (AUC 0.856 vs 0.854). Scripts: `run_narrow.py`, `score_narrow.py` (writes `score.log`), `boot_narrow.py`.

| Score | AUC | AUC within thirds of added lines | LOO AUC, size + score (size alone 0.807) |
|---|---|---|---|
| verdict, whole | 0.856 | 0.775 | 0.872 |
| verdict, max over hunks | 0.852 | 0.761 | 0.871 |
| narrow checks, whole, mean logit | 0.884 | 0.831 | 0.904 |
| narrow checks, hunk max, mean logit | **0.892** | **0.830** | **0.910** |
| all 8 whole answers + size, LOO logistic | | | 0.896 |

- **The narrow checks add ranking signal beyond change size.**
  - Among changes of similar size: 0.775 → 0.83.
  - Paired bootstrap of the AUC: +0.028 [−0.001, +0.060] for the whole change, +0.036 [+0.002, +0.075] per hunk.
  - Four aggregations were tried, so this is a development lead, not a result.
- **The best single checks are "wrong variable" (0.81 among changes of similar size) and "condition" and "missing" (0.79).** "Compile" is the weakest (0.68).
- **Asking per hunk adds nothing for the verdict question.** It helps the checks only slightly.
- **As a REJECT/APPROVE decision, with the threshold chosen leave-one-out, there is no gain:**

  | Score | BA | Caught | False alarms |
  |---|---|---|---|
  | verdict | 0.818 | 51/66 | 9/66 |
  | narrow, whole | 0.811 | 47/66 | 6/66 |
  | narrow, hunks | 0.826 | 49/66 | 6/66 |

  The narrow checks trade catches for fewer false alarms. Opus strict + search at low effort scores 0.917 here.
- **Confirmation (2026-11-09, `../confirm-set/README.md`, second test):** not shown. On the fresh 220 items, AUC N − V = +0.017 [−0.016, +0.051]. Jev's AUC there is only 0.75–0.77, below added lines (0.790).

## 2026-11-09: more Jev variants (`jev-narrow/`, $0.042)

- **Jev + size on fresh items** (`size_transfer.py`, no calls). A logistic model was fitted on dev and applied to the 220 confirm items unchanged. Fresh AUC:
  - size alone: 0.790;
  - size + V: 0.798;
  - size + N: 0.804.

  So on fresh items Jev adds almost nothing beyond counting added lines.
- **Other inputs, dev, whole state only** (`build_inputs.py`, `score_inputs.py`, `score_inputs.log`):

  | Input | Score | AUC | AUC within thirds | LOO size + score |
  |---|---|---|---|---|
  | 30-line diff | verdict | 0.855 | 0.775 | 0.872 |
  | 30-line diff | narrow | 0.884 | 0.831 | 0.899 |
  | Whole commit + message, cut at 50k chars | verdict | 0.852 | 0.784 | 0.885 |
  | Whole commit + message, cut at 50k chars | narrow | 0.878 | 0.828 | 0.899 |
  | Changed lines only | verdict | 0.801 | 0.721 | 0.850 |
  | Changed lines only | narrow | 0.844 | 0.776 | 0.881 |

  The whole commit ties the 30-line diff. Removing the context hurts, so Jev does use the surrounding code.
- **No stronger Jev on OpenRouter.** It lists only `typesafe/jev-router`, a chat router that passes requests on to other models at their prices. It is not a System One model, so it was not tried.

## 2026-11-09: Jev request variants (`jev-narrow/run_variants.py`, `score_variants.py`, $0.085)

Jev's contract has no field for examples. It takes a state as text, a JSON object or a list of turns, and question types `choice`, `score` and `noul`. All variants ask the verdict and the seven checks on the whole state. The comparison uses 128 items: the four few-shot examples (`fewshot.json`, the two shortest visible defects and the two shortest clean items) are excluded from every arm.

| Variant | Verdict AUC | Verdict within thirds | Narrow AUC | Narrow within thirds |
|---|---|---|---|---|
| plain (as before) | 0.853 | 0.761 | 0.881 | 0.821 |
| `noul` questions | 0.847 | 0.758 | 0.896 | 0.825 |
| plus a 0–4 severity `score` | 0.855 | 0.767 | 0.885 | 0.832 |
| JSON state {domain, file, diff} | 0.857 | 0.770 | 0.888 | 0.837 |
| few-shot: 4 labelled examples in a JSON state | 0.836 | 0.761 | 0.884 | 0.840 |

The severity score alone gives AUC 0.842, within thirds 0.766. Every variant is within about ±0.015 of the plain one, which is noise at n = 128. Few-shot examples do not help the verdict.

## 2026-11-09: G+Smo-specific checks (`jev-narrow/run_gismo.py`, `score_gismo.py`, `score_gismo.log`, $0.044)

Ten YES/NO checks were written by grouping the one-sentence descriptions of the 66 dev defects: physical vs parametric quantities, hard-coded dimension, single patch or patch-local index, double-only scalar type, compiler portability, Eigen layout, declaration/instantiation mismatch, cleared state, knot/degree/level counting, and unchecked input. The request, framing and hunk split are run_narrow.py's (whole change plus each hunk, 321 calls). The checks come from these items, so the numbers are in-sample and favour them.

| Score (132 items) | AUC | AUC within thirds | LOO size + score |
|---|---|---|---|
| verdict, whole | 0.853 | 0.769 | 0.872 |
| generic 7, hunks, mean logit (frozen N) | 0.892 | 0.830 | 0.910 |
| G+Smo 10, hunks, mean logit | 0.896 | 0.820 | 0.890 |
| G+Smo 10, whole, mean logit | 0.884 | 0.798 | 0.881 |
| all 17, hunks, mean logit | 0.904 | 0.844 | 0.907 |

Even in-sample, the G+Smo checks tie the generic ones, and all 17 together gain +0.012 AUC, which is noise at n = 132. The checks are precise but rarely fire: at p >= 0.5, "dimension" flags 14 defects and 1 clean item, "layout" 9 and 0, "input" 11 and 1, "physical" only 3 and 0. The two check sets rank the items alike (Spearman 0.84), so the specific checks add little Jev was not already saying. No confirm-set test was run: a gain that does not appear in-sample will not appear out of sample.

## 2026-11-09: six more Jev levers (`jev-narrow/<lever>/`, one README each; $0.195 in Jev calls)

Run as one workflow: one agent per lever built the states, ran Jev on the 132 dev items, and scored four scores fixed in advance with the new shared scorer `jev-narrow/jevscore.py`. A second, independent agent then recomputed the primary score from the raw answers and checked the states for leakage. All six reproduced and none leaked. Reference N (7 generic checks, mean logit of the hunk max): AUC 0.892, within thirds 0.830.

| Lever | Primary score | AUC | Within thirds | d vs N [95%] | Cost |
|---|---|---|---|---|---|
| repeat: mean of 3 identical runs | N on mean p | 0.892 | 0.834 | -0.000 [-0.006, +0.006] | $0.078 |
| paraphrase: original + 2 wordings per check | mean logit over the 21 | 0.897 | 0.838 | +0.005 [-0.004, +0.016] | $0.048 |
| context: declarations of the changed lines' names from the same revision, whole state | 7 checks | 0.881 | 0.832 | -0.011 [-0.040, +0.015] | $0.022 |
| beforeafter: old and new code (JSON) instead of a diff | 7 checks | 0.847 | 0.833 | -0.045 [-0.095, +0.000] | $0.020 |
| locate: "which added line introduces a defect?" per hunk | max 1 - P(NONE) | 0.874 | 0.820 | -0.018 [-0.058, +0.022] | $0.027 |
| combine: nested-LOO ridge logistic over size + 16 stored answers | held-out score | 0.883 | 0.777 | -0.009 [-0.043, +0.022] | $0 |

What was learned:
- **Jev is stable.** Between identical calls p moves by 0.01-0.02 on average, but the decision at 0.5 agrees in 97-99% of calls, and N's AUC varies by at most 0.004 between runs. The 0.892 is not one lucky run, and averaging repeated calls has nothing to cancel.
- **Jev gives one opinion per change, whatever the wording.** Item scores correlate 0.89-0.97 between paraphrases, 0.97 between the diff and JSON input formats, 0.97 with and without the retrieved context, 0.86 between locate and the checks, and 0.84 between the before/after and diff inputs. Ensembles of Jev calls therefore average near-copies (the same finding as the persona seats, n_eff about 1.1).
- **Context** may help where a defect needs another file (17 needs_other_file defects vs the 66 clean items: 0.862 vs 0.835 without context), but it costs about as much on the other defects. With 17 positives this is a direction only. The retrieval does reach relevant code: in 16 of 17 the block contains an identifier the defect description names.
- **Before/after** ties within thirds (0.833) but loses overall: without +/- markers Jev tracks change size less.
- **Learned weights** lose to the equal-weight mean logit, most of all among changes of similar size (0.777).

Scorer fix. The checkers found that `jevscore.loo_size` (and the same lambda in `score_narrow.py`, `score_gismo.py` and `score_inputs.py`) took the logit of every value in [0, 1], including the 5-8 items whose mean-logit score happens to fall there. `loo_size` now treats a score as a probability only when all of its values lie in [0, 1]. Corrected, N's LOO size + score is 0.905, not 0.910. The LOO columns of the earlier 2026-11-09 tables for mean-logit scores are off by up to 0.012 and were not rewritten; no conclusion changes, since every LOO comparison there is a tie.

Where Jev stands on dev: a ceiling of about AUC 0.89, within thirds 0.83-0.85, across 14 ways of asking. Every lever since the narrow checks lands inside ±0.02, and n = 132 cannot resolve smaller gains.

## 2026-11-11: a second Jev version as a WaRF seat (`jev-narrow/versions/`, $0.039)

OpenRouter's System One endpoint serves two Jev versions: `jev-1.14` (`typesafe/jev-1.14-20261014`, = `jev-latest`, used everywhere so far) and `jev-1.13` (`typesafe/jev-1.13-20260917`). Every other probed name (1.0-1.12, 1.15, mini, pro, large, 2, beta, preview, next) returns "does not exist", and the model list shows only `typesafe/jev-router`. `run_version.py` sent the frozen narrow request (verdict + 7 checks, whole change and each hunk, 321 calls) to `jev-1.13`; `score_versions.py` fixed the scores in advance.

| Score (132 items) | AUC | Within thirds | LOO size + score | d vs N 1.14 [95%] |
|---|---|---|---|---|
| N, jev-1.14 (reference) | 0.892 | 0.830 | 0.905 | |
| N, jev-1.13 | 0.896 | 0.829 | 0.907 | +0.004 [-0.016, +0.022] |
| WaRF seats: mean N of both versions (primary) | 0.897 | 0.833 | 0.906 | +0.005 [-0.007, +0.016] |
| V, jev-1.14 | 0.856 | 0.775 | 0.872 | |
| V, jev-1.13 | 0.866 | 0.778 | 0.878 | |

The two versions rank the items alike (Spearman 0.969 for N and for V; two runs of 1.14 give 0.995). So jev-1.13 is a near-copy of 1.14, not an independent seat, and the two-version panel gains nothing. No fresh-set test was run.
