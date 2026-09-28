# WaRF — A Guided Introduction

> **What you need to know to understand what WaRF does, why it does it, and what it found.**
>
> Last checked against the code and the session log: 20 September 2026. Installation and commands are in
> `README.md`; how to read a verdict is in `warf/policy.md`.

---

## What is WaRF?

**WaRF** stands for **Weighted n-Agent Reliability Framework**.

Break that apart:

- **Weighted** — not all agents are equal. Each agent earns a numerical weight based on its track record. A agent that has been consistently right carries more influence than one that has been inconsistently right. The weights are not set by hand; they are learned from experience.
- **n-Agent** — the pool size is variable. The default is five agents — it began with three, and the early results further down come from that pool — and any subset can be chosen per review. As the pool grows, statistical efficiency improves.
- **Reliability Framework** — this is the key word. WaRF does not try to teach agents to be smarter. It treats them as components in a reliability system — components with known error rates that can be measured, tracked, and calibrated over time. The same philosophy underlies industrial quality control: you do not need to understand *why* a component fails; you need to measure *when* it fails and weight it accordingly.

WaRF applies this to LLM-based code review. The question it answers is not *"did this agent find a bug?"* but *"given this agent's historical accuracy in this domain, how much should this vote shift our confidence?"*

---

## The problem

You ask an LLM to review a piece of code. It says "APPROVE." Should you trust it?

Sometimes. But a single model run is unreliable in a specific, hard-to-detect way: **the model may be confidently wrong**. LLMs do not have calibrated uncertainty. They do not tell you when they are near the edge of their knowledge. They produce fluent, plausible reasoning regardless of whether that reasoning is correct.

Worse: if you ask the same model ten times, you mostly get ten agreements — not because the code is definitely safe, but because the model is *internally consistent*. Consistency is not accuracy.

The natural response is to add more agents. But here you run into the **common-mode failure** problem. If all your agents were trained on similar data, they share the same blind spots. Adding more copies of the same reviewer does not add information — it adds confidence. In the worst case, a pool of ten homogeneous agents produces a unanimous wrong verdict at high confidence. This is strictly worse than a single agent, because it is harder to override.

Attitudinal diversity helps, but only partially. Three agents with different personalities (sceptical, lenient, neutral) will disagree more often than three copies of the same agent. That disagreement is real information. But if the code contains a subtle vulnerability that requires specialist knowledge none of the agents have — they will all miss it, regardless of how different their attitudes are.

WaRF is built with these limits in mind. It does not claim to solve the knowledge-gap problem. It claims to make the best possible use of what the agents collectively know, to measure and track where they fail, and to be honest about uncertainty.

---

## The five agents

WaRF ships with five agents. Each is given a fixed **persona** — a system-level instruction that shapes how it reads code before it sees a single line:

| Agent | Persona in brief | What it looks for |
|---|---|---|
| **SKEPTIC** | *"Search hard for bugs, missing guards, edge cases, and unsafe assumptions — assume nothing is correct until checked."* Rejects only if it can name an input or state that produces wrong behaviour. | What can go wrong |
| **ADVOCATE** | *"Assume the code is correct unless you find a clear, demonstrable defect. Defend the author's intent."* | Whether the code does what its author meant |
| **AUDITOR** | *"Apply standards and best practices without bias toward approval or rejection."* | Compliance with good practice |
| **TEST-FOCUSED** | *"If this code were wrong, would a test catch it?"* Rejects failure paths that would be silent. | Errors nobody would notice |
| **BOUNDARY** | *"Trace what happens with None, empty collections, zero, negative values, maximum values, and off-by-one inputs."* Rejects only boundaries that are genuinely mishandled. | Edge inputs |

These are not cosmetic differences. In practice they produce genuinely different votes on the same code. SKEPTIC will flag something as an edge case that ADVOCATE reads as an acceptable design choice. AUDITOR will often hold the deciding position.

**Why these five?** The first three are the natural stances a human reviewer can take. A code author (ADVOCATE) tends to defend their work. A security reviewer (SKEPTIC) tends to look for what can go wrong. A compliance officer (AUDITOR) tries to apply the rule without stake in the outcome. TEST-FOCUSED and BOUNDARY were added in July 2026, after a synthetic validation suite exposed persona bias: planted defects — a missing test, an integer overflow — that AUDITOR and ADVOCATE both read straight past. They are lenses rather than attitudes: each looks for one class of defect the stances tend to miss.

**A persona must state a bar, not only a lens.** In September 2026 every agent's votes were measured against ground truth. An instruction like "look hard for problems" turned out to produce an agent that always finds one: the original TEST-FOCUSED voted REJECT on all 38 labelled reviews it took part in, which makes its vote worth nothing, and BOUNDARY was at chance. The current personas therefore say when to APPROVE as well as what to hunt for — SKEPTIC must be able to name a failing input, BOUNDARY must tell handled and unreachable boundaries from mishandled ones, TEST-FOCUSED must find a failure that would be silent.

**What attitudinal diversity does and does not buy you.** If agents disagree because of different priors about what constitutes a defect — that disagreement is resolvable through calibration. The Bayesian weight system learns which agent's attitude leads to better outcomes in which domain. AUDITOR is the clearest example: its weight is 0.77 in LOGIC and 0.61 in SECURITY (profile snapshot of 13 August 2026) — same agent, same prompt, but in SECURITY it approved too much code that turned out to be bad. The disagreement led to calibration.

What diversity of persona does *not* fix: if all agents share a factual misconception, they will all vote the same way regardless of their attitude. The misconception is not in their attitude; it is in their knowledge. More diverse personalities do not help here.

**Personas are fixed; weights are adaptive.** The persona is the prior. The weight is the posterior. After enough oracle updates, the weight system has done more teaching than the persona ever could — by silently reducing the influence of agents that are systematically wrong on certain code.

---

## How votes become a decision

### The sequential approach

The naive approach is to query all agents, average their votes, and threshold the result. WaRF does something more principled: it queries agents **one at a time**, in order of descending weight, and stops as soon as the statistical evidence is strong enough. This is the **Sequential Probability Ratio Test** (SPRT), developed by Abraham Wald in 1945 and used in clinical trials, industrial quality control, and reliability testing.

The key insight: you do not always need all the evidence. If the first two agents both strongly reject the code, collecting a third vote may be unnecessary — it is unlikely to reverse the decision and it costs money. SPRT formalises exactly *when* you have enough evidence to stop.

### The accumulator Λ

WaRF maintains a running number Λ (lambda), starting at 0. Every agent vote updates it:

- An **APPROVE** vote shifts Λ upward by `ω × 0.981`
- A **REJECT** vote shifts Λ downward by `ω × 1.253`

where ω is the agent's weight in the current domain (between 0 and 1).

The increments (+0.981 and −1.253) are **log-likelihood ratios**: they encode how much more likely this vote is if the code is actually good versus actually bad, given a model of agent accuracy (80% correct APPROVE rate on good code, 70% correct REJECT rate on bad code). REJECT moves Λ slightly more per unit weight than APPROVE — reflecting that a REJECT on good code is rarer than an APPROVE on bad code.

### Stopping boundaries

Two boundaries are fixed at design time, derived from acceptable error rates (5% false positive, 10% false negative):

- Λ ≥ **+2.890** → **APPROVE [HIGH]** — stop immediately
- Λ ≤ **−2.251** → **REJECT [HIGH]** — stop immediately

These bound the error rates at 5% and 10% **under the model's assumptions** — that votes are independent, and that agents approve good code 80% of the time and bad code 30% of the time. The mathematics is Wald's and is not in doubt; the assumptions are the weak point. Measured on the labelled corpus, the original personas separated good from bad code about three times less sharply than assumed, and votes are not independent — copies of one persona agree with each other even more than different personas do (see *What the numbers say so far*).

**[HIGH]** means the SPRT fired. **[MEDIUM]** and **[LOW]** mean the agent pool ran out before either boundary was crossed — the decision came from weighted synthesis instead (see next section).

### Ordering for efficiency

Agents with higher weights go first. This maximises the chance of crossing a boundary early and not querying the remaining agents. A unanimous three-agent pool at uniform weights (ω=0.5) never reaches the REJECT boundary (maximum achievable |Λ| ≈ 1.88 < 2.25) — which was the argument for growing the pool to five. With five agents at uniform weights, four agreeing REJECTs cross it (4 × 0.5 × 1.253 = 2.51); once the leading agents' weights average 0.60, three are enough. APPROVE is harder by design: it takes all five agents approving *and* weights averaging 0.59, so on a fresh install (five approvals at ω=0.5 add up to 2.45 < 2.89) `APPROVE [HIGH]` cannot occur at all.

### Weighted synthesis (fallback)

When the pool is exhausted without a boundary crossing, WaRF computes:

```
score = Σ(ω_i × vote_i) / Σ(ω_i)
```

This is a weighted average of votes (±1). The score is compared to a domain threshold θ:

- score ≥ θ → APPROVE
- score < θ → REJECT
- |score − θ| ≥ 0.2 → MEDIUM confidence
- |score − θ| < 0.2 → LOW confidence

---

## Agent weights and calibration

### The Beta prior

Each agent carries a **Beta distribution** for each review domain (LOGIC, SECURITY, PERFORMANCE). A Beta distribution is parameterised by two numbers: α (alpha) and β (beta). Think of them as accumulated counts:

- α ≈ number of correct calls
- β ≈ number of wrong calls

The agent's effective weight is ω = α / (α + β).

Fresh agents start at α=1, β=1, ω=0.5. This is the **uninformative prior** — "we have seen one correct call and one wrong call, so we know nothing yet." Every oracle update moves these numbers.

### Oracle updates

When you provide a ground-truth verdict — `warf label <session-id> --verdict REJECT` once a human has decided, or `--ground-truth` at review time — WaRF updates each agent's weight for the domain under review:

- Agent voted correctly → α += γ (success count increases)
- Agent voted incorrectly → β += γ (failure count increases)

γ is the oracle's **confidence tier**:

| Oracle | γ | When to use |
|---|---|---|
| DEVELOPER | 1.0 | You read the code and are certain |
| SAST | 0.7 | A static analysis tool confirmed the finding |
| TEST | 0.3 | A test suite caught it, but tests can be incomplete |
| COMPILER | 0.1 | The compiler flagged it — high precision, narrow scope |

A SAST oracle teaches less aggressively than a DEVELOPER because the tool's verdict, while automated, covers a narrower class of defects and may produce false positives of its own.

### What calibration looks like in practice

After 62 labelled reviews (psf/requests, urllib3, the G+Smo C++ library and a synthetic validation suite), AUDITOR leads in LOGIC with ω=0.77, ADVOCATE follows at 0.69 and BOUNDARY at 0.59, while SKEPTIC (0.46) and TEST-FOCUSED (0.32) trail — both accumulated false alarms on clean production code. In SECURITY the picture is flatter and the ranking different: AUDITOR, ADVOCATE and SKEPTIC sit together at about 0.60, TEST-FOCUSED at 0.52, BOUNDARY at 0.47. AUDITOR and ADVOCATE lost their lead there by approving code that contained real defects. (Profile snapshot of 13 August 2026.)

The same framework, the same agents, the same code — different domain weights because the evidence in each domain is different. This is calibration working as designed.

### Temporal decay

Weights accumulated six months ago are less relevant than weights from last week. WaRF applies exponential decay (λ=0.95 per week) to effective observation counts when computing the weight for a new review. An agent that was accurate three months ago and has not been reviewed since will have its weight pulled back toward 0.5 — the system acknowledges that accuracy may not have been stable.

---

## What "APPROVE [MEDIUM]" actually means

The full output label has three parts: a domain, a decision, and a confidence level.

**Domain** is either explicit (`--domain SECURITY`) or auto-detected from file path and content. The domain sets the threshold θ used in synthesis and determines which set of per-agent weights applies.

**Decision** is APPROVE or REJECT.

**Confidence** has three levels:

| Level | Meaning |
|---|---|
| **HIGH** | SPRT boundary crossed — statistically controlled stop with bounded error rates |
| **MEDIUM** | Pool exhausted; weighted synthesis score was far from θ (margin ≥ 0.2) |
| **LOW** | Pool exhausted; weighted synthesis score was close to θ (margin < 0.2) |

**LOW confidence is informative, not a failure.** On mature, well-tested production code where agents find nothing obviously wrong, you expect LOW confidence on APPROVE. The agents are not lying — they genuinely have weak signal. Treating LOW-confidence APPROVE the same as HIGH-confidence APPROVE would be wrong; the confidence level exists precisely to flag this distinction.

**SECURITY reviews are systematically harder to APPROVE.** Because θ=+0.2 in SECURITY, a balanced 2-to-1 vote for APPROVE produces a score of roughly +0.16 — which is below θ and therefore a REJECT verdict at LOW confidence. The security domain is designed to require a stronger signal before granting APPROVE. This matches the asymmetric cost of security errors: a missed vulnerability is almost always more expensive than a false alarm.

---

## Early results: the first labelled reviews (psf/requests, June–July 2026)

*This section is history: three agents, 15 labelled sessions on 12 files, 9 of the 15 verdicts correct. It is kept because the cases are instructive. Current numbers follow further down.*

WaRF was first validated on the `requests` library — a mature, actively maintained Python HTTP library with high test coverage and multiple security-conscious maintainers. This is a hard case: there are few obvious bugs, and most code is correct.

### What WaRF got right

**`cookies.py` — genuine bug in shipping code**

`MockResponse.getheaders()` is annotated `-> Any` but contains no `return` statement — it always returns `None`. Both SKEPTIC and AUDITOR independently identified the same line without seeing each other's reasoning. WaRF returned REJECT [MEDIUM]. This is the **strongest type of WaRF signal**: independent convergence on the same specific line, with no coordination.

**Five APPROVE verdicts on clean production code**

`auth.py`, `adapters.py`, `api.py`, `models.py`, `structures.py` all received APPROVE at MEDIUM or LOW confidence. The low confidence on good code is correct — WaRF does not over-trust its own APPROVE verdicts. (A sixth clean file, `hooks.py`, was wrongly rejected at MEDIUM — it returns in the debate section.)

### What WaRF got wrong, and why

**`utils.py` — missed CVE-2024-47081 (no agent saw it)**

This file contained a published credential-leak vulnerability:

```python
# Vulnerable — looks plausible, misuses the API:
host = ri.netloc.split(splitstr)[0]

# Fixed:
host = ri.hostname
```

"Everything before the first colon is the host" looks like ordinary port-stripping. But a netloc may carry userinfo in front of an `@`: for `http://example.com:@evil.com/` the request goes to `evil.com`, while the split yields `example.com` — so the `.netrc` credentials stored for example.com are sent to evil.com. ADVOCATE and AUDITOR both looked at this function and praised it (*"safely handles credential files"*); SKEPTIC rejected the file, but for unrelated reasons, and never mentions the function. Verdict: APPROVE [MEDIUM], wrong. This is a **Type 2 failure**: knowledge gap, not attitudinal bias. Adding more agents with the same training would have produced the same wrong answer with higher confidence.

**`sessions.py` — correct agent outvoted (two agents wrong)**

The file contained logic to strip `Authorization` headers on cross-host redirects. SKEPTIC correctly identified an incomplete threat model (the stripping missed certain redirect chains). ADVOCATE and AUDITOR evaluated the explicit code path and judged it correct. The ensemble outvoted the correct agent: APPROVE [LOW], wrong.

After the oracle update, SKEPTIC's SECURITY weight increased. Three weeks later the same file went through the debate round: SKEPTIC pointed at the exact comparison, the other two checked it and changed their votes — a unanimous REJECT (see *The debate round*).

---

## The failure modes

| Type | What happens | Example | Fix |
|---|---|---|---|
| **Type 1 — Persona bias** | A systematic attitude causes an agent to rationalise a known defect | `cookies.py` — ADVOCATE saw the missing return and wrote that it *"appears intentional"* | TEST-FOCUSED and BOUNDARY personas, added July 2026 |
| **Type 2 — Knowledge gap** | All agents lack the same domain-specific knowledge; correct answer is not in the pool | CVE-2024-47081 — userinfo in a URL's netloc, unknown to all agents | SAST oracle (Bandit is available via `--sast`); RAG on CVE databases |
| **Type 2b — Incomplete threat model** | Agents evaluate the visible code correctly but miss a broader attack surface; correct minority is outvoted | `sessions.py` — SKEPTIC found the gap, ADVOCATE and AUDITOR did not look for it | Higher SKEPTIC weight in SECURITY (self-corrects over time); debate round |
| **Type 3 — False consensus** | In the debate round a plausible but wrong argument persuades the agents who were right; the result is a wrong verdict at HIGH confidence | `_internal_utils.py` — AUDITOR and ADVOCATE correctly approved, then switched after a "no input validation" argument that does not apply to an internal helper | None yet. Use debate sparingly and treat a post-debate HIGH with more caution than a first-round one |

Type 2 is the most honest limitation: **WaRF cannot detect vulnerabilities that require knowledge not present in the agents' training.** It will signal honest uncertainty (LOW confidence), but it will not fabricate knowledge it does not have.

---

## The debate round

When SPRT does not fire and the pool is exhausted, a second round can be triggered with `--debate`. The hypothesis: if one agent has the correct analysis and the others are wrong, showing each agent the others' reasoning before asking again may allow the correct view to propagate.

In Round 2, each agent receives:
- The same code
- Every other agent's Round-1 vote and reasoning
- Its **own** Round-1 vote, explicitly stated as an anchor
- An instruction to maintain its position unless the other agents have identified a genuine technical error in its reasoning — not merely because they disagree

Round 2 runs its own SPRT from Λ=0. Weights are frozen at Round-1 values (no re-calibration mid-session).

**What it does:** surfaces knowledge that exists in the pool but was not dominant in Round 1. On the pre-fix `sessions.py`, SKEPTIC pointed at the hostname-only comparison in `rebuild_auth()`; AUDITOR and ADVOCATE checked it and both changed to REJECT. (The unanimous verdict still came out at MEDIUM: three agents at those weights cannot reach the boundary.)

**What it does not do:** fix a knowledge gap that all agents share. If the correct answer is not in the pool, deliberation will not produce it — SKEPTIC persisted in a misconception about `isinstance(x, collections.abc.Callable)` even after AUDITOR and ADVOCATE correctly explained the issue.

**What it can do wrong:** manufacture confidence. On `_internal_utils.py` — clean code — AUDITOR and ADVOCATE approved in Round 1. In Round 2 the three rejecting agents argued that `to_native_string()` has no input validation; true as a generic pattern, irrelevant for an internal helper whose callers always pass `str` or `bytes`. AUDITOR wrote that the others *"have identified genuine technical vulnerabilities that I initially overlooked"* and switched, ADVOCATE followed, and the boundary was crossed: REJECT [HIGH], wrong. A correct MEDIUM became an incorrect HIGH. Persuasion is not correctness.

**When it adds zero value:** if no votes change, Round-2 Λ = Round-1 Λ exactly. The debate confirmed the existing verdict at extra token cost. Zero change is not an error; it means the pool's positions are stable.

**Prompt framing is not cosmetic.** An early version of the debate prompt asked *"do you revise your position?"* — a conformity nudge that caused the correct minority agent to capitulate to the majority after seeing two opposing REJECT votes. The current prompt anchors each agent to its own prior vote and explicitly asks it to explain what is wrong in the other agents' reasoning if it maintains its position. The framing change reversed the behaviour.

**The record so far.** Six logged sessions carry a debate round. Judged against the corpus label for each file:

| Session | File | Round 1 | After debate | Truth | Effect |
|---|---|---|---|---|---|
| #31, 21 Jul | `sessions_pre_auth_strip.py` | wrong lean (APPROVE, 2:1) | REJECT, MEDIUM | REJECT | helped |
| #48, 25 Jul | `help.py` | wrong lean (APPROVE, 2:1) | REJECT, HIGH | REJECT | helped |
| #30, 21 Jul | `hooks.py` | correct (APPROVE, 2:1) | unchanged, MEDIUM | APPROVE | no effect |
| #29, 6 Jul | `hooks.py` | split, correct voice present | REJECT, HIGH | APPROVE | made wrong |
| #49, 25 Jul | `_internal_utils.py` | correct (APPROVE, 2:1) | REJECT, HIGH | APPROVE | made wrong |
| #50, 27 Jul | `_internal_utils.py` | correct (APPROVE, 2:1) | REJECT, HIGH | APPROVE | made wrong |

Two helped, one did nothing, three made a verdict wrong, and all three of those ended at HIGH. Six sessions is far too few to call a rate, and session #29 is the one run with the early "do you revise?" wording described above. The honest reading is that debate is an experiment worth running on reviews that are already inconclusive, not a safeguard, and that a HIGH after debate deserves more suspicion than a first-round HIGH. The session numbers are the dashboard's `#N`.

---

## What the numbers say so far

All of this is preliminary: one labelled corpus, small samples.

**Does the confidence label mean anything?** On the 62 labelled reviews, LOW verdicts were correct 27% of the time (4 of 15), MEDIUM 63% (22 of 35) and HIGH 75% (9 of 12). The ordering is what one hopes for — and LOW being worse than a coin flip is why a LOW verdict should never be acted on. Two caveats. The same reviews that taught the weights are the ones being scored. And the HIGH labels were earned under vote probabilities that were assumed, not measured; measured on this corpus, the original personas discriminated about three times less sharply than assumed.

**Is a mixed panel better than five copies of one reviewer?** Tested on a set of 12 labelled files (5 clean, 7 with a defect), every agent voting on every file, all weights starting equal: the mixed panel got 11 of 12 right, five AUDITORs 10 of 12, five SKEPTICs 10 of 12. On accuracy that is a tie. What differs is *how* each pool was wrong — each failed in the direction of its own bias. The mixed panel approved one file with a subtle real bug, at MEDIUM confidence. The five AUDITORs approved that same file unanimously. The five SKEPTICs caught it, but unanimously rejected a clean file at HIGH confidence — and in the mixed panel the very same SKEPTIC rejected that very same file and was outvoted. The mixed panel produced no wrong HIGH verdict; the cloned pools did. Copies of one persona agree with each other more than different personas do, and the SPRT reads agreement as evidence, so a cloned pool is wrong *confidently* — which is the worst case described under *The problem*, observed. Cloning one persona is a bet on that persona, and which persona deserves the bet is not knowable in advance: AUDITOR alone is right in 90% of its LOGIC reviews on the corpus and in 55% of its SECURITY reviews.

---

## What WaRF is not

- **Not a SAST tool.** It does not parse ASTs, run symbolic execution, or trace taint flows. It reads code the way a reviewer reads code.
- **Not a replacement for tests.** It reviews logic; it does not execute anything.
- **Not a magic correctness oracle.** It is a reliability framework: it tells you how much to trust the ensemble verdict, and it gets better at that trust estimate over time.
- **Not a black box.** Every vote, weight, reasoning excerpt, and SPRT trace is logged to `sessions.jsonl`. Every decision is auditable.
- **Not finished.** The five-agent pool, the calibration diagram and a first SAST integration (Bandit as a fixed-weight vote, `--sast`) exist. Open: an evaluation corpus that is independent of the one the weights were learned on; more domains and personas; SPRT constants measured rather than assumed; and whether the oracle should reward the *reasoning* and not only the vote — today an agent that rejects bad code for the wrong reason is credited all the same.

---

## Quick start

```bash
pip install .                 # from a checkout; `pip install ".[anthropic]"` for the API provider
warf init                     # data directory + a first profile
warf providers                # which model backend will answer (Claude CLI, Anthropic API, OpenAI-compatible, Ollama)

# Review a file (auto-detects domain)
warf review path/to/file.py

# Review with an explicit domain
warf review path/to/file.py --domain SECURITY

# Teach it: once a human has decided, label the session (id is in the review output)
warf label <session-id> --verdict REJECT

# Enable debate round
warf review path/to/file.py --debate

# Show current agent weights
warf weights
```

If `warf` is not on your PATH, `python -m warf` (or `py -m warf` on Windows) is equivalent.

See `README.md` for installation, providers and where state lives, `warf/policy.md` for how to read a verdict, and `SPECIFICATION.md` for the formal mathematical treatment.
