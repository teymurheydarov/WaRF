# WaRF — Ideas for Further Development

> Living document. Add ideas as they come up, mark status when picked up.
> Status: 💡 idea | 🔄 in progress | ✅ done | ❌ rejected (with reason)

---

## Related work (state of the art, June 2026)

> Read before the talk. These papers define WaRF's position in the field.

- **[ConSol (March 2025)](https://arxiv.org/abs/2503.17587)** ✅ READ (2026-08-20) — Applies SPRT to find consistent LLM reasoning paths efficiently. Their H0/H1 framing is explicit and prominent — too much so for WaRF's purposes (note from user). Key difference: their hypotheses live at the *sampler level* (is this model producing consistent outputs?); WaRF's hypotheses are about the *code* (defective or not), with SPRT as background machinery. Their heterogeneity means capability-level differences (GPT-4 vs smaller models); WaRF's heterogeneity is persona design — agents look for genuinely different things in the same artifact.
  > **TODO (technical doc):** Sharpen related work entry to distinguish "heterogeneity as capability routing" (ConSol) vs "heterogeneity as evaluation-frame diversity" (WaRF). Add: temperature diversity produces correlated samples from one framing; persona diversity produces structurally independent viewpoints.

- **[Asymptotically Optimal Sequential Testing with Heterogeneous LLMs (April 2026)](https://arxiv.org/pdf/2604.01086)** ✅ READ (2026-08-20) — "A bit different from our package" (note from user). Objective is cost+wait-time minimisation — that's why ≤2 agents is optimal. WaRF has no cost term; the objective is calibrated accuracy at controlled α/β, with early stopping as a side-effect of evidence rather than a direct optimisation target. Their "heterogeneous" means capability tiers to route across efficiently; WaRF's is persona diversity as a structural feature. Result is asymptotically optimal — operates in the large-sample limit. WaRF runs at ~62 oracle labels, nowhere near that regime.
  > **TODO (technical doc):** Add to related work: "routing across capability tiers" vs "constructing independent evaluation frames." Note asymptotic vs practical regime mismatch.

  > 💡 **Multi-objective extension** *(academic interest only — not for SoCraTes talk)*: one could combine the two objectives into a joint functional, e.g. `minimize λ·tokens + (1−λ)·error_rate`, and study the Pareto frontier over λ. At λ=0 this recovers WaRF (accuracy only); at λ=1 it recovers the 2604.01086 setting (cost only). The Pareto-optimal policy would be a natural follow-on paper. Not relevant to a practitioner audience.

- **[Beyond pass@1: A Reliability Science Framework for Long-Horizon LLM Agents (2026)](https://arxiv.org/pdf/2603.29231)** ✅ READ (2026-08-20) — Shared conceptual starting point (reliability science applied to LLMs) but diverges quickly. They target *long-horizon agents* — multi-step pipelines where a coding agent writes entire programs across many tool calls. Their reliability lens is about fault propagation across steps and redundancy at the pipeline level; closer to classical systems engineering (MTBF, failure-rate modeling). WaRF is a single-artefact, single-decision system with SPRT-derived statistical guarantees. User note: "despite starting from a similar idea, they move to a different direction and don't concentrate much on review." Cite as parallel work — same framing, different application domain. No technical doc update needed.

- **[Wisdom and Delusion of LLM Ensembles (2025)](https://arxiv.org/pdf/2510.21513)** — Studies when ensembles help vs hurt for code generation. Finding: ensembles do not always outperform single best agent. Matches WaRF's empirical result (SKEPTIC alone 6/7 > WaRF 4/7 on validation suite).

- **[Single-Agent Outperforms Multi-Agent Under Equal Token Budget (2026)](https://arxiv.org/html/2604.02460v1)** — Counter-evidence to multi-agent approaches on reasoning tasks. WaRF's response: code review is not reasoning — it is reliability engineering. Different task class.

- **[Adversarial Review: Cooperative Code Review through Structured Disagreement](https://openreview.net/forum?id=fOHvpLs6zp)** — Debate-style review: main agent + reviewer + critic argue iteratively. Contrast with WaRF's independent voting. WaRF is non-iterative by design (no inter-agent influence during a session).

- **[Debate or Vote: NeurIPS 2025 Spotlight](https://github.com/topics/multi-agent-debate)** — Direct comparison of debate vs voting in multi-agent LLM decision making. WaRF uses weighted voting; debate is the alternative design choice.

---

## Agent pool

### ✅ Add TEST-FOCUSED and BOUNDARY personas *(implemented 2026-07-22)*
- **TEST-FOCUSED:** *"Assume the test suite is incomplete. What would you test that isn't tested here?"*
- **BOUNDARY:** *"Always try the largest, smallest, None, empty, and negative inputs."*
- Directly addresses Type 1 failures (M-03 missing tests, M-06 integer overflow)
- Grows pool to 5 agents → unlocks SPRT early stopping for the first time
- **M-03 re-run:** REJECT [LOW] ✓ — TEST-FOCUSED+BOUNDARY+SKEPTIC all REJECT; AUDITOR+ADVOCATE missed scope
- **M-06 re-run:** REJECT [LOW] ✓ — BOUNDARY named INT_MAX+1 wrap explicitly; same pattern
- After 2 oracle updates: TEST-FOCUSED and BOUNDARY at ω=0.750 — highest in LOGIC domain
- SPRT early stopping now reachable: if both REJECT + AUDITOR REJECTs, Λ = −2.686 < −2.251 at k=3

### ✅ SAST agent (tool-backed oracle) *(Bandit implemented 2026-08-07)*
- Run Bandit or Semgrep on each file automatically before or alongside LLM agents
- Feed SAST output as oracle update at tier SAST (γ=0.7) — already supported
- Addresses Type 2 knowledge-gap failures (CVE-2024-47081)
- Implementation: call Bandit via subprocess in orchestrator, parse JSON output
- **As built:** `--sast` runs Bandit first, in the SECURITY domain only, as one extra vote at a fixed weight of 0.75 (`warf/sast.py`). Its weight is never learned — the oracle update skips it. Semgrep is not done.

### ✅ Decision-model agent: Jev / Laya *(implemented 2026-10-18)*
- Jev (TypeSafe, September 2026) and Laya (ConvAI, open weights, same month) are "System One" models: a state plus typed questions in, one option with a probability per option out, no generated text. That is the shape of a vote.
- **As built:** provider `jev` (`SystemOneProvider` in `warf/providers.py`) speaks `POST /v1/systemone`; `laya` is an alias for the same protocol on a local `laya-serve`. Each agent asks one Choice question — APPROVE / REJECT, the persona as the question, the orchestrator's message as the state — and renders the answer as `LABEL` + `p(APPROVE)=… p(REJECT)=… confidence=…`, so `_parse_vote`, the weights, `warf label` and persona retirement apply unchanged. The orchestrator appends its reply-format instruction only to providers of kind `text`. Jev not yet run for real (early access, key from console.typesafe.ai); Laya's first run is below. Both paths are exercised against a fake server in `tools/test_systemone.py`.
- 💡 **Use the probability.** Today the vote enters the SPRT with the fixed LLR like any other; p and confidence are only recorded in the vote's reasoning. Once a few dozen labelled sessions carry a decision vote, check whether p(REJECT) is calibrated. If it is, a per-vote LLR from it — or abstaining below a confidence floor (TypeSafe's own example puts "route to a human" at 0.5) — would be the panel's first evidence-weighted vote. Changing the step size changes §3 of the specification; do not do it quietly.
- 💡 **Fine-tune Laya on the corpus.** ConvAI reports the base checkpoints near chance zero-shot and 0.77 after task fine-tuning. The labelled `.warf/sessions.jsonl` (62 ground truths, more with the reverted-commit scan above) is the obvious training split. Laya reads 512–1,024 tokens of state, so this is a reviewer of hunks, not files.
- **First real run (2026-10-18, Laya `multilingual` on CPU, laya 0.4.11 in a Python 3.14 venv):** the wire protocol matched unchanged — vote, `p(APPROVE)/p(REJECT)` and `confidence` arrived through the existing parser, no field or shape fix needed (the server adds `x_jev_confidence`, `answer_confidence`, `action` and `routing`, all ignored). One agent `LAYA` with the README question: M-01 no-div-guard → APPROVE p(REJECT)=0.11, M-00 clean → APPROVE p(REJECT)=0.17, M-08 SQL injection → APPROVE p(REJECT)=0.20; the defective files are not separated from the clean one, as ConvAI's zero-shot numbers predict, and repeats are deterministic. `usage.input_tokens` 215 / 255 / 467 (state 150 / 190 / 402 tokens), `truncated: false` on all three, so the 1,024-token limit was not hit. Inference 0.45–1.5 s per call on 8 cores; the first votes measured 2.9 s because the alias default was `localhost`, which Windows resolves to ::1 first — default changed to `http://127.0.0.1:8000`, after which a vote takes 0.5 s. Setup: `pip install "laya[serve]"` 3½ min (torch 2.14.1+cpu, 124 MB wheel), `laya-serve` healthy after 74 s, 57 s of it fetching the 647 MB checkpoint (`convaiinnovations/laya`, subfolder `multilingual`, revision 7b928d8) into `~/.cache/huggingface`. Caveat for the probability idea above: Laya's `confidence` is normalised entropy (0.49 at p=0.89), not Jev's formula (`x_jev_confidence` 0.77 for the same answer); the served model name is `laya-rl-agent`. No errors.
- **Full suite (2026-10-29, same server with all three checkpoints preloaded):** one `LAYA` agent over M-00..M-13 with `--no-early-stop` and the ground truth applied, four profiles, every vote deterministic. Runner `tools/run_laya_suite.py`; data in `.warf-experiments/laya/` (`py tools/measure_llr.py --home .warf-experiments/laya --profile laya_q1`). README question (`laya_q1`): **1/12** on M-00..M-11, 2/14 with M-13 — the one REJECT is the use-after-free at p(REJECT)=0.66, every other file sits at 0.04–0.28 with the clean M-00 at 0.17, in the middle of the pack. Bounded statement "This code contains a defect that causes incorrect behaviour or a security vulnerability: true/false." (`laya_q2`): 2/12, 3/14; the same with "true means REJECT, false means APPROVE" spelled out (`laya_q2b`): 2/12, 3/14. The rewording lifts p(REJECT) on *every* file (M-00: 0.17 → 0.39 → 0.45): it moves the prior, not the separation — the share of defective files ranked above the clean one is 0.46 / 0.23 / 0.23, so no threshold on p beats the label either. The `typed-decisions` checkpoint with the README question: 1/14, no REJECT at all, p(REJECT) 0.27–0.49 throughout. So it is not the wording: zero-shot Laya does not read the code, and the fine-tuning idea above is the only route. `measure_llr.py` on the four profiles: P1 = 1.000 (one clean file), P0 = 0.923 / 0.846 / 0.846 / 1.000, separation +0.08 / +0.15 / +0.15 / 0.00; the script declines to derive an LLR at a rate of exactly 1, correctly, since n_good = 1 — the number to read here is P0. Laplace-smoothed by hand, LLR_APPROVE = −0.26 / −0.18 / −0.18 / −0.34: on this corpus a Laya APPROVE is, if anything, weak evidence *for* a defect, while the fixed constants credit it +0.981·ω — +0.49 at the starting ω, still +0.29 after fourteen labels had pulled LOGIC ω down to 0.30 (SECURITY 0.17, PERFORMANCE 0.25). The Beta update slows a confident, uninformative voter; it never reaches the near-zero step its measured rates imply, which is the case for the per-agent LLR of "Use the probability" above. Caveats: 13 of 14 files are defective, so P1 rests on one file; M-07 has no label in `corpus.json` or the corpus log and was labelled REJECT/LOGIC from its own comments (off-by-one, division by zero, unchecked `strcpy`).

### Domain-specialist agents
- CRYPTO agent: focused on cryptographic correctness (algorithms, key sizes, IV reuse)
- CONCURRENCY agent: race conditions, deadlocks, thread safety
- INJECTION agent: SQL, command, path traversal, XSS
- Trade-off: more agents = higher cost per review; use SPRT to keep cost bounded

### ✅ Iterative debate round *(implemented and validated 2026-07-21)*
- Implemented: second SPRT pass from Λ=0, per-agent anchored prompt, weights frozen
- **hooks.py result:** debate failed — SKEPTIC held a false belief despite correct explanation from AUDITOR/ADVOCATE
- **sessions_pre_auth_strip.py result:** debate succeeded — SKEPTIC's correct minority argument convinced both AUDITOR and ADVOCATE to change (unanimous REJECT, D2 score=−1.000)
- **Key finding:** debate propagates correct *reasoning*; it does not cure *false beliefs*
- **Prompt framing is load-bearing:** neutral anchor prompt ("do you maintain or revise?") required to prevent conformity collapse
- Literature precedent: Adversarial Review, multi-agent debate papers (see Related work)

### 💡 Subgroup debate — group agents differently for Round 2
- Instead of showing all agents all Round-1 votes, form subgroups for the debate
- Example: run SKEPTIC vs ADVOCATE first (adversarial pair), then AUDITOR sees their exchange and casts the deciding vote
- Motivation: a full all-vs-all debate may dilute the strongest disagreement; structured subgroups could surface it more sharply
- Also opens the door to tournament-style brackets in larger pools (e.g. 5 agents → two pairs debate, winners face the fifth)

### ✅ ConSol-style sampling experiment *(done as identical-persona pools, August and September 2026)*
- Instead of 3 distinct personas, sample the SKEPTIC prompt 3× at temperature=0.8
- Compare token-efficiency and accuracy vs WaRF's persona-diversity approach
- Answers: does persona diversity add value over temperature diversity alone?
- **As run:** five identical SKEPTICs at uniform weights (12 August, four `requests` files: REJECT [HIGH] on all four), then the clean head-to-head of 19–20 September on 12 labelled files: mixed panel 11/12, five AUDITORs 10/12, five SKEPTICs 10/12. Accuracy is a tie; only the single-persona pools were wrong at HIGH. A variant with a varied sampling temperature was not run.

### Optimal 2-LLM experiment *(motivated by 2026 paper)*
- The "Asymptotically Optimal" paper proves ≤2 LLMs suffice under cost+wait optimisation
- Experiment: try all 3 pairs (SKEPTIC+ADVOCATE, SKEPTIC+AUDITOR, ADVOCATE+AUDITOR)
- Which pair performs best? Does 3-agent pool add accuracy beyond the best 2-agent pair?

### Adaptive pool sizing
- Start with 3 agents; if confidence is LOW, automatically query 2 more
- Stops when SPRT fires OR confidence reaches MEDIUM
- Saves cost on obvious cases, adds depth on ambiguous ones

---

## Reliability and calibration

### ✅ Confidence intervals on ω *(implemented: `warf weights` and the MCP server report a 95% interval, Normal approximation)*
- Right now ω=0.500 can mean "reliably neutral" or "one data point, completely unknown"
- BOUNDARY in PERFORMANCE has α=1, β=1 — uniform prior, not a calibrated weight
- Show ω ± uncertainty band derived from Beta distribution variance: σ = sqrt(αβ / ((α+β)²(α+β+1)))
- Weights table and demo output would show e.g. `0.500 ±0.35` vs `0.636 ±0.08`
- Makes the weights honest and flags where more calibration is needed

### ✅ Reliability diagram (calibration plot) *(implemented 2026-08-07: `confidence_calibration.html`)*
- X axis: WaRF confidence level (LOW / MEDIUM / HIGH)
- Y axis: empirical accuracy at each level
- Requires ~30+ labelled reviews to be meaningful
- Classic tool from probabilistic forecasting; very slide-friendly
- Now on 62 labelled reviews: LOW 27%, MEDIUM 63%, HIGH 75% — still preliminary

### ✅ Weight trajectory visualisation *(implemented 2026-08-04: `weight_trajectories.html`)*
- Plot ω over time per agent per domain as oracle updates accumulate
- Shows self-correction visually
- Can be generated from sessions.jsonl
- Legend entries are clickable: two agents with identical histories draw on the same pixels, and a click brings one to the front

### 🔄 Formal pool-size analysis *(partly: `why_not_two_agents.html`, 2026-08-18)*
- Done: the page shows the maximum reachable |Λ| per pool size against both boundaries, from the current weights
- Not done: the curve of required pool size against desired early-stopping probability
- Extend §3.2.7 of SPECIFICATION.md: for a given ω distribution, what n is needed for SPRT to fire within k agents?
- Generates a curve: required pool size vs desired early-stopping probability
- Useful slide for the "cost of reliability" argument

---

## Input and review scope

### ✅ Multi-file review (git diff / SVN patch) *(implemented: `warf review <directory>` and `warf review-commit`)*
- Accept a diff/patch instead of a single file
- Split into per-file hunks, run WaRF on each, aggregate decisions
- Useful for PR/commit review automation
- **As built:** a directory is reviewed file by file, and `review-commit` splits a commit's diff per file (git and SVN formats are both parsed).

### 💡 MCP-based codebase navigation
- Instead of requiring the caller to pre-select files, give agents MCP tools: `read_file`, `search_symbol`, `grep`
- Agent reads the primary file, follows includes, navigates to type definitions — actively resolves context rather than receiving it passively
- Architecturally much better than file concatenation for large codebases (34k+ files)
- **Key tradeoff:** each tool call costs tokens + latency; a context-hunting agent may spend more on navigation than on the review itself
- Mitigation: SPRT can still bound the total cost — if high-weight agents agree early, stop before the slower agents finish navigating
- Requires changing the orchestrator: agents become mini agentic loops (prompt → tool calls → response), not single API calls
- Haiku-4-5 supports tool use, so the model layer is ready; the orchestrator change is the work
- **Cost concern:** on a large codebase with deep include chains, an unbounded navigation agent can be very expensive per review — need a token budget or depth limit per agent call

### ✅ Function-aware diff context *(implemented 2026-08-13: `warf/context_extractor.py`)*
- Current: `--context N` sends N lines around each changed line
- Problem: agents reviewing SSL/hostname commits in connection.py lack the architectural context of surrounding functions
- Lightweight fix: expand diff to include the full enclosing function body (not just N lines)
- Sits between current line-based context and full MCP navigation — no infrastructure change, just smarter context assembly
- Implementation: parse diff hunks, find enclosing `def`/`class` boundaries in the original file, include full body

### 💡 Review online repositories by URL *(added 2026-09-26)*
- **Today:** `warf review` needs a local file or directory, and `warf review-commit` needs a local clone for git. Only SVN accepts a server address (`svn://`, `svn+ssh://`, `https://`, see `warf/vcs.py`).
- **Idea:** `warf review-commit <commit-url>`, first for a GitHub commit URL, then for a pull request URL.
- **Cheapest design:** shallow-clone into a temporary folder, then reuse `review-commit` unchanged. Fetching only the diff is simpler but loses the function-aware context: `enrich_patch` reads the file at that commit from a local repository and falls back to the plain patch without saying so, which would drop the feature built for the TLS-style commits.
- **Why:** anyone could reproduce the talk's claims on a public commit (the urllib3 TLS change, `d4806150`); trying other codebases gets cheap, and the calibration needs more codebases; public history also holds free ground truth.
- **Later:** scan public history for commits that were later reverted, as REJECT label candidates (the urllib3 change was reverted twelve days later). A revert is not proof of a defect, so treat such labels with the same care as on slide 10.
- **Risks:**
  - Hostile code can carry instructions meant to sway the votes. Test this before advertising the feature; running the model CLI from a neutral folder does not cover it.
  - Private repositories need a token. Use the git credentials already on the machine; never store or log a token.
  - A large pull request means many files times five agents. It needs a file cap or a confirmation step.
  - Privacy is unchanged: the code already reaches the model provider today, unless the backend is a local Ollama model.
- **Suggested order:** (1) commit URL through a shallow clone, (2) pull request URLs, (3) the reverted-commit scan.

### ✅ GitHub Actions integration *(workflow implemented 2026-08-10: `.github/workflows/warf-review.yml`)*
- `warf-action`: runs WaRF on changed files in a PR, posts results as comments
- Exit code 1 on REJECT already supported — wires directly into CI
- **As built:** a workflow in this repository runs `warf review-commit` on the pull request's head commit (or a chosen commit, by hand) using the Anthropic API, and posts the verdict as a PR comment. It does not yet use `--fail-on`, so the check does not fail on a HIGH REJECT. A reusable, published action is not done.

### ✅ Per-project weight profiles *(implemented 2026-08-06)*
- Separate `profiles/<project-name>.json` per repository
- Weights calibrated on project-specific code style and risk tolerance
- Flag in CLI: `--profile my-project`

---

## Knowledge augmentation

### RAG on CVE databases
- Before each review, retrieve top-k CVEs matching the file's domain and language
- Inject as context into agent prompts: *"Known vulnerability patterns in this domain: ..."*
- Addresses Type 2 knowledge-gap failures without fine-tuning

### Fine-tuned agents
- Fine-tune a Haiku-class model on labelled code review data (correct REJECT / APPROVE)
- Would reduce common-mode failures if training data covers diverse vulnerability classes
- Higher cost, longer setup; probably post-SoCraTes

---

## Performance and cost

### Token cost vs pool size curve *(do alongside 5-agent experiment)*
- Run the same file through pools of 1, 2, 3, 5 agents
- Plot: agents used vs tokens spent vs decision confidence
- Shows the SPRT efficiency gain empirically
- One slide, very concrete

### Streaming votes
- Display agent votes as they arrive rather than after all finish
- Better UX for interactive use
- Minor implementation change in orchestrator

---

## Presentation and documentation

### ✅ Lambda trajectory display *(implemented 2026-08-03)*
- Show L moving left/right per agent during --demo mode as a visual bar
- Example (the original sketch, with a symmetric scale): `L: ░░░░▓▓▓▓▓▓░░░░  -2.89 ──── 0 ──── +2.89`
- **As built:** `◄B ░░░░░░░█░░░░│░░░░░░░░░░░░░░░ A►` on the real, asymmetric scale from B ≈ −2.251 to A ≈ +2.890; `│` marks λ = 0 and `█` the running λ after each vote.
- Makes the SPRT story immediate for a live audience — they see the needle move
- One afternoon to implement in orchestrator.py demo output block

### `--verbose-full` flag
- Print complete agent reasoning instead of 120-char excerpt
- User can already access full reasoning via sessions.jsonl, but inline is nicer

### ✅ Web dashboard for sessions.jsonl *(implemented 2026-08-07: `dashboard.html` plus the chart pages)*
- Simple HTML page that reads sessions.jsonl and shows review history
- Weight trajectories, decision breakdown, token costs over time
- Could be a single static HTML file with embedded JS
- Since then: sessions carry permanent numbers (`#N`, searchable), and debate sessions show both rounds

### ✅ README for public release *(written 2026-09-20)*
- `README.md`, with `GUIDE.md` for the reasoning behind the design

---

## Research directions

### Failure mode taxonomy (extend what we found empirically)
- Type 1: Persona bias (correctable with diverse agents)
- Type 2: Knowledge gap (requires external tools/oracles)
- Type 2b: Incomplete threat model (self-corrects with oracle updates)
- Are there more types? Study more failure cases

### Comparative study
- WaRF (3 agents) vs single best agent vs SAST alone vs WaRF+SAST
- On the same labelled dataset
- Answers: when does WaRF add value over simpler alternatives?

### Oracle confidence sensitivity analysis
- How sensitive is weight calibration to the choice of γ (oracle tier)?
- Currently: DEVELOPER=1.0, SAST=0.7, TEST=0.3, COMPILER=0.1
- Are these values well-chosen? Run experiments varying γ
