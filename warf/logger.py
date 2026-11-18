"""
WaRF session logger — appends one JSON line per review to sessions.jsonl.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .engine import THETA, Decision, Confidence, logodds_tau
from .orchestrator import ReviewResult, VoteRecord
from .state import ORACLE_TIERS, profile_path
from .paths import sessions_path

DEFAULT_LOG_PATH = sessions_path()

_ORACLE_TIER = {"DEVELOPER": 1, "SAST": 2, "TEST": 3, "COMPILER": 4}


class SessionNotFound(LookupError):
    """No session in the log matched the selector."""


class SessionAmbiguous(LookupError):
    """More than one session matched. Carries the candidates for reporting."""

    def __init__(self, matches: list[tuple[int, dict]]):
        self.matches = matches
        super().__init__(f"{len(matches)} sessions matched")


def session_dict(
    result: ReviewResult,
    artifact_path: str,
    oracle_type: str | None = None,
    x_star: int | None = None,
    weight_updates: list[dict] | None = None,
    profile_name: str | None = None,
) -> dict:
    """
    Build the canonical session record.

    Single source of truth for the session shape — both the JSONL log and the
    CLI's --json output are produced from this, so they cannot drift apart.

    artifact_path:  path (or label) of the file that was reviewed
    oracle_type:    "DEVELOPER" | "SAST" | "TEST" | "COMPILER" — or None if no oracle
    x_star:         +1 / -1 ground truth — or None if no oracle
    weight_updates: list returned by apply_oracle — or None
    """
    entry = {
        "session_id":      str(uuid.uuid4()),
        "created_at":      datetime.now(timezone.utc).isoformat(),
        "artifact":        artifact_path,
        "domain":          result.domain,
        "theta":           THETA[result.domain],
        # Which panel produced this session. Without it, votes from different
        # personas or models are indistinguishable in the log and no before/after
        # comparison is possible.
        "profile":         profile_name,
        "votes": [
            {
                "agent":      v.agent_name,
                "vote":       v.vote,
                "label":      "APPROVE" if v.vote == 1 else "REJECT",
                "omega":      round(v.omega, 4),
                "provider":   v.provider,
                "model":      v.model,
                "persona":    v.persona_hash,
                "reasoning":  v.reasoning,
                "tokens_in":  v.tokens_in,
                "tokens_out": v.tokens_out,
            }
            for v in result.votes
        ],
        "sprt_lambda":      round(result.sprt_lambda, 4),
        "sprt_fired":       result.confidence.value == "HIGH",
        "decision":         result.decision.value,
        "confidence":       result.confidence.value,
        "normalised_score": round(result.normalised_score, 4)
                            if result.normalised_score is not None else None,
        "total_tokens_in":  sum(v.tokens_in  for v in result.votes),
        "total_tokens_out": sum(v.tokens_out for v in result.votes),
    }

    for rec, v in zip(entry["votes"], result.votes):
        if v.evidence_source:          # ADR 0002; votes of seats on the common input keep their shape
            rec["evidence_source"] = v.evidence_source
        if v.question:                 # ADR 0003; verdict seats keep their shape
            rec["question"] = v.question

    if result.aggregate != "vote":
        # docs/spec/logodds-aggregation.md §6; vote-mode records keep their shape
        entry["aggregate"] = result.aggregate
        entry["tau"] = round(logodds_tau(result.domain), 4)   # the decision threshold; theta is vote mode's
        for rec, v in zip(entry["votes"], result.votes):
            rec["p_reject"]    = v.p_reject
            rec["evidence"]    = round(v.evidence, 4) if v.evidence is not None else None
            rec["calibration"] = v.calibration
    if result.learned:
        # docs/spec/learned-aggregation.md §6: the fit behind the verdict
        entry["learned"] = {"bias": round(result.learned["bias"], 4),
                            "n_clean": result.learned["n_clean"],
                            "n_defective": result.learned["n_defective"]}

    if result.debate_votes:
        r1_vote_map = {v.agent_name: v.vote for v in result.votes}
        entry["debate"] = {
            "sprt_lambda": round(result.debate_sprt_lambda, 4),
            "normalised_score": (
                round(result.debate_normalised_score, 4)
                if result.debate_normalised_score is not None else None
            ),
            "votes": [
                {
                    "agent":      v.agent_name,
                    "vote":       v.vote,
                    "label":      "APPROVE" if v.vote == 1 else "REJECT",
                    "omega":      round(v.omega, 4),
                    "changed":    v.vote != r1_vote_map.get(v.agent_name),
                    "provider":   v.provider,
                    "model":      v.model,
                    "persona":    v.persona_hash,
                    "reasoning":  v.reasoning,
                    "tokens_in":  v.tokens_in,
                    "tokens_out": v.tokens_out,
                }
                for v in result.debate_votes
            ],
            "vote_changes": [
                v.agent_name for v in result.debate_votes
                if v.vote != r1_vote_map.get(v.agent_name)
            ],
        }

    if oracle_type is not None and x_star is not None:
        entry["oracle"] = {
            "type":           oracle_type,
            "tier":           _ORACLE_TIER.get(oracle_type, 1),
            "gamma":          ORACLE_TIERS[oracle_type],
            "x_star":         x_star,
            "x_star_label":   "APPROVE" if x_star == 1 else "REJECT",
            "weight_updates": weight_updates or [],
        }

    return entry


def append_session(
    result: ReviewResult,
    artifact_path: str,
    oracle_type: str | None = None,
    x_star: int | None = None,
    weight_updates: list[dict] | None = None,
    log_path: Path = DEFAULT_LOG_PATH,
    profile_name: str | None = None,
    input_sha256: str | None = None,
) -> dict:
    """
    Append one review session to the JSONL log.

    Returns the written entry. Callers that need the generated session_id —
    for example to print it so a human can later run `warf label <id>` —
    read it from the returned dict; older callers may ignore the return value.
    input_sha256 (directory and commit reviews): the SHA-256 of what was reviewed, the file's bytes or its patch
    (without a --commit-context block); a rerun reuses the session only for the same input
    (cli._load_reviewed_sessions).
    """
    entry = session_dict(result, artifact_path, oracle_type, x_star,
                         weight_updates, profile_name)
    if input_sha256:
        entry["input_sha256"] = input_sha256

    log_path.parent.mkdir(parents=True, exist_ok=True)
    # A review killed while writing leaves a last line without its newline: start a line of our own, or the two
    # merge into one line no reader parses and this session is lost with it.
    cut_short = False
    if log_path.exists() and log_path.stat().st_size:
        with open(log_path, "rb") as f:
            f.seek(-1, 2)
            cut_short = f.read(1) != b"\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(("\n" if cut_short else "") + json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


# ── reading back / relabelling ───────────────────────────────────────────────

def load_lines(log_path: Path = DEFAULT_LOG_PATH) -> list[str]:
    """Return the raw non-empty lines of the session log."""
    if not log_path.exists():
        return []
    with open(log_path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def find_session(
    lines: list[str],
    id_prefix: str | None = None,
    artifact_sub: str | None = None,
) -> tuple[int, dict]:
    """Locate one session by session_id prefix or artifact substring.

    Raises SessionNotFound or SessionAmbiguous rather than exiting, so callers
    can decide how to report (human text or JSON).
    """
    matches: list[tuple[int, dict]] = []
    for i, line in enumerate(lines):
        try:
            s = json.loads(line)
        except json.JSONDecodeError:
            continue
        if id_prefix and s.get("session_id", "").startswith(id_prefix):
            matches.append((i, s))
        elif artifact_sub and artifact_sub.lower() in s.get("artifact", "").lower():
            matches.append((i, s))

    if not matches:
        raise SessionNotFound("no session matched")
    if len(matches) > 1:
        raise SessionAmbiguous(matches)
    return matches[0]


def result_from_session(session: dict) -> ReviewResult:
    """Rebuild a ReviewResult from a logged session.

    Only the fields apply_oracle() reads are reconstructed faithfully — domain
    and the two vote rounds. This lets `warf label` reuse the same Bayesian
    update path as an inline --ground-truth review instead of duplicating it.
    """
    def _votes(raw: list[dict]) -> list[VoteRecord]:
        return [
            VoteRecord(
                agent_name=v["agent"],
                vote=v["vote"],
                omega=v.get("omega", 0.0),
                reasoning=v.get("reasoning", ""),
                tokens_in=v.get("tokens_in", 0),
                tokens_out=v.get("tokens_out", 0),
                provider=v.get("provider", ""),
                model=v.get("model", ""),
                # Sessions logged before persona versioning carry no hash; an
                # empty string means "unknown", and apply_oracle applies those
                # normally rather than refusing them.
                persona_hash=v.get("persona", ""),
            )
            for v in raw
        ]

    debate = session.get("debate") or {}
    return ReviewResult(
        decision=Decision(session["decision"]),
        confidence=Confidence(session["confidence"]),
        domain=session["domain"],
        votes=_votes(session.get("votes", [])),
        sprt_lambda=session.get("sprt_lambda", 0.0),
        normalised_score=session.get("normalised_score"),
        debate_votes=_votes(debate.get("votes", [])),
        debate_sprt_lambda=debate.get("sprt_lambda", 0.0),
        debate_normalised_score=debate.get("normalised_score"),
    )


def write_lines(lines: list[str], log_path: Path = DEFAULT_LOG_PATH) -> None:
    """Rewrite the whole session log. Used when patching one entry in place."""
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def oracle_entry(oracle_type: str, x_star: int, weight_updates: list[dict]) -> dict:
    """Build the oracle block attached to a session once ground truth is known."""
    return {
        "type":           oracle_type,
        "tier":           _ORACLE_TIER.get(oracle_type, 1),
        "gamma":          ORACLE_TIERS[oracle_type],
        "x_star":         x_star,
        "x_star_label":   "APPROVE" if x_star == 1 else "REJECT",
        "weight_updates": weight_updates or [],
    }


class AlreadyLabelled(LookupError):
    """The session already carries an oracle label. Carries the session."""

    def __init__(self, session: dict):
        self.session = session
        super().__init__(f"session {session.get('session_id', '?')[:8]} is already labelled")


class ProfileMismatch(LookupError):
    """A profile was named that is not the one the session was reviewed with. Carries both."""

    def __init__(self, session: dict, profile: str):
        self.session, self.profile = session, profile
        super().__init__(
            f"session {session.get('session_id', '?')[:8]} was reviewed with profile {session['profile']!r}, not "
            f"{profile!r}: its votes belong to that profile's agents. Leave the profile out to update it.")


class ProfileNotFound(LookupError):
    """The profile to update has no file here. Carries the session and the path looked at."""

    def __init__(self, session: dict, name: str, path: Path):
        self.session, self.path = session, path
        relative = "" if path.is_absolute() else (
            f"; {name!r} is relative to the directory the review ran in: label from there, or name the file "
            f"with --profile")
        super().__init__(f"profile {name!r} of session {session.get('session_id', '?')[:8]} not found at "
                         f"{path}{relative}. No profile is created to take a label.")


class LabelConflict(LookupError):
    """force=True with a verdict or oracle other than the session's label. Carries the session."""

    def __init__(self, session: dict, verdict: str, oracle_type: str):
        self.session = session
        o = session["oracle"]
        super().__init__(
            f"session {session.get('session_id', '?')[:8]} is labelled {o['x_star_label']} ({o['type']}); --force "
            f"applies that label again, to repair a failed profile write, not {verdict} ({oracle_type}). A label "
            f"cannot be changed: its weight update has no undo short of `warf reset` (policy.md §7).")


def label_session(
    verdict: str,
    profile: str | None,
    session_id: str | None = None,
    artifact: str | None = None,
    oracle_type: str = "DEVELOPER",
    force: bool = False,
    verbose: bool = False,
    log_path: Path = DEFAULT_LOG_PATH,
) -> dict:
    """Attach ground truth to a logged session and update the agents' weights.

    The learning loop in one call: locate the session (by id prefix or artifact
    substring), rebuild its ReviewResult, run the Bayesian update against the
    profile it was reviewed with, and patch the log entry with the oracle block.
    profile None means that one; naming another raises ProfileMismatch, since the
    votes are its agents'. A session logged without a profile takes the named
    one, "default" when None. A profile logged as a relative file path holds
    only from the directory the review ran in; from elsewhere it is not found
    (ProfileNotFound) unless the profile is named, and no profile is ever
    created to take a label.

    Raises SessionNotFound, SessionAmbiguous (carrying the candidates),
    AlreadyLabelled, LabelConflict, ProfileMismatch, ProfileNotFound or
    ValueError instead of exiting, so the CLI and the MCP server can each report
    in their own way. Returns a dict shaped like `warf label --json`.

    Re-labelling (force=True) keeps the original oracle block as the historical
    record and applies a second weight update on top of the first. It takes the
    session's own verdict and oracle only (LabelConflict otherwise): it repairs a
    failed profile write, it does not change a label.
    """
    from .orchestrator import apply_oracle

    x_star_label = verdict.upper()
    if x_star_label not in ("APPROVE", "REJECT"):
        raise ValueError(f"verdict must be APPROVE or REJECT, got {verdict!r}")
    oracle_type = oracle_type.upper()
    if oracle_type not in ORACLE_TIERS:
        raise ValueError(f"oracle must be one of {', '.join(ORACLE_TIERS)}, got {oracle_type!r}")
    x_star = 1 if x_star_label == "APPROVE" else -1

    lines = load_lines(log_path)
    if not lines:
        raise SessionNotFound("no sessions logged yet")
    idx, session = find_session(lines, session_id, artifact)

    relabel = "oracle" in session
    if relabel and not force:
        raise AlreadyLabelled(session)
    if relabel and (x_star, oracle_type) != (session["oracle"]["x_star"], session["oracle"]["type"]):
        raise LabelConflict(session, x_star_label, oracle_type)     # the log would no longer say what was applied

    logged = session.get("profile")
    name = logged if logged is not None else (profile or "default")
    profiles_path = profile_path(name, create=False)
    if logged is not None and profile is not None and \
            profile_path(profile, create=False).resolve() != profiles_path.resolve():
        if profiles_path.exists() or profiles_path.is_absolute():
            raise ProfileMismatch(session, profile)
        # A relative path logged from another directory: the file named here is the one meant.
        name, profiles_path = profile, profile_path(profile, create=False)
    if not profiles_path.exists():
        raise ProfileNotFound(session, name, profiles_path)
    profile = name

    result  = result_from_session(session)
    updates = apply_oracle(result, x_star, oracle_type, profiles_path, verbose=verbose)

    if not relabel:
        session["oracle"] = oracle_entry(oracle_type, x_star, updates)
        lines[idx] = json.dumps(session, ensure_ascii=False)
        write_lines(lines, log_path)

    return {
        "session_id": session["session_id"],
        "artifact":   session["artifact"],
        "domain":     session["domain"],
        "decision":   session["decision"],
        "confidence": session["confidence"],
        "profile":    profile,
        "oracle": {
            "type":         oracle_type,
            "gamma":        ORACLE_TIERS[oracle_type],
            "x_star":       x_star,
            "x_star_label": x_star_label,
        },
        "relabelled":     relabel,
        "weight_updates": updates,
    }
