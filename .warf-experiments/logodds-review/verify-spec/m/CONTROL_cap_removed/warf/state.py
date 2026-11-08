"""
AgentProfile persistence — load and save weight state between sessions.
"""
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .engine import DOMAINS, omega_from_beta

ORACLE_TIERS: dict[str, float] = {
    "DEVELOPER": 1.0,
    "SAST":      0.7,
    "TEST":      0.3,
    "COMPILER":  0.1,
}

PERSONA_SKEPTIC = (
    "You are a defensive code reviewer. Search hard for bugs, missing guards, "
    "edge cases, and unsafe assumptions — assume nothing is correct until checked. "
    "Then apply this bar: REJECT only if you can name a specific input, state, or "
    "call sequence that produces incorrect behaviour. If your search finds nothing "
    "you can make concrete, that is an APPROVE — a suspicion you cannot demonstrate "
    "is not a defect. "
    "Respond with exactly one word on the first line — APPROVE or REJECT — "
    "then explain your reasoning."
)

PERSONA_ADVOCATE = (
    "You are a code reviewer who defends the author's intent. "
    "Assume the code is correct unless you find a clear, demonstrable defect. "
    "Respond with exactly one word on the first line — APPROVE or REJECT — "
    "then explain your reasoning."
)

PERSONA_AUDITOR = (
    "You are an impartial compliance officer performing a neutral technical audit. "
    "Apply standards and best practices without bias toward approval or rejection. "
    "Respond with exactly one word on the first line — APPROVE or REJECT — "
    "then explain your reasoning."
)

PERSONA_TEST_FOCUSED = (
    "You are a code reviewer who asks one question: if this code were wrong, would "
    "a test catch it? Trace each branch and failure path and ask whether its failure "
    "would be loud (an exception, a wrong return value a caller can assert on) or "
    "silent (a swallowed error, a mutated global, a wrong value that looks plausible). "
    "REJECT if you can name a specific path whose failure would be silent, or state "
    "that only manifests under timing, ordering, or environment a test cannot control. "
    "Also REJECT if you find an outright defect while tracing — a real bug does not "
    "become acceptable because it is testable. "
    "APPROVE if every failure path you traced would surface loudly to a caller. "
    "You are judging the code, not its test suite: the absence of a test file is not "
    "itself a defect. "
    "Respond with exactly one word on the first line — APPROVE or REJECT — "
    "then explain your reasoning."
)

PERSONA_BOUNDARY = (
    "You are a code reviewer who probes boundary conditions. For every function and "
    "input, trace what happens with None, empty collections, zero, negative values, "
    "maximum values, and off-by-one inputs. "
    "Then apply this bar: for each boundary you identify, decide whether it is "
    "(a) handled correctly, (b) unreachable given the caller's contract, or "
    "(c) genuinely mishandled. REJECT only if at least one falls in (c) and you can "
    "state the input and the wrong result it produces. Boundaries in categories (a) "
    "and (b) are an APPROVE — enumerating inputs that the code survives is not a "
    "finding. "
    "Respond with exactly one word on the first line — APPROVE or REJECT — "
    "then explain your reasoning."
)


@dataclass
class DomainWeight:
    alpha: float = 1.0
    beta: float  = 1.0

    @property
    def omega(self) -> float:
        return omega_from_beta(self.alpha, self.beta)


def persona_hash(text: str) -> str:
    """Short, stable fingerprint of a persona's *meaning*.

    Whitespace is normalised first so that re-indenting or re-wrapping a profile
    file does not count as changing the agent. Twelve hex chars is plenty: the
    hash only needs to distinguish versions of one agent's prompt from each other.
    """
    normalised = " ".join(text.split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:12]


@dataclass
class AgentProfile:
    name: str
    persona: str
    weights: dict[str, DomainWeight] = field(
        default_factory=lambda: {d: DomainWeight() for d in DOMAINS}
    )
    last_updated: str | None = None  # ISO-8601 UTC; None = never received oracle feedback
    # Which model answers for this agent. None = fall back to the environment
    # default (see providers.detect_default_provider). Setting these per agent is
    # what allows a mixed panel — e.g. three local models plus two hosted ones.
    provider: str | None = None
    model: str | None = None
    # Fingerprint of the persona text that EARNED `weights`. A weight is a
    # measurement of one specific prompt's track record; when the text changes,
    # the agent behind it changes and the measurement no longer applies.
    # None = profile predates this field, provenance unrecorded (see reconcile).
    persona_hash: str | None = None
    # Weights earned by earlier versions of this agent's persona, keyed by their
    # hash. A reverted persona gets its history back; nothing is silently lost.
    retired: dict[str, dict] = field(default_factory=dict)


_DEFAULT_AGENTS = [
    ("SKEPTIC",       PERSONA_SKEPTIC),
    ("ADVOCATE",      PERSONA_ADVOCATE),
    ("AUDITOR",       PERSONA_AUDITOR),
    ("TEST-FOCUSED",  PERSONA_TEST_FOCUSED),
    ("BOUNDARY",      PERSONA_BOUNDARY),
]


def default_profiles() -> list[AgentProfile]:
    # Born stamped: a fresh profile's uniform priors belong to exactly this text.
    return [
        AgentProfile(name=name, persona=persona, persona_hash=persona_hash(persona))
        for name, persona in _DEFAULT_AGENTS
    ]


def load_profiles(path: Path, reconcile: bool = True) -> list[AgentProfile]:
    """Read a profile, reconciling weights with persona text by default.

    Reconciling means: if an agent's persona text has changed since its weights
    were earned, those weights are retired and the agent restarts at uniform
    priors (see reconcile_profiles). That is a write, and it is performed here
    because every reader that goes on to VOTE or to APPLY FEEDBACK must see the
    corrected state — and both of those paths begin with this call.

    Pass reconcile=False for display-only readers, which should report pending
    changes rather than perform them.
    """
    if not path.exists():
        return default_profiles()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    profiles = [_from_dict(d) for d in data]

    if reconcile:
        events = reconcile_profiles(profiles, apply=True)
        if events:
            save_profiles(path, profiles)
            for e in events:
                print(f"  [persona] {e.describe()}", file=sys.stderr)

    return profiles


def save_profiles(path: Path, profiles: list[AgentProfile]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([_to_dict(p) for p in profiles], f, indent=2)


def _to_dict(p: AgentProfile) -> dict:
    out = {
        "name":         p.name,
        "persona":      p.persona,
        "weights":      {d: {"alpha": w.alpha, "beta": w.beta} for d, w in p.weights.items()},
        "last_updated": p.last_updated,
    }
    # Omit when unset so existing profiles round-trip byte-identical.
    if p.provider:
        out["provider"] = p.provider
    if p.model:
        out["model"] = p.model
    if p.persona_hash:
        out["persona_hash"] = p.persona_hash
    if p.retired:
        out["retired"] = p.retired
    return out


def _from_dict(d: dict) -> AgentProfile:
    weights = {
        dom: DomainWeight(alpha=v["alpha"], beta=v["beta"])
        for dom, v in d["weights"].items()
    }
    return AgentProfile(
        name=d["name"],
        persona=d["persona"],
        weights=weights,
        last_updated=d.get("last_updated"),
        provider=d.get("provider"),
        model=d.get("model"),
        persona_hash=d.get("persona_hash"),
        retired=dict(d.get("retired") or {}),
    )


# ── persona versioning ───────────────────────────────────────────────────────
#
# The problem this solves: someone edits an agent's prompt, and its learned
# alpha/beta keep being used and updated as if the same agent were still
# voting. The weights then describe nothing. "Treat a changed agent as a new
# agent" means: when the persona text no longer matches the hash that earned
# the weights, park those weights under their hash and restart at uniform
# priors. If the text is later changed back, the parked weights come back.

@dataclass
class ReconcileEvent:
    agent: str
    kind: str                 # "stamped" | "retired" | "restored"
    old_hash: str | None
    new_hash: str

    def describe(self) -> str:
        if self.kind == "stamped":
            return (f"{self.agent}: persona provenance recorded as {self.new_hash} "
                    f"(profile predated versioning)")
        if self.kind == "retired":
            return (f"{self.agent}: persona changed {self.old_hash} -> {self.new_hash}; "
                    f"weights earned by {self.old_hash} retired, agent restarts at "
                    f"uniform priors")
        return (f"{self.agent}: persona reverted to {self.new_hash}; "
                f"weights earned by that version restored")


def _archive_active(p: AgentProfile) -> None:
    """Park the current weights under the hash that earned them."""
    p.retired[p.persona_hash] = {
        "weights":      {d: {"alpha": w.alpha, "beta": w.beta} for d, w in p.weights.items()},
        "last_updated": p.last_updated,
        "retired_at":   datetime.now(timezone.utc).isoformat(),
    }


def reconcile_profiles(profiles: list[AgentProfile], apply: bool = True) -> list[ReconcileEvent]:
    """Bring each agent's weights into agreement with its current persona text.

    With apply=False this only reports what would happen, so read-only commands
    can display status without touching the file. With apply=True the profile
    objects are mutated in place; the caller is responsible for saving.

    Three cases per agent:
      stamped   no hash recorded yet -> record the current one. This asserts
                that the existing weights were earned by the current text, which
                is true for every profile that predates this feature and has not
                been hand-edited since.
      retired   text differs and no parked weights match -> archive the active
                weights under their hash, restart at uniform priors.
      restored  text differs but matches a parked version -> swap back.
    """
    events: list[ReconcileEvent] = []
    for p in profiles:
        current = persona_hash(p.persona)

        if p.persona_hash is None:
            events.append(ReconcileEvent(p.name, "stamped", None, current))
            if apply:
                p.persona_hash = current
            continue

        if p.persona_hash == current:
            continue

        kind = "restored" if current in p.retired else "retired"
        events.append(ReconcileEvent(p.name, kind, p.persona_hash, current))
        if not apply:
            continue

        _archive_active(p)
        if kind == "restored":
            parked = p.retired.pop(current)
            p.weights = {
                dom: DomainWeight(alpha=w["alpha"], beta=w["beta"])
                for dom, w in parked["weights"].items()
            }
            p.last_updated = parked.get("last_updated")
        else:
            p.weights = {d: DomainWeight() for d in DOMAINS}
            p.last_updated = None
        p.persona_hash = current

    return events


# ── profile naming ───────────────────────────────────────────────────────────

def profile_path(name: str, create: bool = True) -> Path:
    """Resolve a profile argument to a file, creating the profile if it is new.

    A bare name ("default", "myteam") maps to <data_dir>/profiles/<name>.json.
    Anything that looks like a path — a .json suffix or a directory part — is
    used literally, so a snapshot committed with a repo can be named exactly
    and is written to in place.

    A profile that does not exist yet is created fresh: current personas,
    uniform priors, born stamped. It is never copied from another profile;
    forking one is an explicit copy the caller makes.

    Shared by the CLI and the MCP server so both resolve names identically.
    """
    from .paths import profiles_dir

    p = Path(name)
    if p.suffix == ".json" or p.parent != Path("."):
        path = p
    else:
        path = profiles_dir() / f"{name}.json"
    if create and not path.exists():
        save_profiles(path, default_profiles())
        print(f"  [profile] Created '{name}' at {path}  (uniform priors, current personas)",
              file=sys.stderr)
    return path
