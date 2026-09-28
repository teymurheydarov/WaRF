"""
WaRF deterministic math engine.
All functions are pure — no I/O, no API calls, no randomness.
"""
import math
from dataclasses import dataclass
from enum import Enum

# SPRT parameters (Wald 1945)
# p1 = P(APPROVE | code is actually good)
# p0 = P(APPROVE | code is actually bad)
P1 = 0.80
P0 = 0.30
ALPHA_ERR = 0.05   # false positive bound
BETA_ERR  = 0.10   # false negative bound

A = math.log((1 - BETA_ERR) / ALPHA_ERR)    # upper boundary ≈ +2.890
B = math.log(BETA_ERR / (1 - ALPHA_ERR))    # lower boundary ≈ -2.251

LLR_APPROVE = math.log(P1 / P0)             # ≈ +0.981
LLR_REJECT  = math.log((1 - P1) / (1 - P0)) # ≈ -1.253

# Domain-specific synthesis thresholds
THETA = {
    "LOGIC":       0.0,
    "SECURITY":   +0.2,   # bias toward REJECT for security findings
    "PERFORMANCE": -0.1,  # slight tolerance for performance trade-offs
}

DOMAINS = ("LOGIC", "SECURITY", "PERFORMANCE")


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REJECT  = "REJECT"


class Confidence(str, Enum):
    HIGH   = "HIGH"    # SPRT boundary crossed
    MEDIUM = "MEDIUM"  # pool exhausted, margin >= 0.2
    LOW    = "LOW"     # pool exhausted, margin < 0.2


@dataclass
class SPRTState:
    lambda_: float = 0.0
    k: int = 0


def sprt_update(
    state: SPRTState,
    vote: int,
    omega: float,
) -> tuple[SPRTState, Decision | None]:
    """
    Incorporate one weighted vote into the SPRT running statistic.

    vote:  +1 (APPROVE) or -1 (REJECT)
    omega: agent weight in [0, 1]

    Returns (new_state, decision_if_boundary_crossed).
    """
    llr = LLR_APPROVE if vote == 1 else LLR_REJECT
    new_lambda = state.lambda_ + omega * llr
    new_state = SPRTState(lambda_=new_lambda, k=state.k + 1)

    if new_lambda >= A:
        return new_state, Decision.APPROVE
    if new_lambda <= B:
        return new_state, Decision.REJECT
    return new_state, None


def synthesis(
    votes: list[int],
    weights: list[float],
    domain: str,
) -> tuple[Decision, Confidence, float]:
    """
    Weighted-average synthesis function (fallback when SPRT pool is exhausted).

    Returns (decision, confidence, normalised_score).
    """
    theta = THETA[domain]
    total_weight = sum(weights)
    normalised = sum(w * v for w, v in zip(weights, votes)) / total_weight
    margin = abs(normalised - theta)

    decision = Decision.APPROVE if normalised >= theta else Decision.REJECT
    confidence = Confidence.MEDIUM if margin >= 0.2 else Confidence.LOW
    return decision, confidence, normalised


def bayesian_update(
    alpha: float,
    beta: float,
    correct: bool,
    gamma: float,
) -> tuple[float, float]:
    """
    Fractional Beta conjugate update.

    correct: whether agent vote matched ground truth
    gamma:   oracle confidence tier weight (1.0 = developer, 0.7 = SAST, ...)
    """
    c = 1.0 if correct else 0.0
    return alpha + gamma * c, beta + gamma * (1.0 - c)


def omega_from_beta(alpha: float, beta: float) -> float:
    return alpha / (alpha + beta)


def _probit(p: float) -> float:
    """Rational approximation to the inverse normal CDF (Abramowitz & Stegun 26.2.17)."""
    if p > 0.5:
        return -_probit(1.0 - p)
    t = math.sqrt(-2.0 * math.log(p))
    c = (2.515517, 0.802853, 0.010328)
    d = (1.432788, 0.189269, 0.001308)
    return t - (c[0] + c[1] * t + c[2] * t**2) / (1.0 + d[0] * t + d[1] * t**2 + d[2] * t**3)


def omega_ci(alpha: float, beta: float, level: float = 0.95) -> tuple[float, float]:
    """
    Normal approximation credible interval for ω = alpha/(alpha+beta).

    Uses the Beta posterior's mean and variance; accurate when alpha+beta > ~8.
    Returns (lower, upper) clamped to [0, 1].
    """
    n = alpha + beta
    omega = alpha / n
    z  = abs(_probit((1.0 - level) / 2.0))  # positive z-score, e.g. 1.96 for 95%
    se = math.sqrt(omega * (1.0 - omega) / n)
    return max(0.0, omega - z * se), min(1.0, omega + z * se)


LAMBDA_DECAY = 0.95  # decay factor per week (spec §2.3.4)


def apply_decay(alpha: float, beta: float, weeks_elapsed: float) -> tuple[float, float]:
    """
    Apply exponential temporal decay to effective observation counts.

    Decays accumulated evidence toward the uninformative prior (1, 1).
    The prior floor is preserved: effective counts never drop below 1.
    """
    decay = LAMBDA_DECAY ** weeks_elapsed
    alpha_eff = 1.0 + (alpha - 1.0) * decay
    beta_eff  = 1.0 + (beta  - 1.0) * decay
    return alpha_eff, beta_eff
