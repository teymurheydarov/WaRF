# WaRF Output Interpretation Policy

**Single source of truth.** This file is emitted into every adapter — the Claude Code
skill (`warf install-skill`), the MCP server's tool descriptions and prompts, and the
README. Edit here, regenerate the adapters; never edit a copy.

Audience: an agent or developer consuming `warf review --json`.

---

## 1. What a review returns

`warf review <file> --json` emits one object on stdout. All human-facing output goes
to stderr, so stdout is always safe to pipe.

```json
{
  "schema":           1,
  "mode":             "file",
  "fail_on":          "HIGH",
  "session_id":       "f26f4939-4515-49ed-bbd6-c8c8667e3579",
  "created_at":       "2026-09-19T08:14:02.119384+00:00",
  "artifact":         "src/requests/sessions.py",
  "domain":           "SECURITY",
  "theta":            0.2,
  "decision":         "REJECT",
  "confidence":       "HIGH",
  "sprt_lambda":      -2.3301,
  "sprt_fired":       true,
  "normalised_score": null,
  "votes": [
    {
      "agent":      "BOUNDARY",
      "vote":       -1,
      "label":      "REJECT",
      "omega":      0.7,
      "provider":   "anthropic",
      "model":      "claude-haiku-4-5-20251001",
      "persona":    "500973c48f91",
      "reasoning":  "...",
      "tokens_in":  7412,
      "tokens_out": 401
    },
    { "agent": "SKEPTIC",      "vote": -1, "label": "REJECT", "omega": 0.62, "...": "..." },
    { "agent": "TEST-FOCUSED", "vote": -1, "label": "REJECT", "omega": 0.54, "...": "..." }
  ],
  "total_tokens_in":  22187,
  "total_tokens_out": 1201
}
```

The numbers are reproducible, and an agent may check them: each vote moves λ by
ω × LLR (§4), here 0.70, 0.62 and 0.54 × −1.253 → −0.877, −1.654, −2.330. The third
vote crossed `λ_B ≈ −2.251`, so the review stopped with two agents never asked.
Unless `--no-early-stop` was given, the vote that crosses a boundary is the last one
in `votes`, and it always agrees with the verdict.

Field notes that matter when parsing:

- **`vote` is an integer** (`+1` approve, `-1` reject). The human-readable string is
  in **`label`**. Comparing `vote` against `"REJECT"` will never match.
- **`votes` is ordered by descending ω** — heaviest-weighted agent first.
- **`sprt_fired`** is `true` exactly when `confidence == "HIGH"`. It is the
  mechanical fact behind the label: the boundary was crossed and — unless
  `--no-early-stop` was given (§10) — the review stopped there.
- **`normalised_score`** is the weighted-average fallback and is `null` on many
  boundary-crossing sessions. Do not rely on it being present.
- **`provider`, `model`, `persona`** on each vote record which backend answered and
  the 12-character fingerprint of the persona text that cast it. A vote whose
  `persona` no longer matches the profile's current version is refused by
  `warf label` (§7): its outcome is recorded, the weight is not updated.
- **`session_id`** is what `warf label` consumes (§7). Keep it if there is any chance
  a human will later confirm or overturn the verdict.
- A **`debate`** block appears only when `--debate` ran. It carries its own `votes`,
  each with a `changed` boolean, plus a `vote_changes` list of the agents that
  flipped. When it is present, top-level `decision`, `confidence` and `sprt_fired`
  are the debate's outcome, while top-level `votes`, `sprt_lambda` and
  `normalised_score` are still Round 1's: the λ behind the verdict is
  `debate.sprt_lambda`, and that is the one to report. See §8.

`decision` alone is **not** an actionable verdict. It must always be read together with
`confidence`. An agent that acts on `decision` while ignoring `confidence` is using
WaRF incorrectly and will act on noise — see §3.

### Reviewing many files

A directory or commit review returns an envelope instead of a bare record:

```json
{
  "schema":  1,
  "mode":    "directory",
  "root":    "src/",
  "fail_on": "HIGH",
  "summary": {"total": 12, "approve": 9, "reject": 3, "error": 0, "failing": 1},
  "reviews": [ /* one object per file, same shape as above */ ]
}
```

`mode` is `"directory"` or `"commit"` (a commit envelope carries `commit` and `repo`
instead of `root`). **`summary.failing`** counts only the files that met the
`--fail-on` threshold — it is the number that drives the exit code, and it is
normally smaller than `summary.reject`. Report `failing`, not `reject`, when telling
a human whether a change is blocked.

Files that errored appear in `reviews` as `{"artifact": ..., "decision": "ERROR",
"error": "..."}` with no verdict fields.

---

## 2. The routing table

This is the core of the policy. Apply it literally.

| decision | confidence | Action |
|---|---|---|
| `REJECT`  | `HIGH`   | **Block.** Report the objecting agents and their reasoning. |
| `APPROVE` | `HIGH`   | **Safe to proceed** without human review. |
| either    | `MEDIUM` | **Surface to a human.** Do not auto-act. Report that the panel was split. |
| either    | `LOW`    | **Do not act on this verdict.** Report it as inconclusive. |

`LOW` is not a weak version of the verdict. It means the panel produced no usable
signal. Treat a `LOW REJECT` as "WaRF has no opinion", not as "a mild reject".

### Enforcing the table in CI: `--fail-on`

Exit code alone cannot express confidence, so `--fail-on` sets the confidence floor
at which a `REJECT` fails the build:

| Flag | Exit 1 on | Use for |
|---|---|---|
| `--fail-on HIGH` | `REJECT [HIGH]` only | **CI gates.** The only setting consistent with the table above. |
| `--fail-on MEDIUM` | `REJECT [HIGH\|MEDIUM]` | Advisory runs where a split panel should still draw attention. |
| `--fail-on LOW` | any `REJECT` | Legacy default. Blocks on `LOW`, which this table forbids. |

**The default is `LOW`**, for backward compatibility with scripts written before the
flag existed. It is *not* the recommended setting. A CI gate should be explicit:

```bash
warf review src/ --fail-on HIGH --json
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Nothing met the `--fail-on` threshold. Proceed. |
| `1` | At least one `REJECT` met the threshold. WaRF ran correctly and objected. |
| `2` | **WaRF could not run.** Bad path, unreadable diff, no matching session. |

Never treat `2` as a review verdict. It means the review did not happen — a build
that conflates it with `1` will report a nonexistent defect, and one that conflates
it with `0` will silently skip review entirely.

---

## 3. What confidence actually means (mechanically)

Confidence is **not** a softened restatement of the decision. It reports *how* the
decision was reached.

- **`HIGH`** — the SPRT boundary was crossed and the review stopped early.
  Accumulated weighted evidence reached `λ_A ≈ +2.890` (approve) or
  `λ_B ≈ −2.251` (reject) before the agent pool was exhausted.

- **`MEDIUM`** — the pool was exhausted *without* crossing either boundary. The
  verdict comes from a weighted-average fallback, and the margin from the domain
  threshold was `≥ 0.2`.

- **`LOW`** — the pool was exhausted without crossing a boundary, **and** the
  weighted average landed within `0.2` of the domain threshold. The panel was
  effectively undecided.

Note that `MEDIUM` and `LOW` are the *same* mechanical situation — no boundary was
crossed. They differ only in how far the weighted average sat from the threshold.
Neither carries the statistical guarantee that `HIGH` does.

### Observed accuracy on the reference corpus

Measured on 62 oracle-labelled sessions (`psf/requests`, Claude Haiku agents):

| Band | Correct | Rate |
|---|---|---|
| `HIGH`   | 9 / 12  | 75% |
| `MEDIUM` | 22 / 35 | 63% |
| `LOW`    | 4 / 15  | **27%** |

**`LOW` performs below a coin flip.** This is why the routing table forbids acting on
it. It is not a calibration bug — it is `LOW` correctly reporting that the panel had
no coherent signal.

> These figures describe the reference corpus, not a guarantee for your installation.
> A fresh install starts at uniform weights (ω = 0.5 for every agent) and its
> confidence bands are **not yet calibrated**. They become meaningful only as oracle
> labels accumulate — see §7. Until then, treat `HIGH` as "the panel agreed early",
> not as "75% likely correct".

---

## 4. The APPROVE/REJECT asymmetry

The boundaries are deliberately asymmetric: `|λ_B| = 2.251` vs `λ_A = 2.890`, and a
REJECT vote carries more log-likelihood weight than an APPROVE vote
(`≈ −1.253` vs `≈ +0.981`).

Consequences an agent should know:

- `HIGH REJECT` is reachable with **three** agreeing agents once their weights
  average ω ≥ 0.60; at the uniform ω = 0.5 of a fresh install it takes four.
- `HIGH APPROVE` requires **all five agents to approve, with weights averaging
  ω ≥ 0.59**. On a fresh install it is unreachable: five approvals at ω = 0.5 add up
  to +2.45, short of +2.890.
- Therefore `HIGH APPROVE` is rare, and correspondingly strong when it appears.
- The absence of `HIGH APPROVE` is **not** evidence of a problem. Most clean code
  returns `MEDIUM APPROVE`.

Do not report `MEDIUM APPROVE` as though WaRF found something wrong. It usually means
the code is fine and the panel simply never reached unanimity.

---

## 5. Reading the per-agent votes

`votes` is ordered by descending ω — heaviest-weighted agent first.

- **ω is domain-specific.** An agent with ω = 0.77 in LOGIC may sit at 0.45 in
  SECURITY. Never quote an agent's weight without naming the domain.
- **A dissent from a high-ω agent matters more than agreement from a low-ω one.**
  When reporting, lead with the highest-ω agent that dissented from the final
  decision.
- **ω is not a quality score.** It estimates agent–domain *fit*, learned from past
  labelled outcomes. Low ω means "has been wrong in this domain before", not
  "is a bad reviewer".

Useful phrasing when reporting to a human. After an early stop there is often no
dissent at all — the vote that crosses a boundary agrees with the verdict, and
whoever was not asked did not vote:

> REJECT, HIGH confidence (λ = −2.33, stopped after 3 of 5 agents).
> BOUNDARY (ω = 0.70), SKEPTIC (ω = 0.62) and TEST-FOCUSED (ω = 0.54) all flagged
> the auth header handling. The other two agents were not asked.

When there is dissent — most often because the panel split — it leads the report:

> REJECT, MEDIUM confidence — all 5 agents voted, no boundary crossed (λ = −1.06).
> AUDITOR, the highest-weighted dissenter (ω = 0.66 in SECURITY), approved: it read
> the header handling as correct. BOUNDARY (ω = 0.70), SKEPTIC (ω = 0.62) and
> TEST-FOCUSED (ω = 0.50) rejected; ADVOCATE (ω = 0.58) approved.
> MEDIUM goes to a human (§2) — this is not a block.

---

## 6. Choosing the domain

`--domain AUTO` (the default) infers from file path and content. Override when you
have better information than the file extension provides:

| Use | When |
|---|---|
| `SECURITY` | auth, crypto, sessions, input validation, deserialisation, subprocess, network boundaries |
| `LOGIC` | algorithms, state machines, control flow, data transformation |
| `PERFORMANCE` | hot paths, allocation, queries, concurrency |

`SECURITY` applies a threshold bias of `θ = +0.2` toward REJECT — the same evidence
yields a stricter verdict. Selecting `SECURITY` for ordinary business logic will
produce spurious rejects. Do not select it defensively.

---

## 7. Closing the loop — the part most integrations skip

When a human resolves a review, report the outcome back:

```bash
warf label <session-id> --verdict APPROVE|REJECT --oracle DEVELOPER
warf label --artifact sessions.py --verdict REJECT     # select by path instead
```

The `<session-id>` comes from the review's `session_id` field, or from the line the
CLI prints after each review. A unique prefix is enough. If the selector matches more
than one session the command exits `2` and lists the candidates (as `candidates[]`
under `--json`) rather than guessing.

This is what makes WaRF improve. Each labelled outcome updates the Beta posterior for
every agent that voted, per domain. Without labels, weights stay at their priors and
the confidence bands never calibrate.

When the session included a debate round, the **Round-2** votes are scored, not
Round-1 — the oracle credits each agent's final position, not its opening one.

Label whenever ground truth becomes known:

- a human overrode a `HIGH REJECT` and merged anyway → label `APPROVE`
- a `MEDIUM` was escalated and the reviewer confirmed the defect → label `REJECT`
- a `LOW` was ignored and the code later proved faulty → label `REJECT`

Oracle tiers carry different weight: `DEVELOPER` (γ=1.0) > `SAST` (0.7) >
`TEST` (0.3) > `COMPILER` (0.1). Use `DEVELOPER` only for an actual human judgement.

**Do not label speculatively.** A guessed label corrupts the weights permanently and
there is no undo short of `warf reset`, which discards *all* learning, not just the
bad entry.

Labelling an already-labelled session is refused unless `--force` is given. With
`--force` the original label is preserved in the log as the historical record, but a
second weight update is applied on top of the first — so the agents involved are
credited or penalised twice. Use it only to repair a run where the profile write
failed, never to change your mind about a verdict.

**Persona versions.** Every vote records a fingerprint of the persona text that cast
it. When an agent's prompt is edited, its weights are retired (kept under their
fingerprint, restored if the text is reverted) and the agent restarts at uniform
priors — `warf weights` shows this as status `CHANGED` until the next review
applies it, or `warf weights --reconcile` applies it now. A label for a vote cast
by a retired version is recorded but **not applied**: a changed agent must earn
its own weights. Whitespace-only edits do not count as a change.

---

## 8. Debate (`--debate`) — use sparingly

When the pool exhausts without crossing a boundary, `--debate` runs a second round in
which agents see each other's arguments and may revise. An agent that produced no
Round-1 vote (it timed out) has no position to revise and is not polled, so
`debate.votes` can be shorter than the panel.

Debate is **not** a reliability improvement. Observed outcomes across three cases:

| Case | Outcome |
|---|---|
| Argument was verifiable against a specific line | Majority correctly updated → correct, unanimous `REJECT` — still only `MEDIUM`: a three-agent pool could not reach the boundary |
| One agent held a false premise | It did not update despite correct counter-arguments. No change. |
| A plausible-but-wrong argument was rhetorically strong | **The correct minority reversed.** Result: `HIGH` confidence on the *wrong* verdict. |

That third case is the important one: debate converted a correct `MEDIUM` into an
incorrect `HIGH`. Debate can *manufacture* confidence without adding correctness.

Guidance:

- Use `--debate` when a `MEDIUM` blocks a decision that must be resolved now.
- Do not use it routinely, in CI, or to "get a clearer answer".
- After a debate round, treat a resulting `HIGH` with more caution than a first-round
  `HIGH`. Check whether agents *changed* their votes — a flipped majority is a
  warning sign, not a confirmation.

---

## 9. Prohibited readings

Do not:

- act on `decision` without reading `confidence`
- treat `LOW` as a weaker `MEDIUM` — it is below chance, it is not directional
- report `MEDIUM` as a failure or an error; it is a valid, honest outcome
- describe a low-ω agent as unreliable in general — ω is per-domain
- quote the §3 accuracy figures as properties of the user's installation
- run `--debate` to escalate confidence on demand
- submit an oracle label that is a guess

---

## 10. Quick reference

```bash
warf review <path> --json                          # review, machine-readable
warf review <path> --domain SECURITY --json        # override domain
warf review <path> --max-agents 3 --json           # faster, lower confidence ceiling
warf review <path> --fail-on HIGH --json           # CI gate (recommended)
warf review-commit <sha> --fail-on HIGH --json     # gate a commit's changed files
warf weights --json                                # current ω per agent per domain
warf weights --reconcile                           # apply pending persona-version changes
warf label <session-id> --verdict REJECT --json    # close the loop
warf review <path> --no-early-stop --json          # poll every agent: measurement, not review
warf paths                                         # where profiles, log and dashboards live
warf providers                                     # which model backend answers
```

`--max-agents 3` caps the reachable λ. With three agents `HIGH APPROVE` becomes
effectively unreachable (§4), so a run capped this way will never clear a
`--fail-on HIGH` gate on merit — it can only fail or return `MEDIUM`. Use it for a
fast screen, not for a merge gate.

`--no-early-stop` keeps polling after a boundary is crossed. The verdict is
unchanged — the first crossing decides — and every agent votes. `sprt_lambda` then
sums *all* the votes, so a late dissent can leave it back inside the boundaries on a
session that is nevertheless `HIGH`: read `confidence` / `sprt_fired`, never infer
them from λ. The same applies to the debate round's own `sprt_lambda`. Use the flag
when measuring per-agent behaviour (early stopping under-samples low-weight agents),
never to "get more opinions" on a verdict that is already decided.

Exit codes are `0` / `1` / `2` as described in §2. Gate on `--fail-on`, or read
`summary.failing` from the JSON; do not gate on the bare exit code without setting
`--fail-on`, since its default (`LOW`) blocks on verdicts §2 forbids acting on.
Behind an exit `2`, `WARF_TRACEBACK=1` prints the full traceback.

Installation, model providers, where state lives (`.warf/`, `WARF_HOME`), the MCP
server and the Claude Code skill are documented in README.md; this file is only
about reading the output.
