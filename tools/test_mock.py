"""
Dry-run pipeline test using hard-coded votes — no API calls required.
Simulates M-01 (div-by-zero, all REJECT, x*=-1).
"""
import sys
from pathlib import Path

# A dev tool, not part of the package: make the checkout importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warf.engine import SPRTState, sprt_update, synthesis, Decision, Confidence  # noqa: E402
from warf.state import default_profiles, save_profiles, load_profiles  # noqa: E402
from warf.orchestrator import VoteRecord, ReviewResult, apply_oracle  # noqa: E402
from warf.paths import profiles_dir  # noqa: E402

# A throwaway profile: this script resets it to uniform priors on every run,
# which must never happen to the real `default`.
PROFILES_PATH = profiles_dir() / "test_mock.json"

# Start from uniform priors
save_profiles(PROFILES_PATH, default_profiles())

mock_votes = [
    VoteRecord("SKEPTIC",  -1, 0.500, "No division guard — divide by zero is UB."),
    VoteRecord("ADVOCATE", -1, 0.500, "No guard present; crashes on b=0."),
    VoteRecord("AUDITOR",  -1, 0.500, "CWE-369: missing zero divisor check."),
]

print("=== WaRF Dry Run: M-01 [LOGIC] ===\n")

state = SPRTState()
early_decision = None
collected = []

for v in mock_votes:
    print(f"  [{v.agent_name}] omega={v.omega:.3f}  -> {'APPROVE' if v.vote==1 else 'REJECT'}")
    collected.append(v)
    state, boundary = sprt_update(state, v.vote, v.omega)
    print(f"    L={state.lambda_:.3f}", end="")
    if boundary:
        print(f"  SPRT boundary crossed: {boundary.value} [HIGH]")
        early_decision = boundary
        break
    else:
        print()

print()

if early_decision:
    result = ReviewResult(early_decision, Confidence.HIGH, "LOGIC", collected, state.lambda_)
else:
    d, conf, norm = synthesis(
        [v.vote for v in collected],
        [v.omega for v in collected],
        "LOGIC",
    )
    print(f"  Pool exhausted  L={state.lambda_:.3f}  normalised={norm:.3f}  theta=0.0")
    result = ReviewResult(d, conf, "LOGIC", collected, state.lambda_, norm)

print(f"  DECISION  : {result.decision.value}")
print(f"  CONFIDENCE: {result.confidence.value}")
print(f"  L (SPRT)  : {result.sprt_lambda:+.3f}")

print("\nOracle update (DEVELOPER, x*=REJECT):")
apply_oracle(result, -1, "DEVELOPER", PROFILES_PATH)

profiles = load_profiles(PROFILES_PATH)
print(f"\n{'Agent':<12}  {'alpha':>6}  {'beta':>6}  {'omega':>7}")
print("-" * 38)
for p in profiles:
    w = p.weights["LOGIC"]
    print(f"{p.name:<12}  {w.alpha:>6.2f}  {w.beta:>6.2f}  {w.omega:>7.3f}")
