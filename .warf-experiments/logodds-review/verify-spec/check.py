import json, math, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, r"C:/workdir/warf/WaRF")
HOME = tempfile.mkdtemp(prefix="warf-vs-")
os.environ["WARF_HOME"] = HOME
os.environ["WARF_NO_BROWSER"] = "1"
from warf import orchestrator
from warf.engine import *
from warf.engine import LLR_APPROVE, LLR_REJECT, A, B
from warf.calibration import Calibrator, p_reject_from_text
from warf.state import AgentProfile, persona_hash, save_profiles

def panel(n, omega, provider="claude_cli", model="haiku"):
    ps = []
    for i in range(n):
        p = AgentProfile(name=f"S{i}", persona=f"P{i}.", provider=provider, model=model, persona_hash=persona_hash(f"P{i}."))
        for d in p.weights: 
            w = p.weights[d]
            # set alpha/beta so omega = omega with many obs
            w.alpha, w.beta = omega*1000, (1-omega)*1000
        ps.append(p)
    return ps

empty = Path(HOME)/"empty.jsonl"
print("=== F1: SECURITY, 5 uncalibrated APPROVE, omega 0.4 ===")
pp = Path(HOME)/"p.json"
save_profiles(pp, panel(5, 0.4))
def stub(vote, text="ok"):
    def f(persona, code, domain, **kw):
        return vote, text, 1, 1, kw.get("provider") or "claude_cli", kw.get("model") or "haiku"
    return f
orchestrator._call_agent = stub(+1)
for agg in ("vote", "logodds"):
    r = orchestrator.run_review("x=1", "SECURITY", pp, verbose=False, aggregate=agg, log_path=empty)
    print(agg, r.decision.value, r.confidence.value, round(r.sprt_lambda,3), [round(v.omega,3) for v in r.votes])
print("tau SEC", logodds_tau("SECURITY"), " need omega for MEDIUM APPROVE:", (logodds_tau("SECURITY")+math.log(2))/LLR_APPROVE)
for om in (0.5, 0.8, 0.99):
    save_profiles(pp, panel(5, om))
    r = orchestrator.run_review("x=1", "SECURITY", pp, verbose=False, aggregate="logodds", log_path=empty)
    print(" omega", om, r.decision.value, r.confidence.value, round(r.sprt_lambda,3))

print("=== F2: 5 REJECT omega 0.5 SECURITY / LOGIC ===")
save_profiles(pp, panel(5, 0.5))
orchestrator._call_agent = stub(-1)
for dom in ("SECURITY", "LOGIC", "PERFORMANCE"):
    r = orchestrator.run_review("x=1", dom, pp, verbose=False, aggregate="logodds", log_path=empty)
    print(dom, r.decision.value, r.confidence.value, round(r.sprt_lambda,3))
r = orchestrator.run_review("x=1", "LOGIC", pp, verbose=False)
print("vote mode LOGIC", r.decision.value, r.confidence.value, round(r.sprt_lambda,3), "votes", len(r.votes), "5*0.5*LLR_R=", 5*0.5*LLR_REJECT)
print("LOGIC thresholds: REJECT", math.log(2)/-LLR_REJECT, "APPROVE", math.log(2)/LLR_APPROVE)

print("=== F3: early stop on first strong seat ===")
lam_seq = []
es = [-2.6, -0.3, -0.2, -0.4, -0.1]
for k in range(1, 6):
    lam, g = pool_evidence([("jev/x", e) for e in es[:k]])
    lam_seq.append(round(lam,3))
print("running Λ", lam_seq, "B", B)
lam, g = pool_evidence([("jev/x", e) for e in es])
print("full", logodds_decision(lam, g, "LOGIC"))
# Run via run_review with monkeypatched calibrator evidence
seq = iter(es)
orig = Calibrator.evidence
Calibrator.evidence = lambda self, prof, vote, p, om: (next(seq), "platt")
save_profiles(pp, panel(5, 0.5, provider="jev", model="x"))
calls = []
def f(persona, code, domain, **kw):
    calls.append(1); return -1, "x", 1, 1, "jev", "x"
orchestrator._call_agent = f
r = orchestrator.run_review("x=1", "LOGIC", pp, verbose=False, aggregate="logodds", log_path=empty)
print("run_review:", r.decision.value, r.confidence.value, round(r.sprt_lambda,3), "calls", len(calls))
seq = iter(es); calls.clear()
r = orchestrator.run_review("x=1", "LOGIC", pp, verbose=False, aggregate="logodds", log_path=empty, no_early_stop=True)
print("no_early_stop:", r.decision.value, r.confidence.value, round(r.sprt_lambda,3), "calls", len(calls))
Calibrator.evidence = orig

print("=== F4: decision REJECT with zero probs ===")
text = "REJECT\np(APPROVE)=0.00  p(REJECT)=0.00  [jev: decision model, no reasoning]"
p = p_reject_from_text(text)
prof = AgentProfile(name="JEV", persona="q", provider="jev", model="x", persona_hash=persona_hash("q"))
print("p", p, "evidence", Calibrator(empty).evidence(prof, -1, p, 0.5))
print("vote-mode step for REJECT", vote_evidence(-1, 0.5))

print("=== F5: unreadable logs ===")
for name, content in (("nonutf8", b'{"a":1}\n\xff\xfe\n'), ("list", b'[]\n'), ("oraclestr", b'{"oracle":"DEVELOPER"}\n'),
                      ("votesstr", b'{"oracle":{"type":"DEVELOPER","x_star":1},"votes":["x"]}\n')):
    path = Path(HOME)/f"{name}.jsonl"; path.write_bytes(content)
    try:
        c = Calibrator(path); c.evidence(prof, -1, 0.9, 0.5); 
        print(name, "ok")
    except Exception as ex:
        print(name, "CRASH", type(ex).__name__, ex)
