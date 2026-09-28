# WaRF — Weighted n-Agent Reliability Framework

Multi-agent code review that knows how sure it is.

A panel of reviewer personas votes on a file, a diff, or a commit. Each vote is
weighted by that agent's **learned reliability in the domain**, the weighted
evidence accumulates under a **sequential probability ratio test**, and the
review stops the moment a boundary is crossed. The result is a verdict *and a
confidence level* — and the confidence level is the part that decides what to
do with it. Feed back what a human eventually decided, and the weights update.

```
$ warf review src/auth.py --json --fail-on HIGH
{
  "decision": "REJECT", "confidence": "HIGH", "sprt_lambda": -2.33, "sprt_fired": true,
  "votes": [
    {"agent": "BOUNDARY",     "label": "REJECT", "omega": 0.70, "reasoning": "..."},
    {"agent": "SKEPTIC",      "label": "REJECT", "omega": 0.62, "reasoning": "..."},
    {"agent": "TEST-FOCUSED", "label": "REJECT", "omega": 0.54, "reasoning": "..."}
  ],
  "session_id": "f26f4939-…"
}
```

Three of five agents were enough. Each REJECT moved λ by ω × −1.253: −0.88, −1.65,
−2.33 — past the REJECT boundary at −2.251, so the other two were never called. Had
one of them voted first and dissented, its vote would have counted in proportion to
its track record in SECURITY, not as one voice in five.

---

## How it works

1. **Five personas, one lens each.** SKEPTIC hunts for demonstrable defects;
   ADVOCATE approves unless one is shown; AUDITOR applies standards without bias;
   TEST-FOCUSED asks whether a failure would be loud or silent; BOUNDARY traces
   None, empty, zero, negative and off-by-one inputs. Diversity of *what each
   agent looks for* is the point: five copies of one persona mostly agree with
   each other, and the test then reads their agreement as evidence (see *Status
   and evidence*).
2. **Weighted votes.** Every agent has a Beta posterior per domain
   (LOGIC / SECURITY / PERFORMANCE); its mean, ω, is the weight of its vote.
   Heaviest agents vote first.
3. **Sequential test.** Each vote adds ω × log-likelihood-ratio to a running
   statistic λ. Crossing +2.890 is `APPROVE [HIGH]`; crossing −2.251 is
   `REJECT [HIGH]`; the review stops there. If all agents vote without a
   crossing, a weighted average decides and the confidence is `MEDIUM` or `LOW`.
4. **Learning.** `warf label <session> --verdict APPROVE|REJECT` records what
   was actually true. Agents that voted correctly gain weight in that domain,
   the others lose it. Weights are tied to the exact persona text that earned
   them: edit a prompt and its weights are retired, not silently reused.

The output is only useful if read correctly — `HIGH` is a statistical decision,
`MEDIUM` is an honest "the panel was split", `LOW` is *not actionable*. The full
routing table and what never to do with a verdict are in
[`warf/policy.md`](warf/policy.md). Every integration below ships that policy
with it.

---

## Install

```bash
pip install .                # from a checkout; core has no dependencies
pip install -e .             # development
pip install ".[anthropic]"   # Anthropic SDK provider (ANTHROPIC_API_KEY)
pip install ".[mcp]"         # the MCP server
```

Python ≥ 3.10. `warf` is the installed command; `python -m warf` (or `py -m warf`
on Windows) is equivalent and does not depend on PATH. The distribution is named
`warf-review` (the bare name is taken on PyPI); it is not published yet, so install
from a checkout. The import package and the command are `warf` either way.

```bash
warf init                    # data directory + a first profile
warf providers               # which model backend will answer
warf review path/to/file.py  # a review
```

---

## Reviewing

```bash
warf review file.py                          # human-readable
warf review file.py --json                   # machine-readable, stdout only
warf review file.py --domain SECURITY        # override AUTO detection
warf review src/                             # every supported file under a directory
warf review-commit <sha> --repo .            # only the files a commit changed
```

**Exit codes** are `0` nothing failed the gate, `1` a REJECT met the `--fail-on`
threshold, `2` WaRF could not run (bad path, no credentials, quota) — `2` is never
a verdict. For CI, always set the threshold explicitly:

```bash
warf review src/ --json --fail-on HIGH       # block only on REJECT [HIGH]
```

The default threshold is `LOW` for backward compatibility; `policy.md` §2 explains
why a gate should never act on `LOW`.

**Close the loop** once a human has decided:

```bash
warf label <session-id> --verdict REJECT              # id from the review output
warf label --artifact auth.py --verdict APPROVE       # or select by path
```

Never label on a guess: there is no undo short of `warf reset`.

---

## Where state lives

Profiles, the session log and the generated dashboards live in a data directory,
never in the package:

| Resolution order | Location | Use |
|---|---|---|
| `WARF_HOME` | anywhere | CI, scripts |
| nearest `.warf/` walking up from the working directory | project | `mkdir .warf` or `warf init --local`; commit it to share calibration |
| `~/.warf/` | per user | the default; labels accumulate across projects |

`warf paths` shows what resolved and why. `warf refresh` regenerates the
dashboards (`dashboard.html`, `confidence_calibration.html`, …) from the log.

Every review regenerates those pages, silently. To have them opened in your browser
as well, put `{"open_pages": true}` into `settings.json` in the data directory, or
set `WARF_OPEN_BROWSER=1` for one run; `WARF_NO_BROWSER=1` overrides both (batch
runs, CI).

The session list in `dashboard.html` numbers every review: `#1`, `#2`, … in the order
it was logged. A number never changes when more reviews are added. Type `#47` into the
search box to open exactly that session, whatever filters are active. On the
weight-trajectory page, click an agent's name in a legend to bring its line to the
front; two agents with identical histories draw on the same pixels.

---

## Model providers

WaRF's contribution is the weighting, the test and the calibration; it does not
care who answers the prompt. The panel can even mix providers per agent.

| Provider | Needs | Notes |
|---|---|---|
| `claude_cli` | Claude Desktop / Claude Code installed | default when found; subscription quota, no key |
| `anthropic` | `ANTHROPIC_API_KEY`, `pip install ".[anthropic]"` | real token counts |
| `openai_compat` | `WARF_BASE_URL`, optionally `WARF_API_KEY` | OpenAI, Groq, DeepSeek, Together, Mistral, vLLM, LM Studio … |
| `ollama` | a local Ollama | alias for `openai_compat` at `localhost:11434` |

```bash
warf init --provider ollama --model qwen2.5-coder:7b   # a whole panel on a local model
```

Per agent, in a profile file:

```json
{ "name": "SKEPTIC", "provider": "openai_compat", "model": "qwen2.5-coder:7b", ... }
{ "name": "AUDITOR", "provider": "anthropic",     "model": "claude-haiku-4-5-20251001", ... }
```

Because ω is learned per agent per domain, a mixed panel discovers on its own
which persona-on-which-model is worth trusting where. `WARF_PROVIDER`,
`WARF_MODEL` and `WARF_TIMEOUT` set process-wide defaults.

---

## Weights and personas

```bash
warf weights                  # α, β, ω and a 95% interval per agent per domain
warf weights --reconcile      # apply pending persona-version changes now
warf reset --profile NAME     # back to uniform priors
```

Each profile entry records a fingerprint of the persona text that earned its
weights. Change the text and `warf weights` shows the agent as `CHANGED`; the
next review parks the old weights under their fingerprint and restarts the agent
at uniform priors. Revert the text and the old weights come back. A label for a
vote cast by a retired version is recorded but not applied.

---

## Using WaRF from an agent

**Claude Code.** Installs a `/warf` skill that embeds the interpretation policy:

```bash
warf install-skill            # .claude/skills/warf/SKILL.md in this project
warf install-skill --global   # ~/.claude/skills, every project
```

The skill is generated from the installed package, with the invocation that works
on *your* machine baked in — so each developer runs `warf install-skill` once and
nothing needs committing. A team that prefers to commit it should install it with
an invocation that works everywhere, and regenerate it after upgrading WaRF:

```bash
warf install-skill --command "python -m warf"   # portable; then commit .claude/skills/warf/
warf install-skill                              # later: "Up to date", or "Out of date" (exit 1)
warf install-skill --force                      # regenerate, keeping the committed invocation
```

**Any MCP client** (Claude Desktop, Cursor, Zed, custom agents):

```json
{ "mcpServers": { "warf": { "command": "python", "args": ["-m", "warf.mcp_server"] } } }
```

Tools: `warf_review`, `warf_label`, `warf_weights`, `warf_sessions`, `warf_paths`;
the policy is served as the server's instructions, a prompt and a resource. Run
the client from the project root or set `WARF_HOME` so the right `.warf/` is used.

**CI.** [`.github/workflows/warf-review.yml`](.github/workflows/warf-review.yml)
reviews the files a pull request changed and posts the verdict as a comment.

---

## Status and evidence

Alpha. The mechanism is complete and the numbers are preliminary — they come
from a small labelled corpus and should be read with the caveats attached.

- **Confidence tracks accuracy — direction confirmed, magnitudes provisional.**
  On 62 labelled sessions the bands order as they should: `LOW` 27% correct (4/15),
  `MEDIUM` 63% (22/35), `HIGH` 75% (9/12). Two caveats: the sessions that taught the
  weights are the ones being scored, and the assumed vote probabilities turned out
  about 3× too optimistic for the personas of the time — replayed with the measured
  values, none of those 12 `HIGH` verdicts would have reached the boundary (no
  decision changes; all 12 become `MEDIUM`).
- **Persona prompts must state a bar, not just a lens.** Measuring every agent's
  votes against ground truth exposed one agent that never approved anything (38 of
  38 votes REJECT) and one at chance: across the labelled corpus the original panel
  approved good code 53% of the time and bad code 36% of the time. With the three
  weak prompts rewritten, a 12-file reference set gives 76% and 17%, and 11/12
  verdicts correct where the original panel had 10/12 — two false alarms on clean
  code gone, one subtle bug now missed. Different file sets and small n: the
  mechanism holds, the magnitudes are not established.
- **The constants have been checked, not just assumed.** With the rewritten personas
  the measured REJECT step (−1.24) matches the assumed one (−1.25); the assumed
  APPROVE step (+0.98) is conservative against the measured +1.49. The engine still
  uses `P1 = 0.80`, `P0 = 0.30`.
- **A mixed panel is not more accurate than five copies of one persona — it is
  harder to fool.** Same 12 files, same model, uniform weights: mixed panel 11/12,
  five AUDITORs 10/12, five SKEPTICs 10/12. But each cloned pool failed in the
  direction of its persona's bias, and confidently: the SKEPTICs unanimously
  rejected clean code at `HIGH`; the mixed panel produced no wrong `HIGH` verdict.
  Which persona would be the right one to clone is not knowable in advance —
  AUDITOR alone is right in 90% of its LOGIC reviews and 55% of its SECURITY reviews.
- **One known wart in the data.** A `help.py` review of 24 July carries an APPROVE
  label that was corrected to REJECT the next day on a later session; the first
  label is kept as logged, which makes `MEDIUM` look one review worse than it was.
  Experiments take one ground truth per file, the most recent
  (`tools/_groundtruth.py`).

`tools/measure_llr.py`, `tools/run_persona_experiment.py` and `tools/compare_pools.py`
are the instruments (experiment runs are kept in `.warf-experiments/`, apart from the
labelled corpus); [`GUIDE.md`](GUIDE.md) is a plain-language introduction;
[`SPECIFICATION.md`](SPECIFICATION.md) the formal description.

---

## Repository layout

```
warf/            the package: orchestrator, engine, providers, state, paths, cli, mcp_server, policy.md
tools/           research and dev scripts (not installed)
.warf/           this repository's own data: session log, corpus_v1 and talk-snapshot profiles
.warf-experiments/  persona experiment sessions and profiles, kept apart so the corpus stays stable
validation/      synthetic review subjects with planted defects (M-01 … M-11)
slides/          the SoCraTes Austria 2026 talk
```

Built for [SoCraTes Austria 2026](https://socrates-conference.at/).

---

## License and citation

- **Code** — `warf/`, `tools/`, `validation/` and the project configuration — is
  licensed under the [Apache License 2.0](LICENSE); see [`NOTICE`](NOTICE).
- **Slides and written notes** — `slides/`, `GUIDE.md`, `SPECIFICATION.md`,
  `OVERVIEW.md`, `IDEAS.md` — are licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); see
  [`slides/LICENSE.md`](slides/LICENSE.md).
- **Research data** — the session logs and profiles under `.warf/` and
  `.warf-experiments/` — is released under the same CC BY 4.0 terms. It contains
  model-generated commentary on third-party open-source code (psf/requests,
  urllib3, G+Smo), which remains under its own licenses.

If you use WaRF in research, please cite it: GitHub's "Cite this repository"
reads [`CITATION.cff`](CITATION.cff).
