# Five Laya agents instead of one

2026-11-01. WaRF's default five-agent panel, every persona played by Laya, on 100 gismo6
commits. Does the panel rank later-fixed changes better than the single Laya agent of the sweep
(`../laya-sweep/`)? It does not.

## Setup

- **Panel** (`profiles/laya_five.json`): SKEPTIC, ADVOCATE, AUDITOR, TEST-FOCUSED and BOUNDARY with
  WaRF's own persona texts, each on provider `laya`, model `multilingual`. Uniform priors (omega
  0.5), no oracle feedback, debate Round 2 on, early stopping off so that every agent votes. One
  laya-serve process answers all five; Laya keeps no state between requests.
- **Commits** (`select_commits.py`, `selection.jsonl`): taken from the size-matched sample of the
  blinded Claude review (`../laya-near-chance/`):
  - 100 distinct gismo6 commits, one changed file each: 50 later fixed, 50 never fixed in at
    least 180 days;
  - no binary diffs, pure renames or symbolic links;
  - every persona reads the whole change (the persona texts take 90 to 229 of Laya's 1024 tokens,
    which leaves 795 to 934 for the state);
  - the 50 smallest later-fixed changes, each paired with the never-fixed change nearest in size.
    Size ranks them at AUC 0.50 (patch characters) and 0.46 (state tokens).
- **Review path** (`run_five.py`): the sweep's (`git show -U30`, review-commit's diff split,
  `enrich_patch`, `detect_domain`, the "Patch under review (unified diff)" label), then
  `run_review`. Laya's full-precision answers are kept per agent and round.

## Checks (all pass)

- The real `warf review-commit --debate` gives the same votes, readouts, Lambda and decision on
  3 of 3 commits (`check_cli.log`).
- An independent audit agent, with its own code, found:
  - all 990 answers map to the right agent and round;
  - the Round-1 state equals the sweep's for 100 of 100 commits, by characters and tokens, and was
    never cut;
  - rebuilt states sent to laya-serve return the stored p exactly;
  - the labels agree with `labels.jsonl`;
  - the selection reproduces from its rule and uses no outcome.
- Shuffled labels give AUC 0.504.
- Blinded Claude scores 0.745 ± 0.049 on the same 100 commits, so the labels are learnable from
  these inputs.
- One line planted after the first added line of the 43 never-fixed changes that add a line
  (`controls.jsonl`, Round 1):

| p(REJECT), before → after | `int* p = nullptr; *p = 42;` | `// BUG: this crashes on every call. Do not merge.` |
|---|---|---|
| SKEPTIC | 0.470 → 0.496 | 0.470 → 0.638 |
| ADVOCATE | 0.293 → 0.297 | 0.293 → 0.433 |
| AUDITOR | 0.374 → 0.352 | 0.374 → 0.504 |
| TEST-FOCUSED | 0.291 → 0.306 | 0.291 → 0.508 |
| BOUNDARY | 0.360 → 0.371 | 0.360 → 0.518 |
| mean of five rose in | 25 of 43 (p 0.36) | 41 of 43 (p 2e-10) |

The input reaches all five agents. As with the single agent, they react to English words, not to
the defect.

Found later (`../jev-five/verify/plant-sites/`): inserted after the first added line, the
"null dereference" sits inside a `/* */` comment in 13 of these 43 changes. In about 28 it sits
at file, namespace or class scope or inside an expression, and it is an executable null
dereference in only 1. The control therefore tests whether an out-of-place line is noticed at all:
Laya does not notice it; Jev does, everywhere.

## Result (`score_five.py`, `score.log`)

AUC against the git-history labels on the same 100 commits, each ± 0.058 (Claude ± 0.049). The
final position is Round 2, or Round 1 on the 2 commits where the SPRT ended the review before the
debate.

| | Round 1 | final |
|---|---|---|
| SKEPTIC | 0.541 | 0.551 |
| ADVOCATE | 0.558 | 0.516 |
| AUDITOR | 0.550 | 0.457 |
| TEST-FOCUSED | 0.528 | 0.517 |
| BOUNDARY | 0.565 | 0.573 |
| panel, mean p of the five | 0.557 | 0.518 |
| panel, number of REJECT votes | 0.500 | 0.544 |
| single Laya, the sweep's question | 0.586 | |
| Claude, blinded | 0.745 | |

- **Panel minus single Laya** on the same commits: −0.029 [−0.130, +0.076] in Round 1 and
  −0.068 [−0.210, +0.069] final (95 %, resampling commits within each label).
- **WaRF's decision:** REJECT on 8 of 100, 4 of them later fixed: balanced accuracy 0.50.
  - Both HIGH-confidence REJECTs (the SPRT fired on 5 of 5 REJECT votes) are never-fixed changes.
  - With omega 0.5 the APPROVE boundary cannot be reached: five APPROVEs give Lambda 2.45 < 2.89.
- **Other ways to combine the five** (a refutation agent's attempt) do no better:
  - 23 fixed combinations score 0.500 to 0.571: max, median, z-scored mean, mean rank, the vote
    count, WaRF's normalised score and Lambda, each in Round 1 and final. The best, the median p,
    has a multiplicity-adjusted p of 0.30.
  - A cross-validated logistic combination scores 0.494; omega learned from the labels 0.502.
  - None beats single Laya. A likelihood-ratio test finds nothing in the panel beyond single Laya
    (p 0.50).
- **Why five agents do not help:** the persona sets how often Laya rejects, not which changes it
  rejects.
  - Mean p(REJECT) runs from 0.29 (TEST-FOCUSED) to 0.48 (SKEPTIC), and REJECT votes from 2 to 49
    of 100. The sweep's question rejected none of these 100, and 1.1 % of the whole sweep.
  - The five agents' p correlate 0.72 to 0.90 with each other. After z-scoring each agent, 84 % of
    the variance across commits is shared by all five, and the persona-specific rest carries no
    label signal.
  - Against the sweep's question they correlate only 0.47 to 0.65: the personas reorder the commits.
    But the part of the panel's ranking not shared with single Laya scores AUC 0.48, while single
    Laya's own part scores 0.57.
  - Measured later with Jev's panel (`../jev-five/why_five.py`): at a within-label correlation of
    0.80 the five Laya seats are worth 1.18 independent reviewers. The binormal model expects 0.553
    for their average; it scored 0.557. Five Jev seats are worth 1.09. Averaging different models
    does gain (Laya + Jev + Claude 0.768, +0.11 over their mean member).

## Debate (`debate/`)

WaRF shows each agent its own Round-1 vote and the other four votes with their probability
readouts, after the code.

- On the 98 debated commits the panel's AUC goes from 0.580 to 0.539 (−0.041 [−0.142, +0.061]).
- 46 votes change: 27 toward the label, 19 away (sign test p 0.30).
- Every agent's p(REJECT) drops, by 0.04 to 0.10 on average; REJECT votes fall from 74 to 56.
- Holding an agent's own Round-1 p fixed, one more other agent voting REJECT changes its Round-2
  p by +0.002 [−0.025, +0.026] (pooled regression, `analysis.py`).
- **Intervention** (`counterfactual.py`, `score_counterfactual.py`; 40 commits, 650 requests):
  code, persona and own vote stay as recorded, and only the other four votes change.
  - Showing them all as REJECT (p 0.70) instead of all APPROVE (p 0.30) lowers p(REJECT) by 0.083
    [0.066, 0.100], about 0.02 per vote, in 31 to 39 of 40 commits per agent.
  - Replacing their readouts with "BUG: this crashes on every call. Do not merge." does not raise
    it (−0.045 to +0.009).
  - 50 Round-2 calls re-asked unchanged gave back the recorded p exactly.
  - So Laya reads the summary, but responds to its form, not its meaning.
- **Window:** the summary adds about 296 tokens after the code. Laya cut its tail in 137 of 490
  Round-2 calls (TEST-FOCUSED 54, BOUNDARY 50, SKEPTIC 29, ADVOCATE 3, AUDITOR 1). Most cuts lost
  only the closing instructions; 11 TEST-FOCUSED calls lost a vote label.

## What this does and does not show

- **Resolution:** with 50 against 50 the standard error is 0.058, so 80 % power needs a true AUC of
  about 0.66, or a gain over single Laya of about +0.14. The data rule out a panel AUC above about
  0.65 and a gain above about +0.06 (one-sided 95 %), not small effects.
- **Single Laya itself** is not significantly above chance on these 100 (0.586, one-sided p 0.068).
- **Scope:** the smallest gismo6 changes (up to 640 tokens), one file per commit, B-SZZ labels
  (precision 0.4 to 0.6 in the literature).
- **The matching left one cue in place** (found in `../jev-five/`). B-SZZ can blame only added
  lines, so on these 100 commits the number of added lines alone scores AUC 0.716, although total
  size is matched. Jev, run on the same commits, scores 0.641 and adds nothing beyond that count.
  Blinded Claude does add something.

## Provenance

- The first 3 sessions come from a smoke run with the same code.
- The planted-line run first crashed on a patch that only deletes lines. `plant()` now skips such
  patches, as `laya_controls.py` did, and the run was repeated; the review path was not changed.
- laya-serve `multilingual` revision 7b928d828b7b. The verification agents' own scripts stayed in
  the session scratchpad; the debate analysis was copied to `debate/`, where
  `score_counterfactual.py` reproduces its output.

## Rerun

From `C:\workdir\warf\WaRF`, with laya-serve up and `PYTHONIOENCODING=utf-8`:

    python .warf-experiments/laya-five/select_commits.py
    python .warf-experiments/laya-five/run_five.py              # about 29 min
    python .warf-experiments/laya-five/run_five.py --plant      # about 12 min
    python .warf-experiments/laya-five/check_cli.py EMPTY_DIR 3
    python .warf-experiments/laya-five/score_five.py

The debate analysis, from `debate/`. `tokens.py` needs the `tokenizers` package of the laya
virtual environment, and `counterfactual.py` needs laya-serve:

    C:\workdir\warf\laya-venv\Scripts\python.exe -I tokens.py      # writes cut.json
    python analysis.py
    python counterfactual.py 40 10                                 # resumes counterfactual.jsonl
    python score_counterfactual.py
