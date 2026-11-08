# Jev on the five-Laya test commits

2026-11-02. Would TypeSafe's Jev have reviewed better than Laya? We ran Jev in WaRF on the same 100
gismo6 commits as `../laya-five/`, through the same review path (`run_jev.py`, which imports
`../laya-five/run_five.py`). Labels are the same git-history ones: 50 commits later fixed, 50
never fixed, in pairs of similar size.

## Setup

- **Access:** WaRF's `jev` provider, through OpenRouter's System One endpoint
  (`TYPESAFE_BASE_URL=https://openrouter.ai/api`, the user's OpenRouter key in `TYPESAFE_API_KEY`).
  Every answer came from `typesafe/jev-1.14-20261014` (requested as `jev-latest`).
- **Arms:**
  - `one`: a single agent, JEV, asked the sweep's question, as the single Laya agent was;
  - `five`: WaRF's five default personas, all on Jev, with uniform priors, the debate round on
    and early stopping off.
- **Controls:** the same planted lines as for Laya, on the 43 never-fixed changes that add a line.
- **Repeats:** the first 20 commits asked again (`repeat_one.jsonl`); two more full runs of the
  one-question arm were made during verification (`verify/refute/rerun_A.jsonl`, `rerun_B.jsonl`).
- **Size and cost:** 1,556 answers plus 206 in verification, $0.06 in total.

## Result (`score_jev.py`, `score.log`)

AUC against the git-history labels on the same 100 commits, each ± about 0.056:

| | AUC | matched pairs won (of 50) |
|---|---|---|
| Jev, one question | 0.641 | 31 |
| Jev, five agents, mean p, Round 1 | 0.628 | 30 |
| Jev, five agents, mean p, after the debate | 0.633 | 31 |
| Laya, one question (the sweep) | 0.586 | 30 |
| Laya, five agents, Round 1 / after the debate | 0.557 / 0.518 | 28 |
| Claude, blinded | 0.745 | 38.5 |
| number of added lines | 0.716 | |
| patch characters (matched) | 0.502 | 24 |

- **Repeatable:** Jev is not deterministic (2 of 20 answers identical on a second ask, mean
  difference 0.026, 1 vote flip), but the one-question AUC was 0.641, 0.651 and 0.633 in three
  runs. Label permutation p is about 0.01.
- **Better than Laya? Not shown.** On the same commits the difference is +0.055 [−0.12, +0.23]
  (one question), +0.071 [−0.10, +0.24] (panels, Round 1) and +0.115 [−0.05, +0.28] (after the
  debate, where Laya's window cut the debate text). Settling a 0.055 difference would take about
  1,050 later-fixed and 1,050 never-fixed changes; a 0.10 difference about 320 of each.
- **Like Claude:** Jev's scores correlate with Claude's (r 0.52; partial r 0.44 after size, file
  type, added and removed lines, date and label). Laya's do not (r −0.1).
- **Five Jev agents and the debate add nothing:** the panel scores −0.014 [−0.05, +0.02] against
  one question, and the debate +0.005 [−0.02, +0.03]. It changed 11 of 420 votes, 7 toward the
  label.
- **WaRF's decisions:**
  - one Jev agent rejects 53 of 100, 31 of them later fixed (balanced accuracy 0.59);
  - the five-Jev panel rejects 22, 14 of them later fixed (0.56); 16 of these stopped at the SPRT
    in Round 1.

## Most of Jev's signal is the number of added lines (`verify/refute/`)

- **Why added lines predict the labels.** B-SZZ can blame only lines a commit added. Later-fixed
  changes add a median of 4 lines, never-fixed ones 1. The 15 changes that only delete lines or
  only touch comments are all never-fixed. Added lines alone score 0.716, so the matching on
  total size did not remove this cue.
- **Jev's p follows that count** (Spearman 0.42 among later-fixed changes).
- **Once it is held fixed, Jev adds nothing:**
  - in a pair-matched conditional logistic regression, Jev is significant alone (p 0.021) but not
    after log added lines (p 0.30) or after 11 simple features (p 0.91);
  - cross-validated AUC: features alone 0.702, features plus Jev 0.691;
  - within bins of added lines Jev scores 0.583 (permutation p 0.12).
- **Claude keeps real signal beyond the same features** (p 0.002 after added lines, p 0.016 after
  11 features), and ranks 13 of the 18 pairs where the later-fixed change does not add more
  lines; Jev ranks 9.
- **Power of this check:** a planted independent signal of AUC 0.64 is detected beyond added lines
  in 61 % of simulations. So Jev's lack of extra signal is informative but not conclusive.
- **No sign of memorisation:** Jev is not better on older commits (0.59 against 0.69 on newer
  ones). But every commit and fix is public and predates Jev 1.14, so this cannot be ruled out.

## WaRF's own default review, every agent on Jev (`--arm standard`)

WaRF's default profile (the five personas, uniform priors, no provider on the profile), Jev
selected the documented way (`WARF_PROVIDER=jev`, model `jev-latest`), and WaRF's default review as
`warf review-commit` runs it: no debate, early stopping on. Same 100 commits; $0.017.

- The SPRT stopped 17 reviews after four REJECT votes; the other 83 asked all five agents.
- **WaRF's decision:** REJECT on 21 (12 later fixed), APPROVE on 79 (38 later fixed): balanced
  accuracy 0.530. The 17 HIGH-confidence REJECTs were later fixed 10 times.
- **As a ranking:** mean p(REJECT) of the agents asked 0.624 ± 0.056 (one Jev question 0.641,
  difference −0.017 [−0.052, +0.017]); WaRF's Lambda 0.586.
- Claude, blinded, scores 0.120 [0.017, 0.219] higher than this panel's mean p.

## Why five agents add nothing (`why_five.py`, `why_five.log`)

Stored scores only; no model was asked again.

- **The five seats are near-copies.**
  - Jev's five personas correlate 0.86 to 0.96 with each other across the 100 commits, and Laya's
    0.72 to 0.91.
  - The persona sets how strict a seat is (Jev REJECT votes 13 to 48 of 100, Laya 2 to 49), not
    which commits it finds risky.
  - Jev and Laya map the question and the diff to one probability without reasoning, so a persona
    cannot send them to look at different things.
- **Averaging gains only as far as the members' errors differ.** With mean within-label
  correlation r, n members are worth n_eff = n / (1 + (n − 1) r) independent ones. Under a
  binormal model their average then scores Φ(d̄ √n_eff / √2), where d̄ is the members' mean d′. This
  matches every average tried:

| Equal-weight mean of z-scored logits | members' AUC | r within label | n_eff | expected | observed | minus mean member |
|---|---|---|---|---|---|---|
| five Jev personas, Round 1 | 0.600 to 0.640 | 0.89 | 1.09 | 0.629 | 0.630 | +0.006 [−0.006, +0.017] |
| five Laya personas, Round 1 | 0.528 to 0.565 | 0.80 | 1.18 | 0.553 | 0.557 | +0.008 [−0.011, +0.028] |
| Jev asked three times | 0.633 to 0.651 | 0.99 | 1.01 | 0.642 | 0.646 | +0.004 [−0.002, +0.010] |
| Laya + Jev | 0.586 to 0.641 | −0.20 | 2.49 | 0.676 | 0.678 | +0.065 [+0.013, +0.115] |
| Jev + Claude | 0.641 to 0.745 | 0.53 | 1.31 | 0.720 | 0.718 | +0.025 [−0.000, +0.052] |
| Laya + Jev + Claude | 0.586 to 0.745 | 0.04 | 2.80 | 0.755 | 0.768 | +0.110 [+0.061, +0.157] |

- **Five independent reviewers of Jev's skill** would be expected to reach 0.76. Five Jev personas
  are worth 1.09 of them.
- **Averaging different models does work.** Laya and Jev are each weak, but together they beat
  their mean member, because their errors are unrelated, even opposed. No average beats Claude
  significantly (Laya + Jev + Claude: +0.023 [−0.062, +0.106]).
- **WaRF's SPRT counts the five votes as independent evidence.**
  - It ends the review at HIGH-confidence REJECT once four or five of the five Jev agents vote
    REJECT.
  - 10 of those 17 changes were later fixed (59 %), the same rate as a single Jev agent's REJECT
    (31 of 53, 58 %).
  - With all five voting REJECT, 6 of 11 were later fixed.
- **The debate has nothing to work with.** Each agent sees four others that already agree with it,
  and Jev changed 11 of 420 votes.

## Controls

| p(REJECT), before → after (43 never-fixed changes) | Jev, one question | Jev, five agents | Laya, five agents |
|---|---|---|---|
| `int* p = nullptr; *p = 42;` | 0.45 → 0.98 (43 rose) | 0.29 → 0.93 (43 rose) | 0.36 → 0.36 (25 rose) |
| `// BUG: this crashes on every call. Do not merge.` | 0.45 → 0.99 (43 rose) | 0.29 → 0.89 (43 rose) | 0.36 → 0.52 (41 rose) |

- **The planted "null dereference" is rarely one** (`verify/plant-sites/`). Inserted after the
  first added line, it sits inside a `/* */` comment in 13 of the 43 changes. In about 28 it sits
  at file, namespace or class scope, or inside an expression, where it would not compile. Only 1 is
  an executable null dereference.
- **So the control measures a reaction to a blatant, out-of-place line, not bug-finding.** Jev
  reacts to it everywhere, even inside comments; Laya does not react at all.
- **A one-line semantic test:** in a three-line `add()` diff, Jev rejected `a + b` → `a - b` at
  p 1.00 and accepted the reverse at p(REJECT) 0.20. Laya scored the two alike (0.062 and 0.061).

## In short

- Jev reads code in a way Laya does not: it reacts to wrong-looking code and agrees with Claude on
  which changes look risky.
- On these labels, though, its ranking (0.64) is not measurably better than Laya's, and it is not
  measurably better than counting added lines.
- Running it as five personas or with a debate changes nothing.
- Claude is the only reviewer here with signal beyond the simple features.

## Provenance and rerun

- The first 3 one-question sessions come from a smoke run with the same code. `run.log` has the
  rest.
- The verification agents' analysis is copied to `verify/`; `verify/refute/part2d_added.py`
  reproduces its log from there.
- Nothing was written to `../laya-five/` or any `.warf/` (checked by file times).

From `C:\workdir\warf\WaRF`, with `TYPESAFE_API_KEY` (and `TYPESAFE_BASE_URL` for OpenRouter) set
for the user, and `PYTHONIOENCODING=utf-8`:

    python .warf-experiments/jev-five/run_jev.py --arm one
    python .warf-experiments/jev-five/run_jev.py --arm one --repeat 20
    python .warf-experiments/jev-five/run_jev.py --arm five
    python .warf-experiments/jev-five/run_jev.py --arm standard
    python .warf-experiments/jev-five/run_jev.py --arm one --plant
    python .warf-experiments/jev-five/run_jev.py --arm five --plant
    python .warf-experiments/jev-five/score_jev.py
    python .warf-experiments/jev-five/why_five.py     # stored scores only, writes why_five.json
