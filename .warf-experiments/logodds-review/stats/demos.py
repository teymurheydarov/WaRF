import sys, os, math, json, random, tempfile
from pathlib import Path
sys.path.insert(0, "C:/workdir/warf/WaRF")
H = tempfile.mkdtemp(prefix="warf-stats-"); os.environ["WARF_HOME"] = H; os.environ["WARF_NO_BROWSER"] = "1"
from warf import orchestrator
from warf.engine import A, B, LLR_APPROVE, LLR_REJECT, logodds_decision, logodds_tau, pool_evidence, THETA, vote_evidence
from warf.calibration import Calibrator, fit_platt, p_reject_from_text
from warf.state import AgentProfile, persona_hash, save_profiles
from warf.logger import session_dict
L = lambda q: math.log(q/(1-q))

print("== 1. base rate dropped: calibrated agent with 80% clean history ==")
# agent whose readout is already a calibrated posterior: P(clean|r) = sigmoid(r), history 80% clean
rng = random.Random(3); rs, ys = [], []
while len(rs) < 2000:
    r = round(rng.gauss(L(0.8), 1.5), 2); r = max(-4.595, min(4.595, r))
    rs.append(r); ys.append(1 if rng.random() < 1/(1+math.exp(-r)) else -1)
f = fit_platt(rs, ys); print(f"fit a={f.a:.3f} b={f.b:.3f} logit(pi)={f.prior_logodds:.3f}")
for post in (0.6, 0.7, 0.8):
    p_rej = round(1-post, 2); r = math.log((1-p_rej)/p_rej); e = f.evidence(r)
    d, c, n = logodds_decision(e, {"jev/x": e}, "LOGIC")
    print(f"  agent says P(clean)={post:.2f} (p_reject {p_rej}) -> evidence {e:+.3f} -> {d.value} [{c.value}] score {n:+.3f}")

print("== 2. group mean moves back after crossing: one model, 3 seats ==")
seq = [3.0, -1.0, -1.0]
for k in range(1, 4):
    lam, means = pool_evidence([("jev/m", e) for e in seq[:k]]); print(f"  after {k} seats: Lambda={lam:+.3f}")
# through run_review with no_early_stop and stubbed calibrated evidence
prof = Path(H)/"p.json"
ph = persona_hash("p")
save_profiles(prof, [AgentProfile(name=f"S{i}", persona="p", provider="jev", model="m", persona_hash=ph) for i in range(3)])
it = iter(seq)
orchestrator._call_agent = lambda persona, code, domain, **kw: (1, "x", 0, 0, "jev", "m")
class FakeCal:
    def __init__(self, *a): pass
    def evidence(self, profile, vote, p, omega): return next(it), "platt"
orchestrator.Calibrator = FakeCal
r = orchestrator.run_review("x", "LOGIC", prof, verbose=False, aggregate="logodds", no_early_stop=True)
rec = session_dict(r, "x.py")
print(f"  no_early_stop: decision {rec['decision']} [{rec['confidence']}] sprt_lambda {rec['sprt_lambda']} sprt_fired {rec['sprt_fired']} normalised {rec['normalised_score']}")
it = iter(seq)
r = orchestrator.run_review("x", "LOGIC", prof, verbose=False, aggregate="logodds")
print(f"  early stop: {r.decision.value} [{r.confidence.value}] after {len(r.votes)} of 3 seats, Lambda {r.sprt_lambda:+.2f}")
orchestrator.Calibrator = Calibrator

print("== 2b. multiple looks: P(HIGH) any-prefix vs final mean, 5 near-copy seats ==")
rng = random.Random(5); N = 200000; any_hit = fin_hit = 0
for _ in range(N):
    c = rng.gauss(0.0, 1.3); es = [c + rng.gauss(0, 0.45) for _ in range(5)]
    hit = False
    for k in range(1, 6):
        m = sum(es[:k])/k
        if m >= A or m <= B: hit = True; break
    any_hit += hit; m = sum(es)/5; fin_hit += (m >= A or m <= B)
print(f"  corr~{1.3**2/(1.3**2+0.45**2):.2f}: P(cross on some prefix)={any_hit/N:.4f}  P(final mean crosses)={fin_hit/N:.4f}")

print("== 3. spec 9.1 claim by domain: one uncalibrated model, all seats same vote, omega 0.5 ==")
for dom in THETA:
    for v in (1, -1):
        e = vote_evidence(v, 0.5); d, c, n = logodds_decision(e, {"g": e}, dom)
        print(f"  {dom:<12} vote {v:+d}: Lambda {e:+.3f} tau {logodds_tau(dom):+.3f} -> {d.value} [{c.value}] score {n:+.3f} theta {THETA[dom]}")
print("  SECURITY APPROVE needs omega >=", round((math.log(2)+logodds_tau('SECURITY'))/LLR_APPROVE, 3), "to reach MEDIUM alone")

print("== 4. normalised score vs logged theta ==")
d, c, n = logodds_decision(0.5, {"g": 0.5}, "SECURITY")
print(f"  SECURITY Lambda 0.5 -> {d.value}, normalised {n:+.3f}, logged theta {THETA['SECURITY']} (vote-mode rule score>=theta would say {'APPROVE' if n >= THETA['SECURITY'] else 'REJECT'})")

print("== 5. calibration ignores profile/provider/model ==")
log = Path(H)/"mix.jsonl"
php = persona_hash("You are SKEPTIC.")
lines = []
# SKEPTIC persona run under profile 'jev-five' on Jev: always REJECT on defective, APPROVE on clean (perfect)
for y in [1]*10 + [-1]*10:
    lines.append({"profile": "jev-five", "votes": [{"agent": "SKEPTIC", "persona": php, "provider": "jev", "model": "jev-latest", "vote": y,
                  "reasoning": f"p(APPROVE)={0.9 if y==1 else 0.1:.2f}  p(REJECT)={0.1 if y==1 else 0.9:.2f}  [jev: decision model, no reasoning]"}],
                  "oracle": {"type": "DEVELOPER", "x_star": y}})
log.write_text("\n".join(json.dumps(l) for l in lines)+"\n", encoding="utf-8")
cal = Calibrator(log)
claude_skeptic = AgentProfile(name="SKEPTIC", persona="You are SKEPTIC.", provider="claude_cli", model="haiku", persona_hash=php)
print("  Claude SKEPTIC (never labelled) REJECT evidence:", cal.evidence(claude_skeptic, -1, None, 0.5),
      " vs uncalibrated", round(vote_evidence(-1, 0.5), 3))

print("== 6. readout with missing probabilities ==")
txt = "p(APPROVE)=0.00  p(REJECT)=0.00  [jev: decision model, no reasoning]"
p = p_reject_from_text(txt); print("  parsed p_reject", p, "-> r", round(math.log((1-p)/p), 2), "for a REJECT choice")
