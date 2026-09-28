# WaRF — Weighted n-Agent Reliability Framework

**One-line pitch:** A Bayesian calibration system that measures how reliable each LLM code-review agent is — per domain — and lets that measurement govern how much its votes count.

---

## The Problem

Automated code review tools produce too many false positives. Teams learn to mute them. Human review does not scale. Large language models can reason about code, but their reliability is unknown and inconsistent across problem types, and they are often confidently wrong.

---

## The Approach

Five LLM agents with distinct review personas evaluate a code change one after another, most reliable first:

| Agent | Persona in brief |
|---|---|
| AUDITOR | Applies standards and best practice without a bias toward approval or rejection |
| ADVOCATE | Assumes the code is correct unless it finds a clear, demonstrable defect |
| SKEPTIC | Searches hard for bugs and unsafe assumptions; rejects only if it can name an input that breaks |
| BOUNDARY | Traces `None`, empty, zero, negative, maximum and off-by-one inputs |
| TEST-FOCUSED | Asks whether a test would catch it if this code were wrong |

Each agent votes APPROVE or REJECT. A **Sequential Probability Ratio Test (SPRT)** adds up the votes, each weighted by the agent's measured reliability ω in the domain under review:

```
Δλ = ω × LLR      LLR(APPROVE) = ln(0.80 / 0.30) ≈ +0.981
                  LLR(REJECT)  = ln(0.20 / 0.70) ≈ −1.253
```

The step is asymmetric on purpose: a REJECT is stronger evidence than an APPROVE of the same weight. When the running score λ crosses a boundary — **A ≈ +2.890** (APPROVE) or **B ≈ −2.251** (REJECT) — the review stops and the remaining agents are never asked. That is the only way to get confidence **HIGH**.

If every agent has voted and neither boundary was crossed, the decision comes from a weighted average of the votes compared with a domain threshold θ (LOGIC 0.0, SECURITY +0.2, PERFORMANCE −0.1). A margin of at least 0.2 gives **MEDIUM**, a smaller one **LOW**.

After a human decides what the right verdict was, each agent that voted is scored against it. Every agent has a Beta distribution per domain, starting at α = β = 1 (ω = 0.5, maximum uncertainty). A correct vote adds to α, a wrong one to β, and ω = α / (α + β). A low ω shrinks an agent's vote; it never flips its sign.

---

## Evidence so far

All of this is preliminary: one labelled corpus, small samples. Full figures and caveats are in the README and the guide.

**Confidence bands** on the 62 developer-labelled reviews:

| Band | Reviews | Correct |
|---|---|---|
| LOW | 15 | 27% |
| MEDIUM | 35 | 63% |
| HIGH | 12 | 75% |

**Weights** in the frozen snapshot used for the talk, after decay:

| Agent | ω LOGIC | ω SECURITY |
|---|---|---|
| AUDITOR | 0.77 | 0.61 |
| ADVOCATE | 0.69 | 0.61 |
| BOUNDARY | 0.59 | 0.47 |
| SKEPTIC | 0.45 | 0.60 |
| TEST-FOCUSED | 0.32 | 0.52 |

**Persona lesson.** The first TEST-FOCUSED persona rejected all 38 labelled reviews it took part in, so its vote carried no information and its weight only tracked how often the truth happened to be REJECT. A persona has to state a bar, not just a lens. The current personas say when to approve.

**Head-to-head** on the same 12 labelled files: the mixed panel got 11 right, five AUDITORs 10, five SKEPTICs 10. That is a tie on accuracy. The difference is confidence: only the single-persona pools were wrong at HIGH.

**Debate round** (`--debate`, opt-in): six logged sessions, judged against the corpus labels. It helped in two, changed nothing in one and made the verdict wrong in three, each time at HIGH. Treat a HIGH after debate with more caution than a first-round HIGH.

---

## Current Status

- CLI: `warf review <path>` for a file or a directory, and `warf review-commit <hash> --repo <path>` for a commit (git; SVN revisions are handled too); `warf label` records the human verdict.
- Several model backends (Claude CLI, Anthropic API, OpenAI-compatible endpoints, Ollama), a `/warf` skill for Claude Code, and an MCP server.
- Dashboards regenerated after every review from the session log: session list (numbered, searchable), confidence calibration, weight trajectories, token cost.
- Corpus: 251 logged sessions, 62 with a developer label, from `psf/requests`, `urllib3`, G+Smo and a synthetic validation suite.

Talk: SoCraTes Austria, 25 September 2026. See `README.md` to get started, `GUIDE.md` for the reasoning and `SPECIFICATION.md` for the mathematics.
