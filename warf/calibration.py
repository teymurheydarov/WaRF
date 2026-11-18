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
MIN_PER_CLASS_LEARNED  = 20   # learned weights over a panel (docs/spec/learned-aggregation.md §3)
LEARNED_PRIOR_SD       = 1.0  # every learned coefficient ~ N(0, 1)
P_FLOOR = 0.01                # the readout has two decimals; keeps |log-odds| <= 4.6

# WaRF's own rendering of a decision-model answer (providers.SystemOneProvider).
# The tag keeps a text agent's prose from ever being read as a probability.
_DECISION_TAG = "decision model, no reasoning"
_P_APPROVE = re.compile(r"p\(APPROVE\)=([0-9]*\.?[0-9]+)")
_P_REJECT = re.compile(r"p\(REJECT\)=([0-9]*\.?[0-9]+)")


def _clamp(p: float) -> float:
    return min(1.0 - P_FLOOR, max(P_FLOOR, float(p)))


def p_reject_from_text(text: str) -> float | None:
    """
    A decision agent's p(REJECT) from its readout, clamped; None for anything else.

    The provider renders a missing probability as 0.00, so a readout counts only
    when both probabilities are there and sum to about 1.
    """
    if not text or _DECISION_TAG not in text:
        return None
    m_rej, m_app = _P_REJECT.search(text), _P_APPROVE.search(text)
    if m_rej is None or m_app is None:
        return None
    if abs(float(m_rej.group(1)) + float(m_app.group(1)) - 1.0) > 0.05:
        return None
    return _clamp(float(m_rej.group(1)))


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


def seat_logodds(vote: int, p_reject: float | None) -> float:
    """
    A seat's own log-odds for APPROVE, the feature the learned weights act on: ln((1 - p) / p) for a
    usable p that agrees with the vote, else the vote itself (+1 / -1), as for a text agent.
    """
    if p_reject is not None and not (p_reject - 0.5) * vote > 0:
        return approve_logodds(_clamp(p_reject))
    return float(vote)


def _solve(H: list[list[float]], g: list[float]) -> list[float] | None:
    """H d = g by Gaussian elimination with partial pivoting; None if H is singular."""
    n = len(g)
    M = [row[:] + [g[i]] for i, row in enumerate(H)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            for k in range(c, n + 1):
                M[r][k] -= f * M[c][k]
    d = [0.0] * n
    for r in range(n - 1, -1, -1):
        d[r] = (M[r][n] - sum(M[r][k] * d[k] for k in range(r + 1, n))) / M[r][r]
    return d


def _log_posterior_k(w: list[float], X: list[list[float]], ys: list[int], prior_sd: float) -> float:
    total = -0.5 * sum(wj * wj for wj in w[1:]) / prior_sd ** 2       # the intercept w[0] has a flat prior
    for x, y in zip(X, ys):
        z = sum(a * b for a, b in zip(w, x))
        s = z if y == 1 else -z
        total += -math.log1p(math.exp(-s)) if s >= 0 else s - math.log1p(math.exp(s))
    return total


def fit_logistic(X: list[list[float]], ys: list[int], prior_sd: float, max_iter: int = 50) -> list[float] | None:
    """
    MAP logistic regression of y = clean (+1) on the rows of X (their first column is 1, the
    intercept). Every weight ~ N(0, prior_sd²); the intercept has a flat prior, so that it carries the
    training base rate in full and LearnedFit.bias can remove it (a shrunk intercept would lean every
    verdict of a panel trained on an imbalanced history). Newton's method with step halving, as
    fit_platt. None if it does not converge.
    """
    k = len(X[0])
    w = [0.0] * k
    current = _log_posterior_k(w, X, ys, prior_sd)
    for _ in range(max_iter):
        g = [0.0] + [-wj / prior_sd ** 2 for wj in w[1:]]
        H = [[(1.0 / prior_sd ** 2 if a == b and a > 0 else 0.0) for b in range(k)] for a in range(k)]
        for x, y in zip(X, ys):
            p = _sigmoid(sum(a * b for a, b in zip(w, x)))
            t = 1.0 if y == 1 else 0.0
            for a in range(k):
                g[a] += (t - p) * x[a]
                for b in range(k):
                    H[a][b] += p * (1.0 - p) * x[a] * x[b]
        d = _solve(H, g)
        if d is None:
            return None
        step = 1.0
        for _ in range(40):
            candidate = [wj + step * dj for wj, dj in zip(w, d)]
            value = _log_posterior_k(candidate, X, ys, prior_sd)
            if value >= current:
                break
            step /= 2.0
        else:
            return None
        w, current = candidate, value
        if max(abs(step * dj) for dj in d) < 1e-9:
            return w
    return None


@dataclass
class LearnedFit:
    """Learned weights of one panel: Λ = bias + Σ weight(seat) · seat_logodds (learned-aggregation.md §3)."""
    intercept: float
    weights: dict[tuple, float]     # reviewer key (Calibrator._key) -> weight
    prior_logodds: float            # logit of the smoothed clean share of the training sessions
    n_clean: int
    n_defective: int

    @property
    def bias(self) -> float:
        """The fitted intercept minus the training base rate: evidence at prior odds 1:1, as τ expects."""
        return self.intercept - self.prior_logodds

    def weight(self, profile: AgentProfile, provider: str = "", model: str = "") -> float:
        return self.weights.get(Calibrator._key(profile, provider, model), 0.0)


@dataclass
class _History:
    votes: list[int]
    p_rejects: list[float | None]
    labels: list[int]


class Calibrator:
    """
    Evidence for each agent's answer, from the labelled votes in one session log.

    A history belongs to one reviewer: the same agent name, persona text, model,
    evidence source and question. The same persona on another model, shown other
    evidence (AgentProfile.evidence) or asked another question (AgentProfile.question),
    is another reviewer.
    """

    def __init__(self, log_path: Path):
        self._sessions: list[dict] = []
        try:
            raw = Path(log_path).read_bytes().decode("utf-8", errors="replace")
        except OSError:
            raw = ""   # no log yet: every agent is uncalibrated
        for line in raw.splitlines():
            try:
                s = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(s, dict) or not isinstance(s.get("oracle"), dict) \
                    or not isinstance(s.get("votes"), list):
                continue
            if s["oracle"].get("type") == "DEVELOPER" and s["oracle"].get("x_star") in (1, -1):
                self._sessions.append(s)
        self._cache: dict[tuple, _History] = {}
        self._fits: dict[tuple, PlattFit | None] = {}
        self.learned_status = ""   # why the last learned() call gave a fit or none

    @staticmethod
    def _key(profile: AgentProfile, provider: str, model: str) -> tuple:
        return (profile.name, profile.persona_hash or "", provider or "", model or "", profile.evidence or "",
                profile.question or "")

    @staticmethod
    def _vote_key(v: dict) -> tuple:
        return (v.get("agent"), v.get("persona"), v.get("provider") or "", v.get("model") or "",
                v.get("evidence_source") or "", v.get("question") or "")

    @staticmethod
    def _vote_p(v: dict) -> float | None:
        p = v.get("p_reject")
        return _clamp(p) if isinstance(p, (int, float)) else p_reject_from_text(v.get("reasoning") or "")

    def learned(self, reviewers: list[tuple[AgentProfile, str, str]]) -> "LearnedFit | None":
        """
        Weights over the panel's seats from the labelled sessions (docs/spec/learned-aggregation.md §3).

        reviewers: each seat with the provider and model it answers on. A session counts when at least
        one of them voted in it; a seat that did not vote adds 0 (no evidence). None until there are
        MIN_PER_CLASS_LEARNED labels of each class, or when the fit does not converge; `learned_status`
        then says which.
        """
        keys = [self._key(p, prov, model) for p, prov, model in reviewers]
        index = {k: i for i, k in enumerate(keys)}
        rows, ys = [], []
        for s in self._sessions:
            x, seen = [0.0] * len(keys), set()
            for v in s["votes"]:
                if not isinstance(v, dict) or v.get("vote") not in (1, -1):
                    continue
                i = index.get(self._vote_key(v))
                if i is None or i in seen or not (v.get("persona") or ""):
                    continue
                seen.add(i)
                x[i] = seat_logodds(v["vote"], self._vote_p(v))
            if seen:
                rows.append([1.0] + x)
                ys.append(s["oracle"]["x_star"])
        n_clean = sum(1 for y in ys if y == 1)
        n_defective = len(ys) - n_clean
        if n_clean < MIN_PER_CLASS_LEARNED or n_defective < MIN_PER_CLASS_LEARNED:
            self.learned_status = (f"too few labelled sessions with this panel's seats: {n_clean} clean, "
                                   f"{n_defective} defective (needs {MIN_PER_CLASS_LEARNED} of each)")
            return None
        w = fit_logistic(rows, ys, LEARNED_PRIOR_SD)
        if w is None:
            self.learned_status = (f"the weight fit did not converge on {n_clean} clean and {n_defective} "
                                   f"defective sessions")
            return None
        self.learned_status = f"fitted on {n_clean} clean and {n_defective} defective sessions"
        return LearnedFit(intercept=w[0], weights=dict(zip(keys, w[1:])),
                          prior_logodds=_logit((n_clean + 1) / (len(ys) + 2)),
                          n_clean=n_clean, n_defective=n_defective)

    def _history(self, profile: AgentProfile, provider: str, model: str) -> _History:
        key = self._key(profile, provider, model)
        if key not in self._cache:
            h = _History([], [], [])
            if profile.persona_hash:
                for s in self._sessions:
                    for v in s["votes"]:
                        if not isinstance(v, dict) or v.get("vote") not in (1, -1):
                            continue
                        if self._vote_key(v) != key:
                            continue
                        h.votes.append(v["vote"])
                        h.p_rejects.append(self._vote_p(v))
                        h.labels.append(s["oracle"]["x_star"])
            self._cache[key] = h
        return self._cache[key]

    def history_size(self, profile: AgentProfile, provider: str = "", model: str = "") -> int:
        return len(self._history(profile, provider, model).labels)

    def _platt(self, profile: AgentProfile, provider: str, model: str) -> PlattFit | None:
        key = self._key(profile, provider, model)
        if key not in self._fits:
            h = self._history(profile, provider, model)
            pairs = [(approve_logodds(p), y) for p, y in zip(h.p_rejects, h.labels) if p is not None]
            enough = (sum(1 for _, y in pairs if y == 1) >= MIN_PER_CLASS_DECISION
                      and sum(1 for _, y in pairs if y == -1) >= MIN_PER_CLASS_DECISION)
            self._fits[key] = fit_platt([r for r, _ in pairs], [y for _, y in pairs]) if enough else None
        return self._fits[key]

    def evidence(self, profile: AgentProfile, vote: int, p_reject: float | None,
                 omega: float, provider: str, model: str) -> tuple[float, str]:
        """(evidence, calibration tag) for one answer; see the spec's §3 table."""
        if p_reject is not None and (p_reject - 0.5) * vote > 0:
            p_reject = None   # the p contradicts the vote it came with: use the vote
        if p_reject is not None:
            r = approve_logodds(p_reject)
            fit = self._platt(profile, provider, model)
            if fit is None:
                return capped_evidence(r, omega), "capped"
            return fit.evidence(r), "platt"

        h = self._history(profile, provider, model)
        clean = [v for v, y in zip(h.votes, h.labels) if y == 1]
        defective = [v for v, y in zip(h.votes, h.labels) if y == -1]
        if len(clean) < MIN_PER_CLASS_TEXT or len(defective) < MIN_PER_CLASS_TEXT:
            return vote_evidence(vote, omega), "omega"
        p_clean = (sum(1 for v in clean if v == vote) + 1) / (len(clean) + 2)
        p_defective = (sum(1 for v in defective if v == vote) + 1) / (len(defective) + 2)
        return math.log(p_clean / p_defective), "rates"
