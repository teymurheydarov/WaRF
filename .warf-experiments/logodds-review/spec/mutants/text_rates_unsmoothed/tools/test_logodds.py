"""
Log-odds aggregation test (docs/spec/logodds-aggregation.md, section 9).

Pure checks of the evidence, pooling and calibration rules, then one review
through run_review with the agent call stubbed out. No model, no network, no
credentials; the profiles and the session log live in a temporary directory.

Usage:  python tools/test_logodds.py
"""
import json
import math
import os
import random
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_HOME = tempfile.mkdtemp(prefix="warf-logodds-")
os.environ["WARF_HOME"] = _HOME
os.environ["WARF_NO_BROWSER"] = "1"

from warf import orchestrator  # noqa: E402
from warf.engine import (  # noqa: E402
    A, B, LLR_APPROVE, LLR_REJECT, Decision, Confidence,
    logodds_tau, pool_evidence, logodds_decision, capped_evidence,
)
from warf.calibration import (  # noqa: E402
    Calibrator, fit_platt, p_reject_from_text,
)
from warf.logger import session_dict  # noqa: E402
from warf.state import AgentProfile, persona_hash, save_profiles  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


def close(x, y, tol=1e-9):
    return abs(x - y) <= tol


def logit(q):
    return math.log(q / (1 - q))


def readout(p_reject):
    """WaRF's own rendering of a decision-model answer (providers.SystemOneProvider)."""
    choice = "REJECT" if p_reject > 0.5 else "APPROVE"
    return (f"{choice}\np(APPROVE)={1 - p_reject:.2f}  p(REJECT)={p_reject:.2f}  "
            f"confidence=0.50  [jev-test: decision model, no reasoning]")


def labelled_session(agent, persona, vote, y, reasoning=""):
    return {
        "session_id": f"s-{random.random()}", "domain": "LOGIC",
        "votes": [{"agent": agent, "vote": vote, "persona": persona, "reasoning": reasoning}],
        "oracle": {"type": "DEVELOPER", "x_star": y},
    }


def write_log(path, sessions):
    path.write_text("".join(json.dumps(s) + "\n" for s in sessions), encoding="utf-8")


print("\n=== evidence, pooling and decision ===")

# 1. Seats of one model count once.
one_model = [("claude_cli/haiku", 0.5 * LLR_REJECT)] * 5
lam, groups = pool_evidence(one_model)
check(close(lam, 0.5 * LLR_REJECT), f"five REJECTs of one model pool to {lam:.3f} (one vote's worth)")
decision, confidence, _ = logodds_decision(lam, groups, "LOGIC")
check(decision is Decision.REJECT and confidence is Confidence.LOW,
      f"-> {decision.value} [{confidence.value}]: 0.627 nats is under the ln 2 margin")

# 2. Different models add up.
lam, _ = pool_evidence([("jev/jev-latest", 0.5 * LLR_REJECT), ("laya/multilingual", 0.5 * LLR_REJECT)])
check(close(lam, LLR_REJECT), f"one REJECT from each of two models sums to {lam:.3f}")

# 3. An uncalibrated decision agent is capped at its vote-mode step.
check(close(capped_evidence(logit(0.01), 0.5), 0.5 * LLR_REJECT), "p(REJECT)=0.99 is capped at ω·LLR_REJECT")
check(close(capped_evidence(logit(0.99), 0.5), 0.5 * LLR_APPROVE), "p(REJECT)=0.01 is capped at ω·LLR_APPROVE")
check(close(capped_evidence(logit(0.4), 0.5), logit(0.4)), "p(REJECT)=0.6 stays at logit(0.4) inside the cap")

# 8. The domain threshold.
check(close(logodds_tau("SECURITY"), logit(0.6)) and logodds_tau("LOGIC") == 0.0
      and close(logodds_tau("PERFORMANCE"), logit(0.45)), "τ = logit((1 + θ)/2) per domain")

# 9. Models that disagree send the change to a human.
lam, groups = pool_evidence([("a/x", 1.0), ("b/y", -1.2)])
decision, confidence, norm = logodds_decision(lam, groups, "LOGIC")
check(confidence is Confidence.LOW, f"means +1.0 and -1.2 -> {decision.value} [{confidence.value}]")
check(close(norm, 2 / (1 + math.exp(-lam)) - 1), "normalised score is 2σ(Λ−τ)−1")

lam, groups = pool_evidence([("a/x", -1.5), ("b/y", -1.2)])
check(logodds_decision(lam, groups, "LOGIC")[1] is Confidence.MEDIUM, "agreeing models with a clear margin -> MEDIUM")
check(logodds_decision(0.5, {"a/x": 0.5}, "LOGIC")[1] is Confidence.LOW, "a margin under ln 2 -> LOW")

print("\n=== reading a decision model's probability ===")
check(p_reject_from_text(readout(0.88)) == 0.88, "p(REJECT) is read from the decision readout")
check(p_reject_from_text("REJECT\nI estimate p(REJECT)=0.88 here.") is None, "never from a text agent's prose")
check(p_reject_from_text(readout(1.0)) == 0.99 and p_reject_from_text(readout(0.0)) == 0.01,
      "clamped to [0.01, 0.99]")

print("\n=== calibration ===")
rng = random.Random(7)

# 5. The fit recovers the slope of a reviewer that is informative but overconfident.
rs = [rng.uniform(-4, 4) for _ in range(600)]
ys = [1 if rng.random() < 1 / (1 + math.exp(-0.5 * r)) else -1 for r in rs]
fit = fit_platt(rs, ys)
check(fit is not None and abs(fit.b - 0.5) < 0.15, f"fitted slope {fit.b:.3f} ≈ 0.5")

# 4. An uninformative reviewer on an 80 % clean history gives no evidence.
rs = [rng.uniform(-4, 4) for _ in range(300)]
ys = [1 if rng.random() < 0.8 else -1 for _ in rs]
fit = fit_platt(rs, ys)
worst = max(abs(fit.evidence(r)) for r in (-4.0, 0.0, 4.0))
check(worst < 0.3, f"base rate removed: |evidence| ≤ {worst:.3f} for any p")

persona = "Should this change be merged?"
ph = persona_hash(persona)
jev = AgentProfile(name="JEV", persona=persona, provider="jev", model="jev-latest", persona_hash=ph)
text_persona = "Review strictly."
th = persona_hash(text_persona)
auditor = AgentProfile(name="AUDITOR", persona=text_persona, provider="claude_cli", model="haiku",
                       persona_hash=th)

# 6. Text-agent rates; 7. retired persona votes are ignored.
log = Path(_HOME) / "calib.jsonl"
sessions = []
sessions += [labelled_session("AUDITOR", th, -1, -1) for _ in range(9)]
sessions += [labelled_session("AUDITOR", th, +1, -1) for _ in range(1)]
sessions += [labelled_session("AUDITOR", th, -1, +1) for _ in range(1)]
sessions += [labelled_session("AUDITOR", th, +1, +1) for _ in range(9)]
sessions += [labelled_session("AUDITOR", "retired0000", +1, -1) for _ in range(50)]
write_log(log, sessions)
cal = Calibrator(log)
e, tag = cal.evidence(auditor, -1, None, 0.5)
expected = math.log(((1 + 1) / (10 + 2)) / ((9 + 1) / (10 + 2)))
check(tag == "rates" and close(e, expected), f"REJECT evidence {e:.3f} = ln 0.2 from the measured rates")
check(cal.history_size(auditor) == 20, "the 50 votes of a retired persona are not used")

# A decision agent needs 10 labelled votes of each class before its p is trusted.
sessions = [labelled_session("JEV", ph, -1, -1, readout(0.9)) for _ in range(9)]
sessions += [labelled_session("JEV", ph, +1, +1, readout(0.1)) for _ in range(10)]
write_log(log, sessions)
e, tag = Calibrator(log).evidence(jev, -1, 0.99, 0.5)
check(tag == "capped" and close(e, 0.5 * LLR_REJECT), "9 defective labels: still capped")
sessions.append(labelled_session("JEV", ph, -1, -1, readout(0.9)))
write_log(log, sessions)
e, tag = Calibrator(log).evidence(jev, -1, 0.9, 0.5)
check(tag == "platt" and e < 0, f"10 of each: calibrated, p(REJECT)=0.9 -> evidence {e:.3f}")

e, tag = Calibrator(Path(_HOME) / "missing.jsonl").evidence(jev, -1, 0.9, 0.5)
check(tag == "capped", "a missing log leaves every agent uncalibrated")

print("\n=== run_review ===")
profiles_path = Path(_HOME) / "panel.json"
panel = [AgentProfile(name=f"S{i}", persona=f"Persona {i}.", provider="claude_cli", model="haiku",
                      persona_hash=persona_hash(f"Persona {i}.")) for i in range(5)]
save_profiles(profiles_path, panel)

calls = []


def stub_reject(persona, code, domain, **kw):
    calls.append(persona)
    return -1, "looks wrong", 10, 5, kw.get("provider") or "claude_cli", kw.get("model") or "haiku"


orchestrator._call_agent = stub_reject
empty_log = Path(_HOME) / "empty.jsonl"

# 12. vote mode is unchanged: five REJECTs at ω 0.5 cross B at the fourth vote.
r = orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False)
check(r.decision is Decision.REJECT and r.confidence is Confidence.HIGH and len(r.votes) == 4
      and close(r.sprt_lambda, 4 * 0.5 * LLR_REJECT, 1e-12), "vote mode: REJECT [HIGH] after 4 votes, as before")

# 11. logodds mode: the same five seats are one model -> one vote's worth.
calls.clear()
r = orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False,
                            aggregate="logodds", log_path=empty_log)
check(len(calls) == 5 and r.decision is Decision.REJECT and r.confidence is Confidence.LOW,
      f"logodds: all 5 asked, {r.decision.value} [{r.confidence.value}]")
check(close(r.sprt_lambda, 0.5 * LLR_REJECT, 1e-12), f"Λ = {r.sprt_lambda:.3f}")
rec = session_dict(r, "x.py")
check(rec.get("aggregate") == "logodds"
      and all(v.get("calibration") == "omega" and "evidence" in v and "p_reject" in v for v in rec["votes"]),
      "the session record carries aggregate, evidence, calibration and p_reject")
check("aggregate" not in session_dict(orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False),
                                      "x.py"), "a vote-mode record is unchanged")

# Two models reach HIGH together when their calibrated evidence is strong.
mixed = [AgentProfile(name="JEV", persona=persona, provider="jev", model="jev-latest", persona_hash=ph),
         AgentProfile(name="LAYA", persona=persona, provider="laya", model="multilingual", persona_hash=ph)]
save_profiles(profiles_path, mixed)
history = []
for name in ("JEV", "LAYA"):
    history += [labelled_session(name, ph, -1, -1, readout(0.95)) for _ in range(20)]
    history += [labelled_session(name, ph, +1, +1, readout(0.05)) for _ in range(20)]
write_log(log, history)


def stub_decision(persona, code, domain, **kw):
    text = readout(0.95)
    return -1, text.split("\n", 1)[1], 10, 0, kw["provider"], kw["model"]


orchestrator._call_agent = stub_decision
r = orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False, aggregate="logodds", log_path=log)
check(r.decision is Decision.REJECT and r.confidence is Confidence.HIGH and r.sprt_lambda <= B,
      f"two calibrated models: REJECT [HIGH], Λ = {r.sprt_lambda:.2f}")
check(all(v.calibration == "platt" and v.p_reject == 0.95 for v in r.votes), "both votes calibrated from p")

# 12. Errors.
for kwargs, what in (({"aggregate": "logodds", "debate": True}, "logodds with debate"),
                     ({"aggregate": "average"}, "an unknown mode")):
    try:
        orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False, **kwargs)
    except ValueError:
        check(True, f"{what} raises ValueError")
    else:
        check(False, f"{what} raises ValueError")

check(A > 0 > B, "boundaries unchanged")
print("\nAll log-odds checks passed.")
