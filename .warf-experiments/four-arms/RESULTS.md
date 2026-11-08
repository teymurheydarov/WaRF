# Four reviewers on the 100 gismo6 commits

2026-11-04. Claude against Jev, each as one agent and as WaRF's five-persona panel, after the
earlier blinded Claude review (AUC 0.745) turned out to have used knowledge of the labelling rule
(`../something-wrong/`).

## Setup (`run_four.py`)

- **Commits and labels:** the 100 commits of `../laya-five/selection.jsonl`. B-SZZ git-history
  labels: 50 later fixed, 50 never fixed.
- **Review path:** all four arms go through WaRF's own review path (`../laya-five/run_five.py`),
  at uniform priors.
- **Arms:**
  - `claude-one`: one agent, Claude Opus 5.5 (`claude_cli`, `claude-opus-5-5`). It is asked the
    same question as Jev's one agent.
  - `claude-standard`: WaRF's default profile (the five personas) with
    `WARF_PROVIDER=claude_cli` and `WARF_MODEL=claude-opus-5-5`. WaRF's default review: no
    debate, early stopping on.
  - `jev-one` and `jev-standard`: the same two setups on `typesafe/jev-1.14-20261014`.
- **Claude isolation:** every CLI call runs with `--tools "" --strict-mcp-config
  --no-session-persistence` in an empty folder, so no agent can read the repository's later
  history.
  - Checked by hand: an isolated call reports no tools.
- **Input:** both models got the same text. Claude's message is Jev's state plus WaRF's 108-character
  reply format, confirmed by rebuilding all 100 messages.
- **Cost:** 590 Claude calls, all answered with a vote. Jev cost $0.02. No review errors.

## Result (`score_four.py`, `score.log`)

Balanced accuracy of WaRF's verdict (95 % bootstrap within class):

| | all 100 | without the 18 never-fixed changes that can never be labelled REJECT | REJECTs (later fixed) |
|---|---|---|---|
| Claude, one agent | 0.55 [0.45, 0.65] | 0.56 | 47 (26) |
| WaRF Claude, five personas | 0.53 [0.46, 0.60] | 0.56 | 15 (9) |
| Jev, one agent | 0.58 [0.48, 0.67] | 0.58 | 52 (30) |
| WaRF Jev, five personas | 0.56 [0.48, 0.64] | 0.57 | 24 (15) |

- **Claude vs Jev:** the difference is −0.03 [−0.13, +0.07].
  - The verdicts agree on 73 of 100. Only Claude is right on 12, only Jev on 15 (McNemar p 0.70).
- **Panel vs one agent:** −0.02 for both models.
  - The panels mainly approve more.
  - Their HIGH verdicts are all REJECTs after four REJECT votes. Claude: 5 of 10 later fixed. Jev:
    11 of 18.
- **Ranking:**
  - Jev one agent AUC 0.637; Jev panel mean p 0.626. The panel's Λ gives 0.58 for both models.
  - Claude's one agent gives only a vote, so its AUC equals its balanced accuracy.
- **No sign of the old leak.** The old review separated the 18 unlabellable changes from the other
  never-fixed ones at AUC 0.905; all four new arms score 0.45–0.50 there.
- **Power:** with 100 changes, only a difference of about 0.14 in balanced accuracy would show
  reliably.

## Why everything is near chance (`verify/explain/`, `verify/critic/`)

The classification below was done by hand and **not blinded**, so it leans toward Claude.

| What the 50 later-fixed changes hold | Count |
|---|---|
| A defect visible in the diff that the fix removed | 17 |
| Arguable | 4 |
| A real defect not visible from one file | 7 |
| No defect introduced: a later commit touched the lines for other reasons (renames, include reshuffles, author lines) | 22 |

- **Never-fixed side:** it holds unfixed real slips (wrong `@file` tags) and changes that only look
  wrong because the reviewer sees one file without the rest of the commit or its message.
- **Ceiling:** a perfect reviewer of the diff alone would reach only about 0.62–0.71 here.
- **Where there is a visible defect,** both models mostly find it.

## In short

- **Claude is not better than Jev.** Neither is clearly better than chance on these labels.
- **WaRF's five-persona panel does not beat one agent for either model.**
- **These labels cannot measure review skill.** That needs planted defects (`run_five.py --plant`),
  reviews that see the whole commit, or a blinded relabelling of fixes that touch the same hunk soon
  after.

## Rerun

From `C:\workdir\warf\WaRF`, with `PYTHONIOENCODING=utf-8`, and `TYPESAFE_API_KEY` /
`TYPESAFE_BASE_URL` in the user's environment for Jev:

    python .warf-experiments/four-arms/run_four.py --arm jev-one
    python .warf-experiments/four-arms/run_four.py --arm jev-standard
    python .warf-experiments/four-arms/run_four.py --arm claude-one --workers 2 --worker 0 --claude-exe <claude.exe>
    python .warf-experiments/four-arms/run_four.py --arm claude-standard --workers 4 --worker 0 --claude-exe <claude.exe>
    python .warf-experiments/four-arms/score_four.py

Run the Claude arms once per worker index. They took about 30 minutes in total.
