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
