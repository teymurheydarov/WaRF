# WaRF — Weighted n-Agent Reliability Framework
## Architectural Specification v0.4

> **Status:** Draft · **Authors:** Principal Systems Architect  
> **Target venue:** SoCraTes Austria, September 2026  
> **Scope:** Mathematical models, lifecycle, and data structures only. No implementation.  
> **Implementation note (2026-09-26):** the code names the third confidence level `LOW`, where this document says `LOW_CONFIDENCE`. The SPRT boundaries and per-vote log-likelihood ratios (§3.2), the pool-exhausted fallback and its 0.2 margin (§3.2.5) and the Beta(1, 1) prior (§2.3) were checked against `warf/engine.py` and match.  
> **Changelog v0.4:** Added §3.3 Iterative Debate Round; updated §4.2 ReviewSession schema with debate fields; added invariants I-12 through I-14; updated §5 session lifecycle diagram with debate branch.  
> **Changelog v0.3:** Corrected SPRT upper boundary A (2.944 → 2.890); fixed §3.2.5 pool-exhausted confidence wording; added §3.2.7 pool-size constraint on SPRT early stopping; updated §7.4 and added §7.6 with live validation run results.  
> **Changelog v0.2:** Added deterministic orchestration invariant; oracle confidence tiers with fractional updates; vote independence caveat; single-best-agent baseline criterion; developer as primary oracle; §7 Validation Protocol.

---

## Table of Contents

1. [Motivation & Design Philosophy](#1-motivation--design-philosophy)
2. [Mathematical Framework](#2-mathematical-framework)
   - 2.1 [The Synthesis Function](#21-the-synthesis-function)
   - 2.2 [Domain Specialization](#22-domain-specialization)
   - 2.3 [Dynamic Weighting — Backpropagation of Trust](#23-dynamic-weighting--backpropagation-of-trust)
3. [Advanced Mitigation Strategies](#3-advanced-mitigation-strategies)
   - 3.1 [Diversity Injection](#31-diversity-injection)
   - 3.2 [Cost-Optimization via Sequential Analysis (SPRT)](#32-cost-optimization-via-sequential-analysis-sprt)
   - 3.3 [Iterative Debate Round](#33-iterative-debate-round)
4. [Data Schema Specifications](#4-data-schema-specifications)
   - 4.1 [AgentProfile](#41-agentprofile)
   - 4.2 [ReviewSession](#42-reviewsession)
5. [Session Lifecycle](#5-session-lifecycle)
6. [Invariants & Boundary Conditions](#6-invariants--boundary-conditions)
7. [Validation Protocol](#7-validation-protocol)

---

## 1. Motivation & Design Philosophy

Classical majority voting assumes all agents are equally reliable — an assumption that breaks immediately when agents share the same underlying model, the same training distribution, or the same systemic blind spots. This is the **Common-Mode Failure** problem in fault-tolerant computing, studied extensively in safety-critical systems (aviation, nuclear control).

WaRF draws from two traditions:

| Source | Contribution |
|---|---|
| N.P. Redkin — Control Theory | Treating LLM agents as potentially faulty logic gates in a redundant circuit |
| Bayesian Reliability Engineering | Maintaining a probabilistic belief over each agent's domain-specific competence and updating it from deterministic ground-truth signals |

### Core Design Principles

**1. The oracle hierarchy.** The feedback loop that makes WaRF intelligent depends entirely on the quality of its ground-truth signals. Oracles are ranked by reliability (see §2.3.2). The primary oracle is always the **developer** — the human who owns the code and makes the final judgment. Automated tools serve as lower-tier oracles that fire quickly but carry partial trust.

**2. The deterministic orchestration layer.** WaRF's orchestration — the synthesis function, weight updates, SPRT stopping logic — is executed by **deterministic code, not by an LLM**. LLM agents contribute only their binary votes $x_i$. Everything above that is pure mathematics. This is non-negotiable: an orchestration layer that can hallucinate is not a reliability framework.

**3. The single-best-agent baseline.** WaRF is justified only if its ensemble decision $D$ measurably outperforms the single highest-weighted agent in the pool on a held-out validation set. If it does not, the correct action is to route directly to that agent and save the overhead. This baseline must be evaluated before any production deployment.

---

## 2. Mathematical Framework

### 2.1 The Synthesis Function

The framework reduces a multi-agent review to a scalar decision $D$ via a **weighted threshold vote**:

$$\boxed{D = \operatorname{sign}\!\left(\sum_{i=1}^{n} \omega_{i,d} \cdot x_i \;-\; \theta\right)}$$

**Variable definitions:**

| Symbol | Domain | Semantics |
|---|---|---|
| $x_i$ | $\{-1,\, +1\}$ | Agent $i$'s vote: $-1$ = REJECT, $+1$ = APPROVE |
| $\omega_{i,d}$ | $[0,\, 1]$ | Agent $i$'s trust weight in evaluation domain $d$ |
| $d$ | $\{\texttt{LOGIC},\,\texttt{SECURITY},\,\texttt{PERFORMANCE}\}$ | Active evaluation domain |
| $\theta$ | $(-1,\, +1)$ | Decision threshold (see §2.1.1) |
| $D$ | $\{-1,\, 0,\, +1\}$ | Final decision: REJECT / DEADLOCK / APPROVE |

**Output semantics:**

$$D = \begin{cases} +1 & \text{APPROVE — weighted evidence favours correctness} \\ -1 & \text{REJECT — weighted evidence identifies a defect} \\ 0 & \text{DEADLOCK — insufficient consensus; escalate or extend pool} \end{cases}$$

#### 2.1.1 Threshold $\theta$

The threshold $\theta$ is not fixed. It is a **risk-calibrated parameter** set per domain before a session begins:

$$\theta_d \in (-1,\, +1)$$

- $\theta_d > 0$: Approval requires stronger positive consensus. Use for `SECURITY` — bias toward caution.
- $\theta_d = 0$: Symmetric. Use for `LOGIC` — no prior bias.
- $\theta_d < 0$: Approval is easier. Use for `PERFORMANCE` — accept suboptimal code rather than block shipping.

Recommended defaults:

| Domain | $\theta_d$ | Rationale |
|---|---|---|
| `LOGIC` | $0.0$ | Neutral; correctness has clear ground truth |
| `SECURITY` | $+0.2$ | Prudent bias toward rejection on ambiguous evidence |
| `PERFORMANCE` | $-0.1$ | Slight approval bias; regressions are tolerable if minor |

#### 2.1.2 Normalisation

Because $\omega_{i,d} \in [0,1]$, the raw sum $\sum_i \omega_{i,d} \cdot x_i$ lies in $[-W_d,\, +W_d]$ where $W_d = \sum_i \omega_{i,d}$. To keep $\theta$ interpretable as a fraction of total weight, normalise:

$$D = \operatorname{sign}\!\left(\frac{\sum_{i=1}^{n} \omega_{i,d} \cdot x_i}{\sum_{i=1}^{n} \omega_{i,d}} \;-\; \theta_d\right)$$

This ensures $\theta_d$ is always comparable across sessions regardless of pool size.

---

### 2.2 Domain Specialization

Each `ReviewSession` operates in exactly one domain. The domain determines which weight column is active, which ground-truth oracle is credible, and which $\theta_d$ applies.

#### Domain Registry

| Domain ID | Evaluation Focus | Credible Ground-Truth Oracles |
|---|---|---|
| `LOGIC` | Correctness, algorithmic soundness, edge-case handling, type safety | Developer judgment, test suite pass/fail, compiler exit code, formal proof checker |
| `SECURITY` | Injection vectors, authentication flaws, secrets in code, unsafe deserialization, dependency CVEs | Developer judgment, SAST tool (Semgrep, CodeQL), CVE database match, penetration test result |
| `PERFORMANCE` | Algorithmic complexity, N+1 queries, unnecessary allocations, blocking calls in async contexts | Developer judgment, benchmark regression ($\Delta > \epsilon$), profiler hotspot, query EXPLAIN plan |

**Principle:** An agent may be expert in `LOGIC` and naive in `SECURITY`. WaRF maintains three independent weight coefficients per agent — one per domain — and never conflates them.

---

### 2.3 Dynamic Weighting — Backpropagation of Trust

#### 2.3.1 Belief Model

Agent $i$'s reliability in domain $d$ is modelled as a Bernoulli random variable with unknown success probability $p_{i,d}$. We place a **Beta prior**:

$$p_{i,d} \;\sim\; \mathrm{Beta}(\alpha_{i,d},\, \beta_{i,d})$$

The Beta distribution is the conjugate prior to the Bernoulli likelihood, making the update exact and closed-form. Parameters are initialised at session zero as:

$$\alpha_{i,d}^{(0)} = \beta_{i,d}^{(0)} = 1 \qquad \text{(uniform prior — maximum ignorance)}$$

The **operational weight** at any point in time is the posterior mean:

$$\omega_{i,d} = \mathbb{E}[p_{i,d}] = \frac{\alpha_{i,d}}{\alpha_{i,d} + \beta_{i,d}}$$

At initialisation this yields $\omega_{i,d}^{(0)} = 0.5$ for all agents, encoding "we know nothing yet."

#### 2.3.2 Oracle Confidence Tiers

Not all oracles are equally trustworthy. The update magnitude is scaled by the oracle's **confidence weight** $\gamma_t \in (0, 1]$, which reflects how reliably that oracle captures true code quality:

| Tier | Oracle Type | $\gamma_t$ | Rationale |
|---|---|---|---|
| 1 | Developer explicit judgment | $1.0$ | Highest reliability; human who owns the code confirms or overrules |
| 2 | SAST tool (Semgrep, CodeQL) | $0.7$ | Deterministic for known patterns; misses novel or context-dependent issues |
| 3 | Test suite pass/fail | $0.3$ | Validates only what tests cover; silent on untested behaviour |
| 4 | Compiler / type checker | $0.1$ | Validates syntax and types only; says nothing about logic correctness |

The developer (Tier 1) is the primary oracle. Automated tools (Tiers 2–4) fire synchronously and supplement the signal but do not replace it.

#### 2.3.3 Bayesian Update Rule

When an oracle of tier $t$ provides ground truth $x^* \in \{-1, +1\}$ for a session where agent $i$ cast vote $x_i$:

$$\text{Define correctness indicator:} \quad c_{i,d} = \mathbf{1}\!\left[x_i = x^*\right]$$

$$\alpha_{i,d} \;\leftarrow\; \alpha_{i,d} + \gamma_t \cdot c_{i,d}$$

$$\beta_{i,d} \;\leftarrow\; \beta_{i,d} + \gamma_t \cdot (1 - c_{i,d})$$

A **correct** vote increases $\alpha$ by $\gamma_t$; an **incorrect** vote increases $\beta$ by $\gamma_t$. A full Tier 1 update shifts weights strongly; a Tier 4 compiler signal barely moves them. When multiple oracles fire for the same session, apply each update independently in tier order (highest first).

**Worked example** — agent starts at $\alpha=1, \beta=1$ ($\omega = 0.5$), over three sessions:

| Session | Oracle Tier | $\gamma_t$ | Correct? | $\alpha$ | $\beta$ | $\omega_{i,d}$ |
|---|---|---|---|---|---|---|
| Initial | — | — | — | 1.0 | 1.0 | 0.500 |
| 1 | Developer (T1) | 1.0 | ✓ | 2.0 | 1.0 | 0.667 |
| 2 | SAST (T2) | 0.7 | ✗ | 2.0 | 1.7 | 0.541 |
| 3 | Test suite (T3) | 0.3 | ✓ | 2.3 | 1.7 | 0.575 |

#### 2.3.4 Recency Weighting (Exponential Decay Variant)

Pure Bayesian accumulation treats all historical votes equally. For long-lived agents, apply **exponential temporal decay** to the effective observation counts before each session:

$$\alpha_{i,d}^{\mathrm{eff}} = 1 + (\alpha_{i,d} - 1) \cdot \lambda^{\Delta t}$$

$$\beta_{i,d}^{\mathrm{eff}} = 1 + (\beta_{i,d} - 1) \cdot \lambda^{\Delta t}$$

where $\lambda \in (0, 1)$ is the decay factor (recommended: $\lambda = 0.95$ per week) and $\Delta t$ is elapsed time in weeks since the last observation. The subtraction of 1 preserves the uninformative prior floor — the effective counts never fall below the prior.

Operational weight then uses effective counts:

$$\omega_{i,d} = \frac{\alpha_{i,d}^{\mathrm{eff}}}{\alpha_{i,d}^{\mathrm{eff}} + \beta_{i,d}^{\mathrm{eff}}}$$

#### 2.3.5 Uncertainty Bound

The Beta posterior also provides a **credible interval** for $\omega_{i,d}$, useful for detecting under-observed agents:

$$\mathrm{CI}_{95\%}(p_{i,d}) = \mathrm{Beta\text{-}CDF}^{-1}\!\left([0.025,\, 0.975]\;\middle|\;\alpha_{i,d}, \beta_{i,d}\right)$$

An agent whose 95% credible interval width exceeds $\delta = 0.4$ is flagged as **under-calibrated** and excluded from synthesis until it accumulates more observations. Concretely: $\alpha + \beta < 7$ triggers this flag.

---

## 3. Advanced Mitigation Strategies

### 3.1 Diversity Injection

#### 3.1.1 The Common-Mode Failure Problem

If all $n$ agents are identical (same model, same temperature, same system prompt), they do not constitute $n$ independent fault domains — they constitute **one fault domain sampled $n$ times**. Correlated failures are invisible to majority voting and to WaRF's synthesis function.

Two failure modes are defined:

| Mode | Definition | Example |
|---|---|---|
| **Common-Mode Failure (CMF)** | Systematic error shared across agents due to identical training data or prompt structure | All agents miss the same SQL injection pattern because the training corpus normalised it |
| **Collusive Hallucination (CH)** | Mutually reinforcing confident errors where agents agree on a plausible but wrong answer | Three agents unanimously approve an off-by-one in a boundary check because the logic "reads well" |

> **Known limitation:** Diversity injection addresses *reasoning path* diversity and *epistemic stance* diversity. It does not address *training data* diversity. All major LLMs (Claude, GPT, Gemini) are trained on largely overlapping internet corpora. A systematic blind spot shared across pretraining datasets — e.g. a class of vulnerability that is rarely discussed publicly — will not be resolved by persona or temperature variance. The 95% credible intervals on $\omega_{i,d}$ are therefore optimistic bounds in the presence of shared training blind spots, not strict guarantees. This limitation is structural and acknowledged explicitly.

#### 3.1.2 Diversity Axes

Diversity must be injected along at least two independent axes:

**Axis 1 — Model Heterogeneity**

The agent pool must include models from at least two distinct model families. Diversity is measured by the pairwise **disagreement rate** $\rho_{ij}$ observed across historical sessions:

$$\rho_{ij} = P(x_i \neq x_j)$$

Pool composition requirement: $\min_{i \neq j}\, \rho_{ij} \;\geq\; 0.15$

If any pair of agents disagrees less than 15% of the time, they are considered **correlated clones** and the pool operator must substitute one of them.

**Axis 2 — Epistemic Stance Variance**

Each agent in the pool is assigned a distinct **epistemic persona** at prompt construction time. The three required personas are:

| Persona | Prompt Directive | Purpose |
|---|---|---|
| `SKEPTIC` | "Assume this code contains at least one defect. Find it." | Adversarial; breaks confirmation bias |
| `ADVOCATE` | "Assume this code is correct. Defend it." | Stress-tests SKEPTIC findings |
| `AUDITOR` | "Evaluate this code as if you are a compliance officer with no prior context." | Domain-neutral; catches systemic issues |

For $n > 3$, additional agents receive temperature-varied `SKEPTIC` instances ($T \in \{0.2, 0.7, 1.2\}$) to sample different regions of the model's output distribution.

**Axis 3 — Prompt Structure Variance** (recommended for $n \geq 5$)

Rotate the framing of the code under review:
- Agent A receives the raw diff
- Agent B receives the diff with surrounding file context
- Agent C receives only the function signature and its docstring (black-box review)

This prevents agents from sharing reasoning anchors that could induce CMF.

---

### 3.2 Cost-Optimization via Sequential Analysis (SPRT)

#### 3.2.1 Motivation

Invoking all $n$ agents for every review session is token-inefficient. When the first agents unanimously and confidently reject a piece of code with a critical defect, invoking the remaining agents adds cost but not information. Wald's **Sequential Probability Ratio Test (SPRT)** provides a statistically principled stopping criterion.

#### 3.2.2 Hypothesis Formulation

Define two competing hypotheses about the code under review:

$$H_0 : \text{The code is defective} \quad\text{(REJECT)}$$
$$H_1 : \text{The code is acceptable} \quad\text{(APPROVE)}$$

Let $p_1$ be the probability that an agent votes APPROVE ($x_i = +1$) given the code is genuinely acceptable, and $p_0$ be the same probability given the code is genuinely defective. We require $p_1 > p_0$.

Recommended starting values (treat as tuning knobs, calibrate empirically via the validation protocol in §7):

| Parameter | Starting Value | Meaning |
|---|---|---|
| $p_1$ | $0.80$ | An agent approves clean code 80% of the time |
| $p_0$ | $0.30$ | An agent approves defective code 30% of the time |

> **Note:** Wrong $p_0$/$p_1$ values do not produce wrong decisions — they produce inefficient stopping (too early or too late). Decision quality degrades gracefully; correctness does not break. Treat these as performance-tuning parameters, not correctness parameters.

#### 3.2.3 The Log-Likelihood Ratio Statistic

After $k$ agents have been queried, compute the cumulative **weighted log-likelihood ratio**:

$$\Lambda_k = \sum_{j=1}^{k} \omega_{j,d} \cdot \ell(x_j)$$

where the per-vote log-likelihood ratio is:

$$\ell(x_j) = \begin{cases} \log\dfrac{p_1}{p_0} & \text{if } x_j = +1 \text{ (APPROVE vote)} \\[8pt] \log\dfrac{1 - p_1}{1 - p_0} & \text{if } x_j = -1 \text{ (REJECT vote)} \end{cases}$$

Note that $\log\frac{p_1}{p_0} > 0$ (APPROVE evidence favours $H_1$) and $\log\frac{1-p_1}{1-p_0} < 0$ (REJECT evidence favours $H_0$).

#### 3.2.4 Stopping Boundaries

Fix the error tolerances:

| Parameter | Symbol | Recommended Value | Meaning |
|---|---|---|---|
| Type I error (false approval) | $\alpha$ | $0.05$ | Accept defective code at most 5% of the time |
| Type II error (false rejection) | $\beta$ | $0.10$ | Reject acceptable code at most 10% of the time |

Wald's boundaries are:

$$A = \log\frac{1 - \beta}{\alpha} = \log\frac{0.90}{0.05} = \log 18 \approx 2.890$$

$$B = \log\frac{\beta}{1 - \alpha} = \log\frac{0.10}{0.95} \approx -2.251$$

#### 3.2.5 Stopping Rule

After each agent responds, evaluate:

$$\begin{cases} \Lambda_k \;\geq\; A & \Rightarrow \text{Stop. } D = +1 \text{ (APPROVE)} \\ \Lambda_k \;\leq\; B & \Rightarrow \text{Stop. } D = -1 \text{ (REJECT)} \\ B < \Lambda_k < A & \Rightarrow \text{Continue. Query agent } k+1 \end{cases}$$

If $k = n$ (pool exhausted) and the statistic remains in the continuation region, fall back to the synthesis function $D$ from §2.1 and assign confidence per §4.2: `MEDIUM` if $\lvert\text{normalised\_sum} - \theta_d\rvert \geq 0.2$, `LOW_CONFIDENCE` otherwise.

#### 3.2.6 SPRT in the Context of Agent Weights

The weight $\omega_{j,d}$ scales the contribution of each agent's evidence. A high-weight agent's APPROVE vote moves $\Lambda_k$ substantially toward $A$; a low-weight agent's vote barely moves the statistic. This means a single trusted expert agent can terminate the test early, while a pool of under-calibrated agents must all agree before the boundary is crossed — a structurally correct behaviour.

#### 3.2.7 Pool-Size Constraint on Early Stopping

SPRT's cost-saving benefit — stopping before all agents are queried — requires the pool to be large enough that the cumulative statistic can reach a boundary before $k = n$.

For a pool of $n$ agents all at weight $\omega$, the maximum reachable $|\Lambda_n|$ (unanimous votes) is:

$$|\Lambda_n|_{\max} = n \cdot \omega \cdot \left|\log\frac{1-p_1}{1-p_0}\right| = n \cdot \omega \cdot 1.253$$

For SPRT to fire at round $k < n$ (early stopping), we need $|\Lambda_k| \geq |B| = 2.251$ after $k$ votes. With $n = 3$ agents at $\omega = 0.5$:

$$|\Lambda_3|_{\max} = 3 \times 0.5 \times 1.253 = 1.879 < 2.251$$

**SPRT cannot fire early with 3 equal-weight agents.** The boundary is only reachable after all 3 have voted, providing no early-stopping saving. This was confirmed in the live validation run (§7.6): SPRT fired exactly once across 7 sessions, and only at $k = n = 3$.

For early stopping to activate at $k = 2$ (saving one agent call), the two heaviest agents must satisfy:

$$(\omega_1 + \omega_2) \cdot 1.253 \geq 2.251 \quad\Rightarrow\quad \omega_1 + \omega_2 \geq 1.797$$

This requires each agent to exceed $\omega = 0.898$ — reachable only after many consistent correct votes. **A pool of $n \geq 5$ agents is recommended for SPRT to provide meaningful cost savings from the start of calibration.**

---

### 3.3 Iterative Debate Round

#### 3.3.1 Motivation

The diversity mechanisms in §3.1 and §3.2 address **attitudinal bias** (persona diversity) and **token cost** (SPRT). They do not address **shared knowledge gaps** — cases where all agents in the pool hold the same incorrect belief. When a majority of agents are wrong for the same reason, neither persona variance nor additional sampling resolves the error; it amplifies it.

Empirically, this failure class was observed in two forms:

| Failure sub-type | Example | Cause |
|---|---|---|
| **Type 2 — Knowledge gap** | `hooks.py`: two agents incorrectly treated `isinstance(x, collections.abc.Callable)` as invalid | All agents share a misconception; even the correct agent cannot influence the others |
| **Type 2b — Incomplete threat model** | `sessions_pre_auth_strip.py`: SKEPTIC correctly found the auth-stripping gap; ADVOCATE and AUDITOR overruled it | Correct minority agent cannot communicate its reasoning to the majority |

The **iterative debate round** addresses both sub-types by providing a structured second pass in which agents are shown all Round 1 votes and reasoning before revising their position. The correct agent's explanation becomes available to all agents before the final decision is made.

> **Design principle:** Agent instructions are deliberately not modified after oracle failures. Teaching agents what they got wrong is prompt engineering. Letting agents correct each other in-session is reliability engineering — it preserves the black-box model while enabling knowledge transfer between rounds.

#### 3.3.2 Trigger Condition

The debate round is **optional** (controlled by a session flag `debate_enabled`) and only activates when Round 1 exhausts the pool without an SPRT early stop:

$$\text{Trigger debate} \iff \text{debate\_enabled} = \text{True} \;\wedge\; B < \Lambda_n^{(1)} < A$$

When SPRT fires early in Round 1 ($\Lambda_k \geq A$ or $\Lambda_k \leq B$), confidence is already `HIGH` — debate is skipped. Debate is only useful in the ambiguous region where the pool disagreed.

#### 3.3.3 Debate Prompt Structure

Each agent $i$ receives a second prompt constructed as follows:

```
[Original system prompt — persona unchanged]

A first round of independent review has been completed.
The votes and reasoning of all agents are shown below.

[For each agent j ≠ i:]
  Agent (j.persona): VOTE: {APPROVE|REJECT}
  Reasoning: {j.rationale from Round 1}

[For agent i itself:]
  Your own Round 1 vote: {APPROVE|REJECT}
  Your own reasoning: {i.rationale from Round 1}

Given the above, do you maintain or revise your vote?
Respond with VOTE: APPROVE or VOTE: REJECT on the first line,
then give your updated reasoning in 3–5 sentences.
```

**Key properties of this prompt:**
- Agent identities (persona names) are revealed — the epistemic stance behind each argument is part of the context.
- Each agent sees its own prior reasoning, enabling genuine revision rather than mere capitulation.
- The instruction to maintain or revise is open — no pressure in either direction.
- The persona system prompt is unchanged — agent $i$'s epistemic prior is preserved.

#### 3.3.4 Round 2 SPRT and Synthesis

Round 2 runs the same SPRT procedure as Round 1, with the **same weights** (weights are not updated mid-session) and a **fresh accumulator** ($\Lambda^{(2)}_0 = 0$):

$$\Lambda^{(2)}_k = \sum_{j=1}^{k} \omega_{j,d} \cdot \ell(x_j^{(2)})$$

The same boundaries $A$ and $B$ apply. If SPRT fires in Round 2, confidence is `HIGH`. If the pool exhausts again, weighted synthesis on Round 2 votes produces the final decision with `MEDIUM` or `LOW_CONFIDENCE` per the margin rule.

**Agents are queried in the same order as Round 1** (descending $\omega_{j,d}$). The Round 2 prompt for each agent is constructed after collecting all Round 1 reasoning, so all Round 1 votes are visible to every agent before any Round 2 response is sent.

#### 3.3.5 Oracle Rule and Weight Updates

Oracle updates use **Round 2 votes only**. Round 1 votes are logged for analysis but carry no weight update.

$$c_{i,d}^{\mathrm{final}} = \mathbf{1}\!\left[x_i^{(2)} = x^*\right]$$

$$\alpha_{i,d} \leftarrow \alpha_{i,d} + \gamma_t \cdot c_{i,d}^{\mathrm{final}} \qquad \beta_{i,d} \leftarrow \beta_{i,d} + \gamma_t \cdot (1 - c_{i,d}^{\mathrm{final}})$$

**Corollary:** An agent that held the correct position in Round 1 but capitulated to incorrect peer pressure in Round 2 is penalised. An agent that revised its incorrect Round 1 vote to the correct answer is rewarded. The system measures **final epistemic position**, not process.

This is intentional. The framework has no mechanism to reward "good reasoning" — it can only observe outcomes. An agent that updates for the right reason gets the same reward as one that updates by chance. Over many sessions, the correct agents establish stable weights regardless of how they arrived at correct votes.

#### 3.3.6 Logging

Both rounds are recorded in the `ReviewSession`. The schema extension is defined in §4.2.

| Field | Round 1 | Round 2 |
|---|---|---|
| Votes and reasoning | `votes` list | `debate_votes` list |
| SPRT trace | `sprt_trace` | `debate_sprt_trace` |
| Synthesis result | `synthesis` (used if no debate, or as reference) | `debate_synthesis` (final decision when debate runs) |
| Agents that changed vote | — | `debate_vote_changes` : List of agent IDs |

The `debate_vote_changes` field enables post-hoc analysis of which agents updated and in which direction — essential for validating whether the debate round is resolving knowledge gaps or introducing new errors.

#### 3.3.7 Expected Behaviour on Known Failure Cases

| Case | Round 1 outcome | Expected Round 2 outcome | Mechanism |
|---|---|---|---|
| `hooks.py` (Type 2) | SKEPTIC→REJECT, ADVOCATE→REJECT, AUDITOR→APPROVE | AUDITOR explains `isinstance(x, collections.abc.Callable)` is valid; SKEPTIC and ADVOCATE see the argument and may revise | Correct minority agent educates majority |
| `sessions_pre_auth_strip.py` (Type 2b) | SKEPTIC→REJECT, ADVOCATE→APPROVE, AUDITOR→APPROVE | SKEPTIC explains the scheme/port gap in `rebuild_auth`; ADVOCATE and AUDITOR evaluate the argument | Correct minority agent explains the threat model gap |

If debate does not change the outcome on these cases, the failure is a **Type 2 hard limit** — the knowledge gap cannot be resolved by peer reasoning, and requires external input (SAST, RAG, or domain-specialist agent) to overcome.

---

## 4. Data Schema Specifications

### 4.1 AgentProfile

Represents a persistent identity for a single LLM agent across all sessions.

```
AgentProfile
├── id                  : UUID           — Globally unique agent identifier
├── label               : String         — Human-readable name (e.g., "claude-skeptic-01")
├── model_family        : Enum           — { CLAUDE | GPT | GEMINI | MISTRAL | LOCAL }
├── model_version       : String         — Exact version string (e.g., "claude-sonnet-4-6")
├── persona             : Enum           — { SKEPTIC | ADVOCATE | AUDITOR }
├── temperature         : Float ∈ [0,2]  — Sampling temperature at prompt time
├── prompt_hash         : SHA-256        — Hash of the system prompt; detects silent prompt drift
├── weights
│   ├── LOGIC
│   │   ├── alpha       : Float ≥ 1.0   — Beta distribution success parameter
│   │   └── beta        : Float ≥ 1.0   — Beta distribution failure parameter
│   ├── SECURITY
│   │   ├── alpha       : Float ≥ 1.0
│   │   └── beta        : Float ≥ 1.0
│   └── PERFORMANCE
│       ├── alpha       : Float ≥ 1.0
│       └── beta        : Float ≥ 1.0
├── last_updated        : ISO-8601 UTC   — Timestamp of last weight update
└── calibration_status  : Enum           — { CALIBRATED | UNDER_CALIBRATED | SUSPENDED }
```

**Calibration status rules:**

| Status | Condition | Effect |
|---|---|---|
| `CALIBRATED` | $\alpha_d + \beta_d \geq 7$ for active domain | Participates in synthesis with full weight |
| `UNDER_CALIBRATED` | $\alpha_d + \beta_d < 7$ for active domain | Participates but flagged; vote is logged but excluded from SPRT boundary decisions |
| `SUSPENDED` | $\omega_{i,d} < 0.25$ | Excluded from pool until manual review |

---

### 4.2 ReviewSession

Represents a single, bounded evaluation of one code artefact in one domain.

```
ReviewSession
├── session_id          : UUID              — Globally unique session identifier
├── created_at          : ISO-8601 UTC      — Session start timestamp
├── target
│   ├── artifact_hash   : SHA-256           — Hash of the code snippet or diff under review
│   ├── artifact_type   : Enum              — { DIFF | SNIPPET | FILE | PR }
│   └── context_ref     : String?           — Optional pointer to surrounding file context
├── domain              : Enum              — { LOGIC | SECURITY | PERFORMANCE }
├── threshold           : Float ∈ (-1,1)    — θ_d applied in this session
├── agent_pool          : List<UUID>        — Ordered list of AgentProfile IDs to be queried
├── votes               : List<AgentVote>
│   └── AgentVote
│       ├── agent_id    : UUID              — References AgentProfile.id
│       ├── vote        : Int ∈ {-1,+1}     — x_i: REJECT or APPROVE
│       ├── weight      : Float ∈ [0,1]     — ω_{i,d} at time of vote (snapshot)
│       ├── rationale   : String            — Agent's free-text justification (stored, not used in synthesis)
│       ├── queried_at  : ISO-8601 UTC      — Timestamp of API call
│       └── latency_ms  : Int               — Round-trip time in milliseconds
├── sprt_trace          : List<SPRTStep>
│   └── SPRTStep
│       ├── k           : Int               — Agent index (1-based)
│       ├── lambda_k    : Float             — Cumulative Λ_k after this vote
│       └── stopped     : Boolean           — True if this step triggered a boundary
├── synthesis
│   ├── weighted_sum    : Float             — Σ(ω_{i,d} · x_i) before normalisation
│   ├── normalised_sum  : Float             — After dividing by Σω_{i,d}
│   ├── decision        : Int ∈ {-1,0,+1}  — D: final REJECT / DEADLOCK / APPROVE
│   └── confidence      : Enum             — { HIGH | MEDIUM | LOW_CONFIDENCE }
├── debate_enabled      : Boolean           — Whether the debate round was activated for this session
├── debate_votes        : List<AgentVote>?  — Round 2 revised votes (null if debate_enabled=False or SPRT fired in Round 1)
├── debate_sprt_trace   : List<SPRTStep>?   — SPRT trace for Round 2 (Λ reset to 0)
├── debate_synthesis    : Synthesis?        — Final decision when debate runs (supersedes synthesis if present)
├── debate_vote_changes : List<UUID>?       — Agent IDs that changed their vote between Round 1 and Round 2
├── ground_truth        : GroundTruth?      — Populated post-hoc by oracle
│   ├── oracle_type     : Enum             — { DEVELOPER | SAST | TEST_SUITE | COMPILER | BENCHMARK | CVE_SCAN }
│   ├── oracle_tier     : Int ∈ {1,2,3,4}  — Confidence tier (see §2.3.2)
│   ├── oracle_confidence_weight : Float   — γ_t corresponding to oracle_tier
│   ├── oracle_result   : Int ∈ {-1,+1}   — x*: actual outcome
│   └── observed_at     : ISO-8601 UTC
└── status              : Enum             — { PENDING | IN_PROGRESS | AWAITING_ORACLE | CLOSED }
```

**Confidence level rules:**

| Level | Condition |
|---|---|
| `HIGH` | SPRT reached a boundary before pool exhausted |
| `MEDIUM` | Full pool queried; $\lvert\text{normalised\_sum} - \theta_d\rvert \geq 0.2$ |
| `LOW_CONFIDENCE` | Full pool queried; result within $0.2$ of threshold; or $\geq 1$ `UNDER_CALIBRATED` agent was the deciding margin |

---

## 5. Session Lifecycle

```
                         ┌─────────────────────────────────────────────┐
                         │             ReviewSession Created             │
                         │  domain, θ_d, agent_pool, artifact selected  │
                         └──────────────────────┬──────────────────────┘
                                                │
                              ┌─────────────────▼──────────────────┐
                              │  Query Agent k (in pool order)      │
                              │  Record vote x_k, weight ω_{k,d}   │
                              └─────────────────┬──────────────────┘
                                                │
                              ┌─────────────────▼──────────────────┐
                              │    Compute Λ_k (SPRT update)        │
                              └─────────────────┬──────────────────┘
                                                │
                    ┌───────── Λ_k ≤ B ─────────┤──── Λ_k ≥ A ──────────────┐
                    │                           │                            │
                    ▼             B < Λ_k < A   │                            ▼
              D = −1 (REJECT)                   │                    D = +1 (APPROVE)
              Stop early ──────────────────►────┤                    Stop early
                                                │ (pool not exhausted)
                                          k < n │
                                                └──► Query Agent k+1
                                          k = n │
                                                ▼
                              ┌─────────────────────────────────────┐
                              │  Pool exhausted — Apply §2.1        │
                              │  Compute D via synthesis function   │
                              │  Assign LOW_CONFIDENCE if near θ_d  │
                              └─────────────────┬───────────────────┘
                                                │
                              ┌─────────────────▼──────────────────┐
                              │  Await Oracle (status: AWAITING)   │
                              │  Ground truth x* arrives (async)   │
                              │  Developer judgment = Tier 1       │
                              │  Automated tools = Tiers 2–4       │
                              └─────────────────┬──────────────────┘
                                                │
                              ┌─────────────────▼──────────────────┐
                              │  Backpropagate Trust               │
                              │  For each oracle that fired:       │
                              │  α += γ_t · c_{i,d}               │
                              │  β += γ_t · (1 − c_{i,d})         │
                              └─────────────────┬──────────────────┘
                                                │
                              ┌─────────────────▼──────────────────┐
                              │  Update AgentProfile.last_updated  │
                              │  Recompute calibration_status      │
                              │  Session status → CLOSED           │
                              └────────────────────────────────────┘
```

---

## 6. Invariants & Boundary Conditions

The following must hold at all times. A violation indicates a bug in the orchestration layer.

| # | Invariant | Formal Statement |
|---|---|---|
| I-1 | Weights are bounded | $\forall i, d:\; \omega_{i,d} \in [0, 1]$ |
| I-2 | Beta parameters are positive | $\forall i, d:\; \alpha_{i,d} \geq 1 \;\wedge\; \beta_{i,d} \geq 1$ |
| I-3 | Weight-sum is positive | $\sum_i \omega_{i,d} > 0$ for any non-empty pool |
| I-4 | Domain immutability | The `domain` field of an active `ReviewSession` is write-once |
| I-5 | Vote immutability | Once an `AgentVote` is recorded, its `vote` and `weight` fields are frozen |
| I-6 | Prompt drift detection | If `AgentProfile.prompt_hash` changes, all domain weights reset to $(\alpha, \beta) = (1, 1)$ |
| I-7 | Ground truth is binary | $x^* \in \{-1, +1\}$; partial oracles are not accepted |
| I-8 | SPRT uses snapshot weights | $\omega_{j,d}$ used in $\Lambda_k$ is the value at query time, not updated post-hoc |
| I-9 | Suspension floor | A `SUSPENDED` agent never participates, even if pool size drops to 1 |
| I-10 | Decay floor | After exponential decay, $\alpha^{\mathrm{eff}} \geq 1$ and $\beta^{\mathrm{eff}} \geq 1$ always hold |
| I-11 | Deterministic orchestration | The synthesis function, weight updates, and SPRT logic are computed by deterministic code. No LLM is involved in interpreting, routing, or deciding on votes. LLMs contribute $x_i$ only. |
| I-12 | Debate trigger is exclusive | The debate round only activates if $B < \Lambda_n^{(1)} < A$ (Round 1 pool exhausted without SPRT firing). A session with an SPRT-fired Round 1 result must not trigger a debate round. |
| I-13 | Weights are frozen during debate | $\omega_{i,d}$ used in Round 2 SPRT is identical to the value used in Round 1. Intra-session weight updates are prohibited. |
| I-14 | Oracle uses final round only | When debate runs, Bayesian updates use $x_i^{(2)}$ exclusively. Round 1 votes are archived for analysis but never feed the weight update rule. |

---

## 7. Validation Protocol

Before any production use, the framework must be verified against a **controlled mutation corpus** — a small dataset of code artefacts with pre-certified ground truth. This verifies three things independently:

1. The synthesis function $D$ produces the correct decision given the votes.
2. The Bayesian weight updates move $\omega_{i,d}$ in the correct direction.
3. The SPRT stops at an appropriate agent count (not too early, not too late).

### 7.1 Why Controlled Mutations

Real codebases provide uncertain, delayed ground truth. Mutations provide **pre-certified verdicts**: you introduce a known defect, so $x^* = -1$ (REJECT) is known with certainty before any agent is queried. After running agents and applying weight updates, you can verify by hand that the math produced the expected outcome.

This transforms validation from "wait for real bugs to surface" into "run the experiment now."

### 7.2 Corpus Design Principles

Each mutation must satisfy:

- **Certifiability:** $x^*$ is known before the session starts, not inferred afterward.
- **Traceability:** each mutation maps to exactly one domain and one oracle tier.
- **Reversibility:** the mutation is applied to a copy; the original clean state is preserved as the APPROVE baseline.
- **Non-triviality:** the defect must be plausible enough that at least one agent might miss it. Trivially obvious bugs test nothing.

### 7.3 Reference Corpus — ICGASA Project

The initial validation corpus is derived from the **ICGASA** project (a dual-language C++/Python training codebase with active CI infrastructure: CMake + ctest for C++, pylint + flake8 + mypy + pytest for Python). Mutations are applied to isolated copies; the original codebase is never committed in a broken state.

| ID | Domain | Mutation Description | Introduced Defect | $x^*$ | Oracle | $\gamma_t$ |
|---|---|---|---|---|---|---|
| M-01 | `LOGIC` | Remove div-by-zero guard in `calculator.cpp` | Calling `calc.divide(x, 0)` produces UB / crash instead of throwing | $-1$ | ctest (T3) + Developer (T1) | 0.3 / 1.0 |
| M-02 | `LOGIC` | Restore pre-SFINAE type error in `main.cpp` | Lambda with incompatible return type; does not compile | $-1$ | Compiler (T4) + Developer (T1) | 0.1 / 1.0 |
| M-03 | `LOGIC` | Drop test coverage for negative-operand edge cases | `multiply(-1, -1)` and `subtract(INT_MIN, 1)` untested | $-1$ | Developer (T1) — test suite cannot self-report its own gaps | 1.0 |
| M-04 | `SECURITY` | Add a path-joining utility that concatenates user input without sanitization | Path traversal: `../../etc/passwd` style injection | $-1$ | SAST (T2) + Developer (T1) | 0.7 / 1.0 |
| M-05 | `PERFORMANCE` | Replace `divide` with a loop-subtraction implementation | $O(a/b)$ instead of $O(1)$; regresses on large inputs | $-1$ | Developer (T1) + Benchmark (T2) | 1.0 / 0.7 |
| M-06 | `LOGIC` | No overflow guard in `multiply` for `INT_MAX` inputs | `multiply(INT_MAX, 2)` silently overflows | $-1$ | Developer (T1) + ctest edge-case (T3) | 1.0 / 0.3 |
| M-00 | `LOGIC` | Clean baseline — no mutation | Original code, all tests passing | $+1$ | ctest (T3) + Developer (T1) | 0.3 / 1.0 |

M-00 is the APPROVE control case. All other mutations are REJECT cases. A balanced corpus requires at least one APPROVE case to prevent agents from simply learning to always vote REJECT.

### 7.4 Expected Convergence After Full Corpus

After running all 7 sessions (M-00 through M-06) with a three-agent pool (SKEPTIC, ADVOCATE, AUDITOR) and applying Tier 1 developer oracle updates throughout, the expected qualitative outcome is:

- **SKEPTIC** $\omega$ rises in `LOGIC` — the adversarial persona catches defects that look superficially correct (missing guards, overflow, absent test coverage).
- **ADVOCATE** $\omega$ rises for M-00 (correctly defends clean code) but drops on subtle REJECT cases where the code "reads fine."
- **AUDITOR** $\omega$ tracks ADVOCATE closely — both share the same blind spot on absence-type defects.

See §7.6 for the actual observed results from the live validation run.

If weights do not diverge in this qualitative pattern after 7 sessions, investigate the update rule implementation before proceeding.

### 7.5 Baseline Comparison

After completing the corpus sessions, evaluate the **single-best-agent baseline**:

$$\text{Baseline accuracy} = \frac{\text{correct decisions by agent } i^*}{7} \quad \text{where } i^* = \arg\max_i \omega_{i,d}$$

$$\text{WaRF accuracy} = \frac{\text{correct ensemble decisions } D}{7}$$

WaRF is justified if and only if $\text{WaRF accuracy} \geq \text{Baseline accuracy}$. If the best single agent already gets all 7 correct, WaRF adds no value for this corpus — expand the corpus before concluding.

---

### 7.6 Live Validation Run Results (June 2026)

The first live run against the full ICGASA corpus using Claude Haiku 4.5 as the voting model produced the following results:

| Session | Domain | $x^*$ | WaRF $D$ | Correct | SPRT fired | Confidence |
|---|---|---|---|---|---|---|
| M-01 | LOGIC | REJECT | REJECT | ✓ | No | MEDIUM |
| M-00 | LOGIC | APPROVE | APPROVE | ✓ | No | MEDIUM |
| M-02 | LOGIC | REJECT | REJECT | ✓ | Yes ($k=3$) | HIGH |
| M-03 | LOGIC | REJECT | APPROVE | ✗ | No | MEDIUM |
| M-04 | SECURITY | REJECT | REJECT | ✓ | No | MEDIUM |
| M-05 | PERFORMANCE | REJECT | REJECT | ✓ | No | MEDIUM |
| M-06 | LOGIC | REJECT | APPROVE | ✗ | No | MEDIUM |

**WaRF accuracy: 5/7 (71%)**

**Single-agent comparison:**

| Agent | Correct | Accuracy | Final $\omega$ (LOGIC) |
|---|---|---|---|
| SKEPTIC | 6/7 | 86% | 0.714 |
| ADVOCATE | 5/7 | 71% | 0.571 |
| AUDITOR | 5/7 | 71% | 0.571 |
| **WaRF ensemble** | **5/7** | **71%** | — |

**Finding:** WaRF did not outperform the single best agent (SKEPTIC at 86%) on this corpus. Both errors (M-03, M-06) were absence-type defects — missing test coverage and missing overflow guard — where ADVOCATE and AUDITOR voted APPROVE and overruled the correct SKEPTIC vote.

**Self-correcting behaviour:** After 7 sessions, SKEPTIC holds the highest LOGIC weight (0.714). Future LOGIC reviews will weight SKEPTIC more heavily, making it progressively harder for ADVOCATE and AUDITOR to overrule a SKEPTIC REJECT on the kinds of defects that caused the two errors. The baseline criterion was not met on this corpus; the system is calibrating toward meeting it.

**SPRT finding:** Early stopping fired once (M-02, $k=3$), providing no agent-call savings since $k=n$. This confirms the 3-agent pool-size constraint described in §3.2.7. The 5-agent pool experiment (planned) is required to validate SPRT's cost-saving claim.

---

*End of WaRF Specification v0.4*
