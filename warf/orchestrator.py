"""
WaRF orchestrator — drives the review loop.
Calls the claude CLI for votes (uses subscription quota, not API key).
All math delegated to engine.py.
"""
import concurrent.futures
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .engine import (
    SPRTState, sprt_update, synthesis, bayesian_update, apply_decay,
    Decision, Confidence, THETA, A, B,
)
from .state import AgentProfile, DomainWeight, ORACLE_TIERS, load_profiles, save_profiles
from .sast import bandit_vote, SAST_AGENT_NAME, SAST_OMEGA
from .paths import debug_log_path
from .providers import (
    ProviderError, get_provider, resolve_model, detect_default_provider,
    DEFAULT_TIMEOUT,
)

# Which model answers by default. Per-agent overrides live on the profile
# (AgentProfile.provider / .model); see providers.py for the resolution order.
VOTE_MODEL = "claude-haiku-4-5-20251001"


def _omega_bar(omega: float, width: int = 10) -> str:
    filled = round(omega * width)
    return "█" * filled + "░" * (width - filled)


def _lambda_bar(lambda_val: float, width: int = 28) -> str:
    """Render current L on a fixed B..A scale. Example: ◄B░░░░│░░░▓░░░░░░░░░░A►"""
    total = A - B
    pos      = max(0, min(width - 1, int((lambda_val - B) / total * width)))
    zero_pos = max(0, min(width - 1, int((0.0      - B) / total * width)))
    bar = list("░" * width)
    bar[zero_pos] = "│"
    bar[pos]      = "█"  # overwrites │ if pos == zero_pos
    return f"◄B {''.join(bar)} A►"


@dataclass
class VoteRecord:
    agent_name: str
    vote: int          # +1 APPROVE / -1 REJECT
    omega: float
    reasoning: str
    tokens_in: int = 0
    tokens_out: int = 0
    # Which backend produced this vote. Recorded so a mixed-model panel stays
    # attributable after the fact, and so experiments on one model can be
    # separated from the historical corpus.
    provider: str = ""
    model: str = ""
    # Fingerprint of the persona text that cast this vote (state.persona_hash).
    # apply_oracle refuses feedback for a vote whose persona version has since
    # been retired — otherwise `warf label` on an old session would train the
    # new agent on the old agent's behaviour.
    persona_hash: str = ""


@dataclass
class ReviewResult:
    decision: Decision
    confidence: Confidence
    domain: str
    votes: list[VoteRecord] = field(default_factory=list)
    sprt_lambda: float = 0.0
    normalised_score: float | None = None
    # Debate round 2 (populated only when --debate triggers a second SPRT pass)
    debate_votes: list[VoteRecord] = field(default_factory=list)
    debate_sprt_lambda: float = 0.0
    debate_normalised_score: float | None = None


_DEBUG_LOG: Path | None = None  # set by run_review when debug=True
_DEBUG_LOG_LOCK = threading.Lock()


def _parse_vote(text: str) -> tuple[int, str]:
    first_word = text.split()[0].upper().rstrip(".,:")
    if first_word == "APPROVE":
        vote = 1
    elif first_word == "REJECT":
        vote = -1
    else:
        vote = 1 if re.search(r"\bAPPROVE\b", text, re.IGNORECASE) else -1
    reasoning = text[text.index("\n"):].strip() if "\n" in text else ""
    return vote, reasoning


def _call_agent(
    persona: str,
    code: str,
    domain: str,
    *,
    user_message: str | None = None,
    input_label: str = "Code under review",
    context: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[int, str, int, int, str, str]:
    """Send code to one agent and parse its vote.

    provider/model come from the agent's profile entry when set, otherwise from
    the environment (see providers.detect_default_provider). Passing them per
    call is what lets one panel mix models.

    Returns (vote, reasoning, tokens_in, tokens_out, provider_used, model_used).
    The last two are returned rather than stashed on the module because agents
    are dispatched concurrently.
    """
    if user_message is None:
        ctx_section = f"Project context:\n{context}\n\n" if context else ""
        user_message = (
            f"Domain: {domain}\n\n"
            f"{ctx_section}"
            f"{input_label}:\n```\n{code}\n```\n\n"
            "First line of your response must be exactly one word: APPROVE or REJECT.\n"
            "Subsequent lines: your reasoning."
        )
    if _DEBUG_LOG is not None:
        with _DEBUG_LOG_LOCK, _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n[INPUT len={len(user_message)}]\n{user_message}\n")

    provider_name = provider or detect_default_provider()
    model_name    = resolve_model(provider_name, model)
    backend       = get_provider(provider_name)

    try:
        completion = backend.complete(
            system=persona,
            user=user_message,
            model=model_name,
            timeout=DEFAULT_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        # Surfaced unchanged: run_review treats a timeout as "skip this agent"
        # rather than failing the whole review.
        if _DEBUG_LOG is not None:
            partial_out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            partial_err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            with _DEBUG_LOG_LOCK, _DEBUG_LOG.open("a", encoding="utf-8") as f:
                f.write(f"[TIMEOUT]\npartial_stdout: {partial_out!r}\npartial_stderr: {partial_err!r}\n")
        raise
    except ProviderError as exc:
        if _DEBUG_LOG is not None:
            with _DEBUG_LOG_LOCK, _DEBUG_LOG.open("a", encoding="utf-8") as f:
                f.write(f"[PROVIDER ERROR {provider_name}/{model_name}] {exc}\n")
        raise RuntimeError(f"[{provider_name}/{model_name}] {exc}") from exc

    if _DEBUG_LOG is not None:
        with _DEBUG_LOG_LOCK, _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{provider_name}/{model_name}]\n[OUTPUT]\n{completion.text}\n")

    vote, reasoning = _parse_vote(completion.text)
    return (vote, reasoning, completion.tokens_in, completion.tokens_out,
            provider_name, model_name)


def _effective_omega(profile: AgentProfile, domain: str) -> float:
    """
    Return the decay-adjusted weight for this agent in this domain.

    If the agent has never received oracle feedback (last_updated is None),
    no decay is applied — there is nothing to decay from.
    """
    w = profile.weights[domain]
    if profile.last_updated is None:
        return w.omega
    last = datetime.fromisoformat(profile.last_updated)
    now  = datetime.now(timezone.utc)
    weeks = (now - last).total_seconds() / (7 * 24 * 3600)
    alpha_eff, beta_eff = apply_decay(w.alpha, w.beta, weeks)
    return alpha_eff / (alpha_eff + beta_eff)


def _build_debate_prompt(
    code: str,
    domain: str,
    round1_votes: list[VoteRecord],
    agent_name: str,
    context: str | None = None,
) -> str:
    """
    Construct a per-agent Round-2 prompt.

    Each agent sees its own Round-1 vote explicitly (anchor) and the other
    agents' votes. The instruction is neutral: maintain OR revise, and
    explicitly asks the agent to explain what is wrong in others' reasoning
    if it keeps its position.
    """
    own   = next(v for v in round1_votes if v.agent_name == agent_name)
    own_label = "APPROVE" if own.vote == 1 else "REJECT"

    others = [v for v in round1_votes if v.agent_name != agent_name and v.agent_name != SAST_AGENT_NAME]
    other_lines = []
    for v in others:
        label   = "APPROVE" if v.vote == 1 else "REJECT"
        excerpt = v.reasoning[:300].replace("\n", " ") if v.reasoning else "(no reasoning)"
        other_lines.append(f"- {v.agent_name}: {label}\n  Reasoning: {excerpt}")
    others_text = "\n".join(other_lines)

    ctx_section = f"Project context:\n{context}\n\n" if context else ""
    return (
        f"Domain: {domain}\n\n"
        f"{ctx_section}"
        f"Code under review:\n```\n{code}\n```\n\n"
        "=== Round 1 Summary ===\n"
        f"Your Round 1 vote: {own_label}\n\n"
        f"Other agents voted:\n{others_text}\n\n"
        "=== Your Turn ===\n"
        "Critically evaluate the other agents' reasoning:\n"
        "- If their reasoning reveals a genuine technical error in your own analysis, "
        "revise your vote and explain what convinced you.\n"
        "- If their reasoning contains misconceptions or factual errors, "
        "maintain your position and explain specifically what they got wrong.\n"
        "- Do NOT change your vote simply because others disagree with you.\n\n"
        "First line of your response must be exactly one word: APPROVE or REJECT.\n"
        "Subsequent lines: your reasoning."
    )


def _run_debate_round(
    profiles: list[AgentProfile],
    code: str,
    domain: str,
    round1_votes: list[VoteRecord],
    verbose: bool,
    demo: bool = False,
    context: str | None = None,
    no_early_stop: bool = False,
) -> tuple[list[VoteRecord], float, Decision, Confidence, float | None]:
    """
    Run Round 2 (debate). Λ resets to 0; weights frozen at Round-1 values.
    Returns (votes, sprt_lambda, decision, confidence, normalised_score_or_None).
    no_early_stop has the same meaning as in run_review: keep polling after a
    boundary is crossed so every agent's Round-2 position is recorded.
    """
    r1_vote_map  = {v.agent_name: v.vote  for v in round1_votes}
    r1_omega_map = {v.agent_name: v.omega for v in round1_votes}

    sprt_state = SPRTState()
    votes: list[VoteRecord] = []
    early_decision: Decision | None = None

    # --- Sequential debate calls ------------------------------------------
    for profile in profiles:
        if profile.name not in r1_vote_map:
            # Timed out in Round 1. The debate asks an agent to maintain or revise
            # its own position and this one has none, so it sits the round out —
            # rather than bringing the whole review down on the lookup below.
            if verbose:
                print(f"  [D2][{profile.name}] no Round-1 vote (timed out) — not polled")
            continue
        omega = r1_omega_map[profile.name]
        debate_msg = _build_debate_prompt(code, domain, round1_votes, agent_name=profile.name, context=context)

        if verbose:
            print(f"  [D2][{profile.name}] omega={omega:.3f}  querying...")

        t0 = time.time()
        try:
            vote, reasoning, tok_in, tok_out, prov_used, model_used = _call_agent(
                profile.persona, code, domain, user_message=debate_msg,
                provider=profile.provider, model=profile.model,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - t0
            if verbose:
                print(f"  [D2][{profile.name}] TIMEOUT ({elapsed:.1f}s) — skipping agent")
            continue
        elapsed = time.time() - t0
        label   = "APPROVE" if vote == 1 else "REJECT"
        changed = vote != r1_vote_map.get(profile.name)

        if verbose:
            tag = "  [CHANGED]" if changed else ""
            print(f"  [D2][{profile.name}] -> {label}{tag}  ({elapsed:.1f}s)")
            if reasoning:
                excerpt = reasoning[:120].replace("\n", " ")
                print(f"      {excerpt}{'...' if len(reasoning) > 120 else ''}")

        votes.append(VoteRecord(
            agent_name=profile.name, vote=vote, omega=omega,
            reasoning=reasoning, tokens_in=tok_in, tokens_out=tok_out,
            provider=prov_used, model=model_used,
            persona_hash=profile.persona_hash or "",
        ))

        sprt_state, boundary = sprt_update(sprt_state, vote, omega)
        if boundary is not None:
            if verbose:
                print(f"  [D2] SPRT boundary crossed "
                      f"(L={sprt_state.lambda_:.3f}): {boundary.value} [HIGH]"
                      + ("  — continuing, early stop disabled" if no_early_stop else ""))
            # Same rule as Round 1: the first crossing is the decision; under
            # no_early_stop every agent still gets to vote.
            if early_decision is None:
                early_decision = boundary
            if not no_early_stop:
                break

    if not votes:
        raise RuntimeError("All debate agents timed out — no votes collected")

    if early_decision is not None:
        return votes, sprt_state.lambda_, early_decision, Confidence.HIGH, None

    vote_list   = [v.vote  for v in votes]
    weight_list = [v.omega for v in votes]
    d_decision, d_confidence, d_norm = synthesis(vote_list, weight_list, domain)

    if verbose:
        theta = THETA[domain]
        print(f"  [D2] Pool exhausted  L={sprt_state.lambda_:.3f}  "
              f"normalised={d_norm:.3f}  theta={theta}  margin={abs(d_norm - theta):.3f}")
        print(f"  [D2] -> {d_decision.value} [{d_confidence.value}]")

    return votes, sprt_state.lambda_, d_decision, d_confidence, d_norm


def run_review(
    code: str,
    domain: str,
    profiles_path: Path,
    verbose: bool = True,
    debate: bool = False,
    input_label: str = "Code under review",
    debug: bool = False,
    demo: bool = False,
    reason: bool = False,
    context: str | None = None,
    sast_path: Path | None = None,
    agents: list[str] | None = None,
    max_agents: int | None = None,
    no_early_stop: bool = False,
) -> ReviewResult:
    """
    Run a full WaRF review session.

    Agents are queried in descending weight order (heaviest first) for SPRT efficiency.
    Returns a ReviewResult; does NOT update weights (call apply_oracle for that).

    no_early_stop keeps polling after a boundary is crossed. The verdict is
    unchanged — it is still the boundary that fired — but every agent votes, which
    is required when measuring per-agent discrimination rather than running a
    review for its own sake.
    """
    global _DEBUG_LOG
    if debug:
        _DEBUG_LOG = debug_log_path()
        print(f"  [debug] logging to {_DEBUG_LOG}")
    else:
        _DEBUG_LOG = None

    profiles = load_profiles(profiles_path)

    # Heaviest effective weight in this domain goes first — maximises SPRT early-stop probability
    profiles.sort(key=lambda p: _effective_omega(p, domain), reverse=True)

    # --agents: explicit developer-specified pool (case-insensitive name match)
    if agents is not None:
        names_upper = {n.upper() for n in agents}
        profiles = [p for p in profiles if p.name.upper() in names_upper]
        if not profiles:
            raise RuntimeError(f"--agents filter matched no loaded profiles: {agents}")
    # --max-agents: ω-ranked cutoff after sort (weight-informed top-N)
    elif max_agents is not None:
        if max_agents < 1:
            raise RuntimeError(f"--max-agents must be a positive integer, got {max_agents}")
        profiles = profiles[:max_agents]

    # --- Sequential agent calls (heaviest omega first for SPRT efficiency) -
    sprt_state = SPRTState()
    votes: list[VoteRecord] = []
    early_decision: Decision | None = None
    agent_timings: list[dict] = []

    # --- SAST pre-vote (SECURITY domain only, fixed ω, no LLM call) ----------
    if sast_path is not None and domain == "SECURITY":
        sast_result = bandit_vote(sast_path)
        if sast_result is None:
            if verbose or demo:
                print("  [sast] bandit not installed — SAST vote skipped.")
        else:
            sast_v, sast_r, sast_high, sast_total = sast_result
            sast_label = "APPROVE" if sast_v == 1 else "REJECT"
            count_note = f"{sast_high} HIGH finding(s)" if sast_high else "clean"

            sast_record = VoteRecord(
                agent_name=SAST_AGENT_NAME,
                vote=sast_v,
                omega=SAST_OMEGA,
                reasoning=sast_r,
            )
            votes.append(sast_record)
            agent_timings.append({"name": SAST_AGENT_NAME, "elapsed": 0.0, "timed_out": False})

            lambda_before = sprt_state.lambda_
            sprt_state, boundary = sprt_update(sprt_state, sast_v, SAST_OMEGA)
            delta = sprt_state.lambda_ - lambda_before

            if verbose:
                print(f"  [SAST-BANDIT] -> {sast_label}  (bandit, {sast_total} finding(s))  Δλ={delta:+.3f}  L={sprt_state.lambda_:+.3f}")
                if sast_r != "No security findings detected.":
                    print(f"  {'─' * 40}")
                    for line in sast_r.splitlines():
                        print(f"      {line}")
                    print(f"  {'─' * 40}")
            elif demo:
                bar = _omega_bar(SAST_OMEGA)
                print(f"  {'SAST-BANDIT':<14} {sast_label:<7}  ω={SAST_OMEGA:.3f}  {bar}  Δλ={delta:+.3f}  L={sprt_state.lambda_:+.3f}  ({count_note})")
                print(f"  {' ' * 14} {_lambda_bar(sprt_state.lambda_)}")

            if boundary is not None:
                skipped = len(profiles)
                if verbose:
                    print(f"  SPRT boundary crossed at k=1 (L={sprt_state.lambda_:.3f}): {boundary.value} [HIGH]  ({skipped} LLM agent(s) skipped)")
                if demo:
                    print(f"  {'─' * 56}")
                    print(f"  SPRT → {boundary.value} [HIGH]  1 agent (SAST only — {skipped} LLM skipped)")
                early_decision = boundary

    for i, profile in enumerate(profiles):
        # early_decision may already be set by the SAST pre-vote above, or by a
        # boundary crossed on a previous iteration. Under no_early_stop the
        # decision is recorded but polling continues, so this guard must respect
        # it too — otherwise the loop exits here and the flag silently does nothing.
        if early_decision is not None and not no_early_stop:
            break
        omega = _effective_omega(profile, domain)

        if verbose:
            print(f"  [{profile.name}] omega={omega:.3f}  querying...")
        elif demo:
            print(f"  {profile.name:<14} …", end="", flush=True)

        t0 = time.time()
        try:
            vote, reasoning, tok_in, tok_out, prov_used, model_used = _call_agent(
                profile.persona, code, domain, input_label=input_label, context=context,
                provider=profile.provider, model=profile.model,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - t0
            agent_timings.append({"name": profile.name, "elapsed": elapsed, "timed_out": True})
            if verbose:
                print(f"  [{profile.name}] TIMEOUT ({elapsed:.1f}s) — skipping agent")
            elif demo:
                print(f"\r  {profile.name:<14} TIMEOUT  ({elapsed:.0f}s)")
            continue
        elapsed = time.time() - t0
        agent_timings.append({"name": profile.name, "elapsed": elapsed, "timed_out": False})
        label = "APPROVE" if vote == 1 else "REJECT"

        lambda_before = sprt_state.lambda_
        sprt_state, boundary = sprt_update(sprt_state, vote, omega)
        delta = sprt_state.lambda_ - lambda_before

        if demo:
            bar = _omega_bar(omega)
            print(f"\r  {profile.name:<14} {label:<7}  ω={omega:.3f}  {bar}  Δλ={delta:+.3f}  L={sprt_state.lambda_:+.3f}")
            print(f"  {' ' * 14} {_lambda_bar(sprt_state.lambda_)}")
            if reason and reasoning:
                lines = [l for l in reasoning.splitlines() if l.strip()][:2]
                for line in lines:
                    clean = re.sub(r'^#{1,6}\s*', '', re.sub(r'\*+([^*]+)\*+', r'\1', line))
                    print(f"      {clean[:120]}{'…' if len(clean) > 120 else ''}")

        if verbose:
            print(f"  [{profile.name}] -> {label}  ({elapsed:.1f}s)  Δλ={delta:+.3f}  L={sprt_state.lambda_:+.3f}")
            if reasoning:
                print(f"  {'─' * 40}")
                for line in reasoning.splitlines():
                    print(f"      {line}")
                print(f"  {'─' * 40}")

        votes.append(VoteRecord(
            agent_name=profile.name,
            vote=vote,
            omega=omega,
            reasoning=reasoning,
            tokens_in=tok_in,
            tokens_out=tok_out,
            provider=prov_used,
            model=model_used,
            persona_hash=profile.persona_hash or "",
        ))

        if boundary is not None:
            if no_early_stop:
                # Experiment mode: record that the boundary was reached but keep
                # polling, so every agent produces a vote. Without this, low-omega
                # agents are systematically under-sampled and their measured
                # discrimination cannot be compared with the rest of the panel.
                if early_decision is None:
                    early_decision = boundary
                    if verbose:
                        print(f"  SPRT boundary crossed at k={sprt_state.k} "
                              f"(L={sprt_state.lambda_:.3f}): {boundary.value} [HIGH] "
                              f"— continuing, early stop disabled")
                continue
            skipped = len(profiles) - i - 1
            if verbose:
                msg = f"  SPRT boundary crossed at k={sprt_state.k} (L={sprt_state.lambda_:.3f}): {boundary.value} [HIGH]"
                if skipped:
                    msg += f"  ({skipped} agent(s) not queried)"
                print(msg)
            if demo:
                print(f"  {'─' * 56}")
                print(f"  {' ' * 14} {_lambda_bar(sprt_state.lambda_)}")
                msg = f"  SPRT → {boundary.value} [HIGH]  {i + 1}/{len(profiles)} agents"
                if skipped:
                    msg += f"  — {skipped} skipped"
                print(msg)
            early_decision = boundary
            break

    if not votes:
        raise RuntimeError("All agents timed out — no votes collected")

    # ── Time analysis ────────────────────────────────────────────────────────
    if verbose and agent_timings:
        responded  = [t for t in agent_timings if not t["timed_out"]]
        timed_out  = [t for t in agent_timings if t["timed_out"]]
        total_wall = sum(t["elapsed"] for t in agent_timings)
        avg = sum(t["elapsed"] for t in responded) / len(responded) if responded else 0.0
        print(f"\n  {'─' * 46}")
        print(f"  {'Agent':<14}  {'Time':>6}  Status")
        print(f"  {'─' * 46}")
        for t in agent_timings:
            status = "✗ timeout" if t["timed_out"] else "✓"
            print(f"  {t['name']:<14}  {t['elapsed']:>5.1f}s  {status}")
        print(f"  {'─' * 46}")
        print(f"  {'Total wall':<14}  {total_wall:>5.1f}s")
        print(f"  {'Voted':<14}  {len(responded)}/{len(agent_timings)}   avg {avg:.1f}s")
        if timed_out:
            names = ", ".join(t["name"] for t in timed_out)
            print(f"  {'Timed out':<14}  {len(timed_out)}   [{names}]")
        print(f"  {'─' * 46}\n")
    elif demo and agent_timings:
        timed_out = [t for t in agent_timings if t["timed_out"]]
        total = sum(t["elapsed"] for t in agent_timings)
        print(f"  {'─' * 56}")
        if timed_out:
            print(f"  {total:.0f}s total  — {len(timed_out)} timeout(s): {', '.join(t['name'] for t in timed_out)}")
        else:
            print(f"  {total:.0f}s total  — all {len(agent_timings)} agents responded")

    if early_decision is not None:
        return ReviewResult(
            decision=early_decision,
            confidence=Confidence.HIGH,
            domain=domain,
            votes=votes,
            sprt_lambda=sprt_state.lambda_,
        )

    # Pool exhausted — fall back to synthesis
    vote_list   = [v.vote  for v in votes]
    weight_list = [v.omega for v in votes]
    decision, confidence, norm = synthesis(vote_list, weight_list, domain)

    if verbose:
        theta = THETA[domain]
        print(f"  Pool exhausted  L={sprt_state.lambda_:.3f}  "
              f"normalised={norm:.3f}  theta={theta}  margin={abs(norm - theta):.3f}")
        print(f"  -> {decision.value} [{confidence.value}]")

    # Debate round — §3.3.2: triggered only when Round 1 pool is exhausted and debate=True
    if debate:
        if verbose:
            print(f"\n{'=' * 42}")
            print("  DEBATE ROUND 2")
            print(f"{'=' * 42}\n")
        d_votes, d_lam, d_decision, d_confidence, d_norm = _run_debate_round(
            profiles, code, domain, votes, verbose, demo, context=context,
            no_early_stop=no_early_stop,
        )
        return ReviewResult(
            decision=d_decision,
            confidence=d_confidence,
            domain=domain,
            votes=votes,
            sprt_lambda=sprt_state.lambda_,
            normalised_score=norm,
            debate_votes=d_votes,
            debate_sprt_lambda=d_lam,
            debate_normalised_score=d_norm,
        )

    return ReviewResult(
        decision=decision,
        confidence=confidence,
        domain=domain,
        votes=votes,
        sprt_lambda=sprt_state.lambda_,
        normalised_score=norm,
    )


def apply_oracle(
    result: ReviewResult,
    x_star: int,
    oracle_type: str,
    profiles_path: Path,
    verbose: bool = True,
) -> list[dict]:
    """
    Update agent weights given developer ground truth.

    x_star:      +1 (APPROVE) or -1 (REJECT)
    oracle_type: key in ORACLE_TIERS

    Returns a list of weight-update records for session logging.
    """
    gamma = ORACLE_TIERS[oracle_type]
    profiles = load_profiles(profiles_path)
    profile_map = {p.name: p for p in profiles}
    updates: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # §3.3.5: oracle credits the final epistemic position — use Round 2 votes when debate ran
    votes_to_score = result.debate_votes if result.debate_votes else result.votes

    for v in votes_to_score:
        if v.agent_name not in profile_map:
            continue  # skip virtual agents (e.g., SAST-BANDIT)
        profile = profile_map[v.agent_name]
        w = profile.weights[result.domain]
        correct = (v.vote == x_star)

        if v.persona_hash and profile.persona_hash and v.persona_hash != profile.persona_hash:
            # This vote was cast by a persona version that has since been
            # retired. Crediting or penalising the CURRENT weights for it would
            # train the new agent on the old agent's behaviour. Record the
            # outcome for the log; leave the weights alone. The entry keeps the
            # full shape (alpha/beta/omega unchanged) so dashboard consumers that
            # index those keys keep working; "skipped" marks it for filtering.
            updates.append({
                "agent":           v.agent_name,
                "correct":         correct,
                "alpha_after":     round(w.alpha, 4),
                "beta_after":      round(w.beta,  4),
                "omega_after":     round(w.omega, 4),
                "skipped":         "persona_changed",
                "vote_persona":    v.persona_hash,
                "profile_persona": profile.persona_hash,
            })
            if verbose:
                print(f"  {profile.name}: SKIPPED  vote cast by persona {v.persona_hash}, "
                      f"current weights belong to {profile.persona_hash}")
            continue

        new_alpha, new_beta = bayesian_update(w.alpha, w.beta, correct, gamma)
        new_omega = new_alpha / (new_alpha + new_beta)
        profile.weights[result.domain] = DomainWeight(alpha=new_alpha, beta=new_beta)
        profile.last_updated = now_iso
        updates.append({
            "agent":       v.agent_name,
            "correct":     correct,
            "alpha_after": round(new_alpha, 4),
            "beta_after":  round(new_beta,  4),
            "omega_after": round(new_omega, 4),
        })

        if verbose:
            mark = "OK" if correct else "WRONG"
            print(f"  {profile.name}: {mark}  "
                  f"alpha={new_alpha:.2f}  beta={new_beta:.2f}  omega={new_omega:.3f}")

    save_profiles(profiles_path, list(profile_map.values()))

    if verbose:
        print(f"  Saved -> {profiles_path}")

    return updates
