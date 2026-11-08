import json, math, os, random, sys, tempfile
from pathlib import Path
sys.path.insert(0, r"C:/workdir/warf/WaRF")
H = tempfile.mkdtemp(prefix="warf-vs-")
os.environ["WARF_HOME"] = H
os.environ["WARF_NO_BROWSER"] = "1"
from warf import orchestrator
from warf.engine import A, B, LLR_APPROVE, LLR_REJECT, logodds_tau, logodds_decision, Decision
from warf.calibration import Calibrator, fit_platt, p_reject_from_text, approve_logodds
from warf.state import AgentProfile, persona_hash, save_profiles, PERSONA_SKEPTIC
from warf.logger import session_dict

def sess(agent, ph, vote, y, provider, model, profile, reasoning=""):
    return {"profile": profile, "oracle": {"type": "DEVELOPER", "x_star": y},
            "votes": [{"agent": agent, "vote": vote, "persona": ph, "provider": provider,
                       "model": model, "reasoning": reasoning}]}

print("== F1: cross-model calibration leak ==")
ph = persona_hash(PERSONA_SKEPTIC)
log = Path(H) / "f1.jsonl"
rows = [sess("SKEPTIC", ph, 1, 1, "systemone", "jev-latest", "jev-five") for _ in range(10)]
rows += [sess("SKEPTIC", ph, -1, -1, "systemone", "jev-latest", "jev-five") for _ in range(10)]
log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
claude = AgentProfile(name="SKEPTIC", persona=PERSONA_SKEPTIC, persona_hash=ph, provider="claude_cli", model="haiku")
cal = Calibrator(log)
e, tag = cal.evidence(claude, -1, None, 0.5)
print("claude skeptic REJECT:", round(e, 3), tag, "B=", round(B, 3), "crosses B:", e <= B, "uncal:", round(0.5*LLR_REJECT, 3))

print("== F2: base rate / tau ==")
random.seed(1)
rs, ys = [], []
for _ in range(2000):
    # true posterior p_clean drawn so base rate ~0.76
    pc = random.betavariate(3.2, 1.0)
    pc = min(0.99, max(0.01, pc))
    y = 1 if random.random() < pc else -1
    p_rej = round(1 - pc, 2); p_rej = min(.99, max(.01, p_rej))
    rs.append(approve_logodds(p_rej)); ys.append(y)
fit = fit_platt(rs, ys)
print("fit a,b,prior,pi:", round(fit.a,3), round(fit.b,3), round(fit.prior_logodds,3), round(sum(1 for y in ys if y==1)/len(ys),3))
for pc in (0.6, 0.7, 0.75, 0.8):
    ev = fit.evidence(approve_logodds(1-pc))
    d, c, n = logodds_decision(ev, {"systemone/jev": ev}, "LOGIC")
    print(f" posterior P(clean)={pc}: evidence={ev:+.3f} -> {d.value} [{c.value}]  fitted posterior={1/(1+math.exp(-(fit.a+fit.b*approve_logodds(1-pc)))):.3f}")

print("== F3: running group mean / early stop ==")
def stub_factory(seq):
    it = iter(seq)
    def stub(persona, code, domain, **kw):
        vote, text = next(it)
        return vote, text, 0, 0, "systemone", "jev-x"
    return stub
class StubCal:
    def __init__(self, ev): self.ev = list(ev)
    def evidence(self, profile, vote, p, omega): return self.ev.pop(0), "platt"
names = ["S1", "S2", "S3"]
profs = [AgentProfile(name=n, persona=f"p {n}", persona_hash=persona_hash(f"p {n}"), provider="systemone", model="jev-x") for n in names]
pp = Path(H) / "p3.json"; save_profiles(pp, profs)
def ro(pr): 
    ch = "REJECT" if pr > .5 else "APPROVE"
    return f"{ch}\np(APPROVE)={1-pr:.2f}  p(REJECT)={pr:.2f}  [jev: decision model, no reasoning]"
seq = [(1, ro(0.05)), (-1, ro(0.7)), (-1, ro(0.7))]
for nes in (False, True):
    orchestrator._call_agent = stub_factory(seq)
    orig = orchestrator.Calibrator
    orchestrator.Calibrator = lambda path: StubCal([3.0, -1.0, -1.0])
    try:
        r = orchestrator.run_review("x", "LOGIC", pp, verbose=False, aggregate="logodds", no_early_stop=nes)
    finally:
        orchestrator.Calibrator = orig
    print(f" no_early_stop={nes}: {r.decision.value} [{r.confidence.value}] n_votes={len(r.votes)} sprt_lambda={r.sprt_lambda:+.3f} inside=({B:.3f},{A:.3f}):", B < r.sprt_lambda < A)
    sd = session_dict(r, "x", "prof")
    print("   logged sprt_fired", sd["sprt_fired"], "sprt_lambda", sd["sprt_lambda"])
# disagreement + HIGH
from warf.engine import pool_evidence, sprt_boundary
lam, means = pool_evidence([("m1", 4.0), ("m2", -1.0)])
print(" groups +4,-1: lambda", lam, "boundary", sprt_boundary(lam), " exhausted would be:", logodds_decision(lam, means, "LOGIC")[:2])

# Monte Carlo prefix-mean crossing
random.seed(2)
N = 200000; rho = 0.89; mu = 0.0; sd_ = 1.6
cross_prefix = cross_final = 0
for _ in range(N):
    z0 = random.gauss(0, 1)
    es = [mu + sd_*(math.sqrt(rho)*z0 + math.sqrt(1-rho)*random.gauss(0,1)) for _ in range(5)]
    s = 0; hit = False
    for k, e in enumerate(es, 1):
        s += e
        if s/k >= A or s/k <= B: hit = True; break
    cross_prefix += hit
    m = sum(es)/5
    cross_final += (m >= A or m <= B)
print(f" MC sd={sd_} rho={rho}: P(prefix cross)={cross_prefix/N:.4f} P(final cross)={cross_final/N:.4f}")

print("== F4: spec 9.1 domain dependence / theta logging ==")
for dom in ("LOGIC", "SECURITY", "PERFORMANCE"):
    tau = logodds_tau(dom)
    rej = 0.5*LLR_REJECT; app = 0.5*LLR_APPROVE
    print(f" {dom}: tau={tau:+.3f} REJECT@0.5 -> {logodds_decision(rej,{'g':rej},dom)[:2]}  APPROVE@0.5 -> {logodds_decision(app,{'g':app},dom)[:2]}")
    # omega for MEDIUM
    print(f"   omega for MEDIUM: reject {(math.log(2)-tau)/-LLR_REJECT*-1 if False else (math.log(2)+tau)/(-LLR_REJECT):.3f}  approve {(math.log(2)+tau)/LLR_APPROVE:.3f}")
d, c, n = logodds_decision(0.5, {"g": 0.5}, "SECURITY")
print(" SECURITY lambda=0.5:", d.value, c.value, "normalised", round(n, 4), "theta 0.2 -> vote-rule reads", "APPROVE" if n >= 0.2 else "REJECT")

print("== F5: missing probabilities ==")
txt = "REJECT\np(APPROVE)=0.00  p(REJECT)=0.00  [jev: decision model, no reasoning]"
p = p_reject_from_text(txt); print(" p_reject", p, "r", round(approve_logodds(p), 3))
log5 = Path(H) / "f5.jsonl"
rows = [sess("D", "h", 1, 1, "systemone", "j", "x") | {} for _ in range(10)]
for r_ in rows: r_["votes"][0]["p_reject"] = 0.2
rows2 = [sess("D", "h", -1, -1, "systemone", "j", "x") for _ in range(10)]
for r_ in rows2: r_["votes"][0]["p_reject"] = 0.8
rows2[0]["votes"][0]["p_reject"] = 1.0
log5.write_text("\n".join(json.dumps(r) for r in rows + rows2), encoding="utf-8")
try:
    print(Calibrator(log5).evidence(AgentProfile(name="D", persona="x", persona_hash="h"), -1, 0.7, 0.5))
except Exception as ex:
    print(" crash:", type(ex).__name__, ex)
rows2[0]["votes"][0]["p_reject"] = 0.0
log5.write_text("\n".join(json.dumps(r) for r in rows + rows2), encoding="utf-8")
try:
    print(Calibrator(log5).evidence(AgentProfile(name="D", persona="x", persona_hash="h"), -1, 0.7, 0.5))
except Exception as ex:
    print(" crash:", type(ex).__name__, ex)
