# Is Laya's near-chance score real?

2026-11-01, after the full sweep in `../laya-sweep/`. Against git-history (SZZ) labels Laya ranks
later-fixed changes at AUC 0.54, and 0.51 at matched patch size. These checks ask whether that is
an artifact of the pipeline or what Laya does.

## The pipeline (all checks pass)

- Rebuilding 120 inputs from git and asking laya-serve again gives back the stored p(REJECT)
  exactly, with identical length and token count (`laya_controls.py`).
- Laya's own state-token count tracks the characters sent, review by review: r = 0.992 on a log
  scale over all 36,715 reviews (`sanity_laya.py`).
- Every review got the full 65-token question. Laya lays out `[CLS] question [SEP] options [SEP]
  state [SEP]` and cuts only the state's tail, at 959 tokens (`laya/common.py`, `build_sequence`).
  The `truncated_questions` flag in 81 % of reviews only means that question's state was cut.
- Nothing sits in front of the code: the frame is the bare 58 to 64 character header.
- The vote is the argmax in all 36,715 reviews; shuffled labels give AUC 0.50; the same label join
  gives patch size 0.67.

## Laya on planted bugs (`laya_controls.py`, `controls.jsonl`)

120 fully read changes that git history says were fine, each with one line inserted after the first
added line:

| Planted | n | p(REJECT) before | after | rose |
|---|---|---|---|---|
| `int* p = nullptr; *p = 42;` | 94 | 0.158 | 0.155 | 46 % |
| `// BUG: this crashes on every call. Do not merge.` | 94 | 0.158 | 0.288 | 95 % |

Caveat found later (`../jev-five/verify/plant-sites/`): with the same insertion rule, the planted
"null dereference" was an executable dereference in only 1 of 43 laya-five changes. In the others
it sat in a comment, at file, namespace or class scope, inside an expression, or in a Python file.
So it tests whether an out-of-place line is noticed, not whether a real dereference is. The 120
changes here were not classified.

Hand-made one-line pairs, correct then buggy: `a + b` to `a - b` 0.062 to 0.061; `i < n` to `i <= n`
0.145 to 0.141; inverted null guard 0.103 to 0.135; double `delete` 0.103 to 0.083; division by
zero 0.174 to 0.100. Junk states: random characters 0.895, empty patch 0.190, lorem ipsum 0.030.
Laya reacts to English words and to how natural the text looks, not to what the code does.

## A blinded reference reviewer (`build_claude_sample.py`, `score_claude_review.py`)

176 later-fixed and 176 never-fixed phase-A changes that Laya read in full, paired by repository and
patch size (size AUC 0.500). Eight Claude (Opus 5.5) agents each read one batch file holding only
the state text Laya saw, with random ids, and ran no other tool.

| | AUC | 95 % bootstrap |
|---|---|---|
| Claude p(defect) | 0.780 ± 0.025 | 0.732 to 0.825 |
| Laya p(REJECT) | 0.542 ± 0.031 | 0.482 to 0.602 |
| patch size | 0.500 | |

Claude minus Laya: +0.16 to +0.32. Claude's top quarter holds 72 of 88 later-fixed changes, its
bottom quarter 15 of 88. Its most suspicious items name defects visible in the diff (`#ifcc`,
`free()` of a `getenv()` result, `reserve()` then `std::copy` to `begin()`, an inverted assertion).
22 of its reasons hint at remembered G+Smo history; without them the AUC stays at 0.780, and on
commits authored in 2025-26 it is 0.725 ± 0.078 (Laya 0.457), so memory explains little of it.

Found later (`../laya-five/select_commits.py`): 6 of the 352 patches show no code (3 binary
diffs, 2 pure renames, 1 editor lock-file symlink; 2 of them later fixed).
Without them Claude scores 0.776 ± 0.025 and Laya 0.540 ± 0.031 on 346.

## Debate (`laya_debate.py`, `debate.jsonl`)

WaRF's Round-2 prompt (`_build_debate_prompt`) on the same 352 changes, asked three ways. WaRF puts
the other agents' arguments after the code, so in the sweep's reviews Laya's 959-token window
would cut them off in 81 % of cases; these short changes mostly keep them (cut in 63 to 81 of 352).

| | AUC vs history | p(REJECT) when CLAUDE says REJECT / APPROVE |
|---|---|---|
| Round 1, no debate | 0.542 ± 0.031 | |
| Debate, Laya alone (sees only its own vote) | 0.572 ± 0.030 | |
| Debate, CLAUDE's verdict and reason for this change | 0.532 ± 0.031 | 0.152 / 0.167 |
| Debate, CLAUDE's verdicts dealt to the wrong changes | 0.557 ± 0.031 | 0.145 / 0.162 |
| CLAUDE's vote itself (REJECT on its top quarter) | 0.656 ± 0.029 | |

Laya's p does not follow the other agent's vote (AUC 0.48 with real verdicts, 0.46 shuffled), and it
voted REJECT on 1 or 2 of the 352 in every arm. Debate neither helps it nor makes it echo.

WaRF's full five-agent panel with Laya in every seat, debate included, is in
`../laya-five/RESULTS.md`: no better than one Laya on 100 of these changes.

## Published results (checked against the sources by a research agent)

- Lines added alone (LApredict) reached mean AUC 0.72 on SZZ labels and beat DeepJIT and CC2Vec
  (Zeng et al., ISSTA 2021). Size at 0.67 here is ordinary.
- SZZ precision against developer-named inducing commits is 0.36 to 0.66, B-SZZ 0.39 (Rosa et al.,
  ICSE 2021); 0.40 to 0.59 on the Linux kernel (Lyu et al., TSE).
- In PrimeVul's paired evaluation no model, GPT-3.5 and GPT-4 included, beat a random guess
  (Ding et al., ICSE 2025).
- Code LMs barely react to counterfactual edits of a diff (ReDef, arXiv 2509.09192, 2025), the
  same blindness the planted bugs show here.

## Rerun

From `C:\workdir\warf\WaRF`, with laya-serve up and `PYTHONIOENCODING=utf-8`:

    python .warf-experiments/laya-near-chance/laya-probe/sanity_laya.py .warf-experiments/laya-sweep
    python .warf-experiments/laya-near-chance/laya-probe/laya_controls.py 120
    python .warf-experiments/laya-near-chance/laya-probe/score_claude_review.py .warf-experiments/laya-near-chance/laya-probe/claude_review_result.json

`build_claude_sample.py` draws new random ids each run, so rerunning it invalidates
`claude_review_result.json`. numpy's BLAS crashes in `gs\cf\python.exe`, so these scripts avoid it.
