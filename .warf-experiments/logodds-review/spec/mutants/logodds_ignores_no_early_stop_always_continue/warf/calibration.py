"""
Per-agent calibration for log-odds aggregation (docs/spec/logodds-aggregation.md §3, §5).

Turns an agent's answer into evidence in natural log-likelihood-ratio units
(positive = APPROVE), learned from the developer labels of that agent's past
votes in the session log. Until an agent has enough labels its evidence is
capped at what its vote is worth in `vote` mode.

Reads the JSONL log directly: logger imports the orchestrator, which imports
this module.
"""
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .engine import capped_evidence, vote_evidence
from .state import AgentProfile

MIN_PER_CLASS_DECISION = 10   # Platt fit: two parameters
MIN_PER_CLASS_TEXT     = 5    # two rates
P_FLOOR = 0.01                # the readout has two decimals; keeps |log-odds| <= 4.6

# WaRF's own rendering of a decision-model answer (providers.SystemOneProvider).
# The tag keeps a text agent's prose from ever being read as a probability.
_DECISION_TAG = "decision model, no reasoning"
_P_REJECT = re.compile(r"p\(REJECT\)=([0-9]*\.?[0-9]+)")


def p_reject_from_text(text: str) -> float | None:
    """A decision agent's p(REJECT) from its readout, clamped; None for anything else."""
    if not text or _DECISION_TAG not in text:
        return None
    m = _P_REJECT.search(text)
    if m is None:
        return None
    return min(1.0 - P_FLOOR, max(P_FLOOR, float(m.group(1))))


def approve_logodds(p_reject: float) -> float:
    """ln((1 - p) / p): the agent's own log-odds that the change is clean."""
    return math.log((1.0 - p_reject) / p_reject)


def _logit(q: float) -> float:
    return math.log(q / (1.0 - q))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x)) if x >= 0 else math.exp(x) / (1.0 + math.exp(x))


@dataclass
class PlattFit:
    a: float
    b: float
    prior_logodds: float   # logit of the smoothed clean share of the training labels

    def evidence(self, r: float) -> float:
        """Fitted posterior log-odds minus the training base rate: a likelihood ratio."""
        return self.a + self.b * r - self.prior_logodds


def _log_posterior(a: float, b: float, rs: list[float], ys: list[int]) -> float:
    total = -0.5 * a * a - 0.5 * (b - 1.0) ** 2
    for r, y in zip(rs, ys):
        z = a + b * r
        # log σ(z) for clean, log σ(-z) for defective, computed without overflow
        s = z if y == 1 else -z
        total += -math.log1p(math.exp(-s)) if s >= 0 else s - math.log1p(math.exp(s))
    return total


def fit_platt(rs: list[float], ys: list[int], max_iter: int = 50) -> PlattFit | None:
    """
    MAP logistic regression of y = clean (+1) on r, prior a ~ N(0, 1), b ~ N(1, 1).

    Newton's method on the 2x2 problem with step halving, so the log posterior
    never decreases (a full step diverges when the start is far off). None if it
    does not converge.
    """
    a, b = 0.0, 1.0
    current = _log_posterior(a, b, rs, ys)
    for _ in range(max_iter):
        ga, gb = -a, -(b - 1.0)            # gradient of the log posterior
        haa, hab, hbb = 1.0, 0.0, 1.0      # negative Hessian
        for r, y in zip(rs, ys):
            p = _sigmoid(a + b * r)
            t = 1.0 if y == 1 else 0.0
            ga += t - p
            gb += (t - p) * r
            w = p * (1.0 - p)
            haa += w
            hab += w * r
            hbb += w * r * r
        det = haa * hbb - hab * hab
        if det <= 0:
            return None
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        step = 1.0
        for _ in range(40):
            candidate = _log_posterior(a + step * da, b + step * db, rs, ys)
            if candidate >= current:
                break
            step /= 2.0
        else:
            return None
        a, b, current = a + step * da, b + step * db, candidate
        if abs(step * da) < 1e-9 and abs(step * db) < 1e-9:
            n_clean = sum(1 for y in ys if y == 1)
            return PlattFit(a, b, _logit((n_clean + 1) / (len(ys) + 2)))
    return None


@dataclass
class _History:
    votes: list[int]
    p_rejects: list[float | None]
    labels: list[int]


class Calibrator:
    """Evidence for each agent's answer, from the labelled votes in one session log."""

    def __init__(self, log_path: Path):
        self._sessions: list[dict] = []
        try:
            for line in Path(log_path).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    s = json.loads(line)
                except json.JSONDecodeError:
                    continue
                oracle = s.get("oracle") or {}
                if oracle.get("type") == "DEVELOPER" and oracle.get("x_star") in (1, -1):
                    self._sessions.append(s)
        except OSError:
            pass   # no log yet: every agent is uncalibrated
        self._cache: dict[tuple[str, str], _History] = {}
        self._fits: dict[tuple[str, str], PlattFit | None] = {}

    def _history(self, profile: AgentProfile) -> _History:
        key = (profile.name, profile.persona_hash or "")
        if key not in self._cache:
            h = _History([], [], [])
            if profile.persona_hash:
                for s in self._sessions:
                    for v in s.get("votes", []):
                        if v.get("agent") != profile.name or v.get("persona") != profile.persona_hash:
                            continue
                        p = v.get("p_reject")
                        if p is None:
                            p = p_reject_from_text(v.get("reasoning", ""))
                        h.votes.append(v.get("vote"))
                        h.p_rejects.append(p)
                        h.labels.append(s["oracle"]["x_star"])
            self._cache[key] = h
        return self._cache[key]

    def history_size(self, profile: AgentProfile) -> int:
        return len(self._history(profile).labels)

    def _platt(self, profile: AgentProfile) -> PlattFit | None:
        key = (profile.name, profile.persona_hash or "")
        if key not in self._fits:
            h = self._history(profile)
            pairs = [(approve_logodds(p), y) for p, y in zip(h.p_rejects, h.labels) if p is not None]
            enough = (sum(1 for _, y in pairs if y == 1) >= MIN_PER_CLASS_DECISION
                      and sum(1 for _, y in pairs if y == -1) >= MIN_PER_CLASS_DECISION)
            self._fits[key] = fit_platt([r for r, _ in pairs], [y for _, y in pairs]) if enough else None
        return self._fits[key]

    def evidence(self, profile: AgentProfile, vote: int, p_reject: float | None,
                 omega: float) -> tuple[float, str]:
        """(evidence, calibration tag) for one answer; see the spec's §3 table."""
        if p_reject is not None:
            r = approve_logodds(p_reject)
            fit = self._platt(profile)
            if fit is None:
                return capped_evidence(r, omega), "capped"
            return fit.evidence(r), "platt"

        h = self._history(profile)
        clean = [v for v, y in zip(h.votes, h.labels) if y == 1]
        defective = [v for v, y in zip(h.votes, h.labels) if y == -1]
        if len(clean) < MIN_PER_CLASS_TEXT or len(defective) < MIN_PER_CLASS_TEXT:
            return vote_evidence(vote, omega), "omega"
        p_clean = (sum(1 for v in clean if v == vote) + 1) / (len(clean) + 2)
        p_defective = (sum(1 for v in defective if v == vote) + 1) / (len(defective) + 2)
        return math.log(p_clean / p_defective), "rates"
