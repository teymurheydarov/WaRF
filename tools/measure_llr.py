"""
Measure the empirical P1/P0 that the SPRT log-likelihood ratios assume.

    P1 = P(agent votes APPROVE | ground truth is APPROVE)
    P0 = P(agent votes APPROVE | ground truth is REJECT)

engine.py currently *assumes* P1=0.80, P0=0.30. Those numbers were chosen, not
measured, and they set the LLR magnitudes -> how fast lambda moves -> how often
SPRT fires -> how much HIGH confidence ever appears. Every lambda in the corpus
is scaled by them.

This script measures them from oracle-labelled sessions, derives what the SPRT
constants would be, and replays every session to show how many verdicts would
actually change.

Zero API cost: reads sessions.jsonl only.

Usage:
    py tools/measure_llr.py
    py tools/measure_llr.py --domain SECURITY
    py tools/measure_llr.py --profile legacy          # the original corpus only
    py tools/measure_llr.py --persona 2ad809ed        # one version of one agent's prompt

Every run that finds versioned votes ends with a per-persona-version table, which
is how a prompt edit is compared with the text it replaced.
"""
import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

# A dev tool, not part of the package: make the checkout importable and use
# absolute imports. Works against an installed warf as well.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warf.engine import (  # noqa: E402
    P1, P0, ALPHA_ERR, BETA_ERR, A, B,
    LLR_APPROVE, LLR_REJECT, THETA,
)
from warf.paths import sessions_path  # noqa: E402

SESSIONS = sessions_path()

# --profile legacy: sessions logged before the profile field existed, i.e. the
# original corpus reviewed by the old personas. They carry no profile at all.
LEGACY = "legacy"

# Agents with no profile entry (e.g. SAST-BANDIT) are excluded, matching
# apply_oracle(), which skips them when crediting the oracle.
VIRTUAL_AGENTS = {"SAST-BANDIT"}


# ── counting ─────────────────────────────────────────────────────────────────

class Tally:
    """APPROVE-vote counts split by ground truth."""

    def __init__(self) -> None:
        self.approve_given_good = 0   # numerator of P1
        self.n_good             = 0   # denominator of P1
        self.approve_given_bad  = 0   # numerator of P0
        self.n_bad              = 0   # denominator of P0

    def add(self, vote: int, x_star: int) -> None:
        if x_star == 1:
            self.n_good += 1
            self.approve_given_good += (vote == 1)
        else:
            self.n_bad += 1
            self.approve_given_bad += (vote == 1)

    @property
    def p1(self) -> float | None:
        return self.approve_given_good / self.n_good if self.n_good else None

    @property
    def p0(self) -> float | None:
        return self.approve_given_bad / self.n_bad if self.n_bad else None

    @property
    def n(self) -> int:
        return self.n_good + self.n_bad


def _scored_votes(session: dict) -> list[dict]:
    """The votes the oracle actually credits: Round 2 when a debate ran, else Round 1."""
    debate = session.get("debate")
    if debate and debate.get("votes"):
        return debate["votes"]
    return session.get("votes", [])


def _persona(vote: dict) -> str | None:
    """The persona version a vote was cast under; None for votes logged before
    persona versioning (the logger writes "" when the hash is unknown)."""
    return vote.get("persona") or None


def _countable(vote: dict) -> bool:
    return vote.get("agent") not in VIRTUAL_AGENTS and vote.get("vote") in (1, -1)


def collect(domain_filter: str | None,
            profile_filter: str | None = None,
            dedupe: bool = True,
            persona_filter: str | None = None) -> tuple[Tally, dict, dict, list[dict], dict]:
    """Return (global tally, per-domain tallies, per-agent tallies, labelled
    sessions, per-persona-version tallies keyed (agent, persona hash or None)).

    profile_filter segments the corpus by the panel that produced it, which is what
    makes a persona or model change measurable against the previous baseline.
    Sessions logged before the `profile` field existed carry None and are matched
    only when no filter is given.

    persona_filter (a full hash) narrows everything but the per-persona tallies to
    the votes cast under that one persona version, and the sessions to those in
    which it voted.
    """
    overall    = Tally()
    by_domain  = defaultdict(Tally)
    by_agent   = defaultdict(Tally)
    by_persona = defaultdict(Tally)     # insertion order = first seen in the log
    labelled   = []

    if not SESSIONS.exists():
        return overall, by_domain, by_agent, labelled, by_persona

    with SESSIONS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
            except json.JSONDecodeError:
                continue

            oracle = s.get("oracle")
            if not oracle or oracle.get("x_star") is None:
                continue
            domain = s.get("domain", "?")
            if domain_filter and domain != domain_filter:
                continue
            if profile_filter == LEGACY:
                # Sessions logged before the profile field existed: the original
                # corpus (old personas). They carry no profile at all.
                if s.get("profile") is not None:
                    continue
            elif profile_filter and s.get("profile") != profile_filter:
                continue

            labelled.append(s)

    # Per persona version — tallied before the session-level dedupe below. That
    # dedupe keeps the latest session per (profile, artifact), so once a prompt has
    # been edited and the files re-reviewed it would discard exactly the sessions
    # that hold the previous version's votes. Here the unit is the vote: the latest
    # one each persona version cast on each artifact.
    latest_vote: dict[tuple, tuple[int, int]] = {}
    for s in labelled:
        for v in _scored_votes(s):
            if not _countable(v):
                continue
            by_persona[(v["agent"], _persona(v))]   # registers first-seen order
            key = (s.get("profile"), s.get("artifact"), v["agent"], _persona(v))
            if dedupe:
                latest_vote[key] = (v["vote"], s["oracle"]["x_star"])
            else:
                by_persona[(v["agent"], _persona(v))].add(v["vote"], s["oracle"]["x_star"])
    for (_, _, agent, persona), (vote, x_star) in latest_vote.items():
        by_persona[(agent, persona)].add(vote, x_star)

    if persona_filter:
        labelled = [s for s in labelled
                    if any(_countable(v) and _persona(v) == persona_filter
                           for v in _scored_votes(s))]

    if dedupe:
        # Keep only the most recent session per (profile, artifact). Re-reviewing
        # one file produces correlated observations, not independent samples, and
        # a superseded partial run would otherwise be counted alongside the
        # complete re-run that replaced it.
        latest: dict[tuple, dict] = {}
        for s in labelled:
            latest[(s.get("profile"), s.get("artifact"))] = s
        labelled = list(latest.values())

    for s in labelled:
        x_star = s["oracle"]["x_star"]
        domain = s.get("domain", "?")

        for v in _scored_votes(s):
            if not _countable(v):
                continue
            if persona_filter and _persona(v) != persona_filter:
                continue
            vote = v["vote"]
            overall.add(vote, x_star)
            by_domain[domain].add(vote, x_star)
            by_agent[v["agent"]].add(vote, x_star)

    return overall, by_domain, by_agent, labelled, by_persona


# ── derived constants ────────────────────────────────────────────────────────

def derivable(p1: float | None, p0: float | None) -> bool:
    """Both rates measured and strictly inside (0, 1).

    At exactly 0 or 1 the log-likelihood ratio is unbounded — a vote that never
    erred on the sample would carry infinite evidence — which on a small sample
    is an artefact of n, not a property of the agent.
    """
    return p1 is not None and p0 is not None and 0.0 < p1 < 1.0 and 0.0 < p0 < 1.0


def derive(p1: float, p0: float) -> dict:
    """SPRT constants implied by a given (P1, P0). Requires derivable(p1, p0)."""
    return {
        "p1":           p1,
        "p0":           p0,
        "llr_approve":  math.log(p1 / p0),
        "llr_reject":   math.log((1 - p1) / (1 - p0)),
        "A":            math.log((1 - BETA_ERR) / ALPHA_ERR),   # unchanged by P1/P0
        "B":            math.log(BETA_ERR / (1 - ALPHA_ERR)),
    }


def replay(session: dict, llr_approve: float, llr_reject: float,
           a_bound: float, b_bound: float) -> tuple[str, str, float]:
    """Re-run one session's SPRT with alternative LLR values.

    Mirrors engine.sprt_update / engine.synthesis exactly: votes are consumed in
    stored order (descending omega) and the run stops at the first boundary cross.
    Returns (decision, confidence, lambda).
    """
    votes = _scored_votes(session)
    lam = 0.0
    for v in votes:
        vote  = v.get("vote")
        omega = v.get("omega", 0.0)
        if vote not in (1, -1):
            continue
        lam += omega * (llr_approve if vote == 1 else llr_reject)
        if lam >= a_bound:
            return "APPROVE", "HIGH", lam
        if lam <= b_bound:
            return "REJECT", "HIGH", lam

    # Pool exhausted -> weighted-average fallback
    weights = [v.get("omega", 0.0) for v in votes if v.get("vote") in (1, -1)]
    signs   = [v["vote"] for v in votes if v.get("vote") in (1, -1)]
    if not weights or sum(weights) == 0:
        return "APPROVE", "LOW", lam
    theta      = THETA.get(session.get("domain", "LOGIC"), 0.0)
    normalised = sum(w * s for w, s in zip(weights, signs)) / sum(weights)
    margin     = abs(normalised - theta)
    decision   = "APPROVE" if normalised >= theta else "REJECT"
    confidence = "MEDIUM" if margin >= 0.2 else "LOW"
    return decision, confidence, lam


# ── reporting ────────────────────────────────────────────────────────────────

def _pct(x: float | None) -> str:
    return "  n/a " if x is None else f"{x:6.3f}"


def _needed(bound: float, step: float) -> str:
    """Agreeing votes needed to cover `bound` in steps of `step`; 'never' when a
    vote does not move lambda towards the boundary at all (P1 <= P0)."""
    return str(math.ceil(bound / step)) if step > 0 else "never"


def _sep(t: Tally) -> str:
    return f"{t.p1 - t.p0:+.3f}" if (t.p1 is not None and t.p0 is not None) else "n/a"


def _persona_label(persona: str | None) -> str:
    return persona or "(unversioned)"


def resolve_persona(prefix: str, by_persona: dict) -> tuple[str, str]:
    """Expand a hash prefix to (agent, full hash), git-style. Exits with the
    candidates when it matches nothing or more than one version."""
    prefix  = prefix.strip().lower()
    known   = [(agent, p) for (agent, p) in by_persona if p]
    matches = [(agent, p) for (agent, p) in known if p.startswith(prefix)]
    if len({p for _, p in matches}) == 1:
        # One text can in principle serve two agents; the filter is the hash.
        return " + ".join(agent for agent, _ in matches), matches[0][1]

    print()
    if not known:
        print(f"  --persona {prefix}: no vote in scope carries a persona version.")
        print("  Sessions logged before persona versioning cannot be segmented this way;")
        print("  use --profile to compare the panels that produced them.")
    else:
        what = "is ambiguous" if matches else "matches nothing"
        print(f"  --persona {prefix} {what}. Versions in scope:")
        for agent, p in (matches or known):
            print(f"      {p}   {agent:<14} {by_persona[(agent, p)].n} votes")
    print()
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Measure empirical P1/P0 from oracle-labelled sessions.")
    ap.add_argument("--domain", default=None, choices=list(THETA),
                    help="Restrict to one domain (default: all)")
    ap.add_argument("--min-votes", type=int, default=10, metavar="N",
                    help="Suppress per-agent rows with fewer than N scored votes (default: 10)")
    ap.add_argument("--profile", default=None, metavar="NAME",
                    help="Only score sessions produced by this profile, so a persona "
                         "or model change can be compared against the old baseline. "
                         "'legacy' = sessions logged before profiles were recorded "
                         "(the original corpus)")
    ap.add_argument("--persona", default=None, metavar="HASH",
                    help="Only score the votes cast under this persona version (a hash "
                         "prefix is enough; the per-persona table of any run lists them). "
                         "Measures one version of one agent's prompt, so the panel-level "
                         "sections are omitted")
    ap.add_argument("--no-dedupe", dest="dedupe", action="store_false", default=True,
                    help="Count every logged session, including superseded re-reviews "
                         "of the same artifact (default: keep only the latest per file)")
    ap.add_argument("--home", default=None, metavar="DIR",
                    help="Read <DIR>/sessions.jsonl instead of the resolved data directory, "
                         "e.g. --home .warf-experiments for the persona experiments. Safer "
                         "than exporting WARF_HOME, which would silently redirect every "
                         "other warf command in that shell as well")
    args = ap.parse_args()

    if args.home:
        # collect() reads the module-level SESSIONS.
        globals()["SESSIONS"] = Path(args.home) / "sessions.jsonl"

    persona = persona_agent = None
    if args.persona:
        *_, versions = collect(args.domain, args.profile, args.dedupe)
        persona_agent, persona = resolve_persona(args.persona, versions)

    overall, by_domain, by_agent, labelled, by_persona = collect(
        args.domain, args.profile, args.dedupe, persona)

    scope = "".join(filter(None, [
        f" [{args.domain}]" if args.domain else "",
        f" [profile={args.profile}]" if args.profile else "",
        f" [persona={persona} {persona_agent}]" if persona else "",
    ]))
    print(f"\n{'=' * 72}")
    print(f"  Empirical P1/P0 measurement{scope}")
    print(f"{'=' * 72}\n")

    if overall.n == 0:
        print("  No oracle-labelled sessions found. Nothing to measure.")
        print("  Label some sessions first:  warf label <id> --verdict APPROVE|REJECT\n")
        return

    print(f"  Labelled sessions : {len(labelled)}")
    print(f"  Scored votes      : {overall.n}"
          f"   ({overall.n_good} on APPROVE-truth, {overall.n_bad} on REJECT-truth)")

    if overall.n_good < 30 or overall.n_bad < 30:
        print("\n  !  Small sample. Treat the numbers below as directional, not settled.")

    # ── global ───────────────────────────────────────────────────────────────
    measured = derive(overall.p1, overall.p0) if derivable(overall.p1, overall.p0) else None

    print(f"\n{'-' * 72}")
    print(f"  {'':<16}{'ASSUMED':>12}{'MEASURED':>12}{'DELTA':>12}")
    print(f"{'-' * 72}")
    for label, assumed, got in (("P1", P1, overall.p1), ("P0", P0, overall.p0)):
        delta = f"{got - assumed:>+12.3f}" if got is not None else f"{'n/a':>12}"
        print(f"  {label:<16}{assumed:>12.3f}{_pct(got):>12}{delta}")

    if measured is None:
        if overall.p1 is None or overall.p0 is None:
            print("\n  Cannot derive LLRs: one of the two conditions has no votes.")
        else:
            print("\n  Cannot derive LLRs: a rate of exactly 0 or 1 makes the log-likelihood")
            print("  ratio unbounded. On a sample this small that is an artefact of n, not")
            print("  evidence of an infallible vote. More labelled sessions are needed.")
    else:
        print(f"  {'LLR_APPROVE':<16}{LLR_APPROVE:>12.3f}{measured['llr_approve']:>12.3f}"
              f"{measured['llr_approve'] - LLR_APPROVE:>+12.3f}")
        print(f"  {'LLR_REJECT':<16}{LLR_REJECT:>12.3f}{measured['llr_reject']:>12.3f}"
              f"{measured['llr_reject'] - LLR_REJECT:>+12.3f}")
        print(f"\n  Boundaries A={A:+.3f} / B={B:+.3f} are set by alpha/beta only;")
        print(f"  they do not move when P1/P0 change. Only the step size does.")

    if persona:
        print(f"\n  --persona measures one version of one agent's prompt. The panel-level")
        print(f"  sections (agents needed to reach HIGH, session replay) assume these rates")
        print(f"  hold for every agent, so they are omitted here.")
    elif measured is not None:
        # How many agreeing agents to cross, at a representative omega
        for om in (0.5, 0.7):
            old_r = _needed(-B, om * -LLR_REJECT)
            new_r = _needed(-B, om * -measured["llr_reject"])
            old_a = _needed(A, om * LLR_APPROVE)
            new_a = _needed(A, om * measured["llr_approve"])
            print(f"\n  At omega={om}:  agents needed to reach HIGH")
            print(f"      REJECT : {old_r} (assumed)  ->  {new_r} (measured)")
            print(f"      APPROVE: {old_a} (assumed)  ->  {new_a} (measured)")

    # ── per domain ───────────────────────────────────────────────────────────
    if len(by_domain) > 1:
        print(f"\n{'-' * 72}")
        print(f"  Per domain")
        print(f"{'-' * 72}")
        print(f"  {'DOMAIN':<14}{'P1':>8}{'P0':>8}{'votes':>8}   {'separation':>10}")
        for dom, t in sorted(by_domain.items()):
            print(f"  {dom:<14}{_pct(t.p1):>8}{_pct(t.p0):>8}{t.n:>8}   {_sep(t):>10}")

    # ── per agent ────────────────────────────────────────────────────────────
    # Under --persona there is one agent and its row would repeat the table above.
    if not persona:
        print(f"\n{'-' * 72}")
        print(f"  Per agent  (tests the 'P1/P0 are global' assumption)")
        print(f"{'-' * 72}")
        print(f"  {'AGENT':<16}{'P1':>8}{'P0':>8}{'votes':>8}   {'separation':>10}")
        shown = 0
        for name, t in sorted(by_agent.items(), key=lambda kv: -kv[1].n):
            if t.n < args.min_votes:
                continue
            shown += 1
            print(f"  {name:<16}{_pct(t.p1):>8}{_pct(t.p0):>8}{t.n:>8}   {_sep(t):>10}")
        if shown == 0:
            print(f"  (no agent has >= {args.min_votes} scored votes)")
        else:
            print(f"\n  'separation' is P1 - P0: how much an agent's vote actually")
            print(f"  discriminates good code from bad. Near zero = the vote carries")
            print(f"  little information regardless of the omega assigned to it.")

        # Coverage check. Agents that vote on fewer sessions than their peers were
        # either skipped by early stopping or timed out, and their absences are not
        # random -- a slow agent drops out of the hardest files. Comparing separation
        # across agents with uneven coverage compares different samples.
        counts = {name: t.n for name, t in by_agent.items()}
        if counts:
            hi, lo = max(counts.values()), min(counts.values())
            if hi and (hi - lo) / hi > 0.15:
                thin = sorted((n for n, c in counts.items() if c < hi * 0.85),
                              key=lambda n: counts[n])
                print(f"\n  !  UNEVEN COVERAGE: {lo}-{hi} votes across agents.")
                print(f"     Under-sampled: {', '.join(f'{n} ({counts[n]})' for n in thin)}")
                print(f"     Their separation is measured only on the sessions they")
                print(f"     completed, which is a biased subset. Re-run with")
                print(f"     --no-early-stop and a higher WARF_TIMEOUT before trusting")
                print(f"     the per-agent numbers.")

    # ── per persona version ──────────────────────────────────────────────────
    # What a prompt edit did: each agent's versions in the order they first appear
    # in the log. Not subject to --min-votes — a version with four votes is exactly
    # what gets looked at the day after an edit; the count is there to be read.
    if persona:
        agents = {a for (a, p) in by_persona if p == persona}
        rows = [(k, t) for k, t in by_persona.items() if k[0] in agents]
    else:
        rows = list(by_persona.items())
    if any(p for (_, p), _ in rows):
        order = {a: i for i, a in enumerate(dict.fromkeys(a for (a, _), _ in rows))}
        rows.sort(key=lambda kv: order[kv[0][0]])          # stable: keeps version order
        print(f"\n{'-' * 72}")
        print(f"  Per persona version  (latest vote per version per artifact)"
              if args.dedupe else f"  Per persona version  (every vote)")
        print(f"{'-' * 72}")
        print(f"  {'AGENT':<16}{'PERSONA':<16}{'P1':>8}{'P0':>8}{'votes':>8}   {'separation':>10}")
        for (agent, p), t in rows:
            mark = "  <-" if persona and p == persona else ""
            print(f"  {agent:<16}{_persona_label(p):<16}{_pct(t.p1):>8}{_pct(t.p0):>8}"
                  f"{t.n:>8}   {_sep(t):>10}{mark}")
        print(f"\n  Versions of one agent are comparable only where they saw the same")
        print(f"  files; a version measured on easier files looks better than it is.")
    elif not persona:
        print(f"\n  No vote in scope carries a persona version (all logged before persona")
        print(f"  versioning), so there is nothing to segment by prompt text yet.")

    # ── impact ───────────────────────────────────────────────────────────────
    if persona or measured is None:
        print()
        return

    print(f"\n{'-' * 72}")
    print(f"  Impact: replaying {len(labelled)} labelled sessions with measured LLR")
    print(f"{'-' * 72}")

    changed_decision  = 0
    changed_band      = 0
    correct_before    = 0
    correct_after     = 0
    band_moves: dict[str, int] = defaultdict(int)

    for s in labelled:
        x_star   = s["oracle"]["x_star"]
        old_dec  = s["decision"]
        old_conf = s["confidence"]
        new_dec, new_conf, _ = replay(
            s, measured["llr_approve"], measured["llr_reject"], A, B
        )
        if new_dec != old_dec:
            changed_decision += 1
        if new_conf != old_conf:
            changed_band += 1
            band_moves[f"{old_conf} -> {new_conf}"] += 1
        correct_before += (1 if old_dec == "APPROVE" else -1) == x_star
        correct_after  += (1 if new_dec == "APPROVE" else -1) == x_star

    n = len(labelled)
    print(f"  Decision changed  : {changed_decision:>3} / {n}")
    print(f"  Confidence changed: {changed_band:>3} / {n}")
    for move, count in sorted(band_moves.items(), key=lambda kv: -kv[1]):
        print(f"      {move:<20} {count}")
    print(f"\n  Accuracy vs oracle: {correct_before}/{n} assumed"
          f"  ->  {correct_after}/{n} measured")

    if changed_decision == 0 and changed_band == 0:
        print(f"\n  => P1/P0 are not load-bearing on this corpus. The assumed values")
        print(f"     can stay, and the choice is defensible as 'verified, not tuned'.")
    else:
        print(f"\n  => P1/P0 materially affect outcomes. Adopting the measured values")
        print(f"     changes {changed_band} confidence label(s). Re-run the calibration")
        print(f"     charts before quoting accuracy-per-band figures.")
    print()


if __name__ == "__main__":
    main()
