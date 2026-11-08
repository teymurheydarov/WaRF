"""Behaviour demos for the log-odds review (spec lens). No model calls; agent calls stubbed."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
HOME = tempfile.mkdtemp(prefix="warf-spec-review-")
os.environ["WARF_HOME"] = HOME

from warf import orchestrator  # noqa: E402
from warf.engine import LLR_APPROVE, LLR_REJECT, pool_evidence, logodds_decision, sprt_boundary, B  # noqa: E402
from warf.calibration import Calibrator, p_reject_from_text  # noqa: E402
from warf.state import AgentProfile, DomainWeight, persona_hash, save_profiles, default_profiles  # noqa: E402

empty = Path(HOME) / "empty.jsonl"


def panel(omega, n=5, provider="claude_cli", model="haiku"):
    out = []
    for i in range(n):
        p = AgentProfile(name=f"S{i}", persona=f"P{i}", provider=provider, model=model,
                         persona_hash=persona_hash(f"P{i}"))
        for d in p.weights:
            p.weights[d] = DomainWeight(alpha=omega * 10, beta=(1 - omega) * 10)
        out.append(p)
    path = Path(HOME) / f"panel_{omega}_{n}.json"
    save_profiles(path, out)
    return path


def stub(vote):
    def f(persona, code, domain, **kw):
        return vote, "x", 1, 1, kw.get("provider"), kw.get("model")
    return f


print("A. SECURITY, five seats of one model, all APPROVE, uncalibrated, omega 0.4")
orchestrator._call_agent = stub(+1)
pp = panel(0.4)
for mode in ("vote", "logodds"):
    r = orchestrator.run_review("x", "SECURITY", pp, verbose=False, aggregate=mode, log_path=empty)
    print(f"   {mode:<8} -> {r.decision.value} [{r.confidence.value}]  L={r.sprt_lambda:+.3f}")

print("B. SECURITY / LOGIC, five seats of one model, all REJECT, omega 0.5 (spec 9.1: never above LOW)")
orchestrator._call_agent = stub(-1)
pp = panel(0.5)
for dom in ("LOGIC", "SECURITY"):
    r = orchestrator.run_review("x", dom, pp, verbose=False, aggregate="logodds", log_path=empty)
    print(f"   {dom:<9} -> {r.decision.value} [{r.confidence.value}]  L={r.sprt_lambda:+.3f}")

print("C. Decision readout whose probabilities are missing (provider renders 0.00 / 0.00), choice REJECT")
text = "p(APPROVE)=0.00  p(REJECT)=0.00  [jev-x: decision model, no reasoning]"
p = p_reject_from_text(text)
jev = AgentProfile(name="JEV", persona="q", provider="jev", model="jev-latest", persona_hash=persona_hash("q"))
e, tag = Calibrator(empty).evidence(jev, -1, p, 0.5)
print(f"   vote REJECT, p_reject read {p}, evidence {e:+.3f} ({tag})  <- counts toward APPROVE")

print("D. Spec 8: an unreadable log must not fail the review")
orchestrator._call_agent = stub(-1)
for what, content in (("non-UTF-8 byte", b'{"a": "\xe9"}\n'), ("JSON array line", b"[]\n"),
                      ("oracle as string", b'{"oracle": "DEVELOPER"}\n')):
    bad = Path(HOME) / f"bad_{what.replace(' ', '_')}.jsonl"
    bad.write_bytes(content)
    try:
        r = orchestrator.run_review("x", "LOGIC", pp, verbose=False, aggregate="logodds", log_path=bad)
        print(f"   {what:<18} ok -> {r.decision.value}")
    except Exception as exc:
        print(f"   {what:<18} CRASH {type(exc).__name__}: {exc}")

print("E. Early stop on a group mean: the first seat of a model crosses B alone; the full group would not")
seq = [-2.6, -0.3, -0.2, -0.4, -0.1]    # calibrated evidence of five seats of one model
for k in range(1, 6):
    lam, means = pool_evidence([("jev/jev-latest", e) for e in seq[:k]])
    print(f"   after {k} seat(s): L={lam:+.3f}  boundary={sprt_boundary(lam)}")
lam, means = pool_evidence([("jev/jev-latest", e) for e in seq])
print("   full pool verdict:", [x.value if hasattr(x, 'value') else round(x, 3) for x in logodds_decision(lam, means, "LOGIC")])

print("F. Disagreement rule alone (margin large): +1.0 and -2.5 in LOGIC")
lam, means = pool_evidence([("a/x", 1.0), ("b/y", -2.5)])
print("   ", [x.value if hasattr(x, 'value') else round(x, 3) for x in logodds_decision(lam, means, "LOGIC")])
