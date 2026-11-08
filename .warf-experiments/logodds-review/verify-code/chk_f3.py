import json, sys, tempfile, os
from pathlib import Path
sys.path.insert(0, r"C:/workdir/warf/WaRF")
H = tempfile.mkdtemp(); os.environ["WARF_HOME"] = H; os.environ["WARF_NO_BROWSER"] = "1"
from warf import orchestrator
from warf.state import AgentProfile, persona_hash, save_profiles
from warf.logger import session_dict
def ro(p): return f"p(APPROVE)={1-p:.2f}  p(REJECT)={p:.2f}  [jev-x: decision model, no reasoning]"
names = ["SKEPTIC","ADVOCATE","AUDITOR","TEST-FOCUSED","BOUNDARY"]
panel = [AgentProfile(name=n, persona=f"P {n}", provider="jev", model="jev-latest", persona_hash=persona_hash(f"P {n}")) for n in names]
pp = Path(H)/"p.json"; save_profiles(pp, panel)
h = panel[0].persona_hash
sess = [{"votes":[{"agent":"SKEPTIC","vote":-1,"persona":h,"reasoning":ro(0.95)}],"oracle":{"type":"DEVELOPER","x_star":-1}} for _ in range(20)]
sess += [{"votes":[{"agent":"SKEPTIC","vote":1,"persona":h,"reasoning":ro(0.05)}],"oracle":{"type":"DEVELOPER","x_star":1}} for _ in range(20)]
log = Path(H)/"s.jsonl"; log.write_text("".join(json.dumps(s)+"\n" for s in sess), encoding="utf-8")
prof_by_persona = {f"P {n}": n for n in names}
def stub(persona, code, domain, **kw):
    p = 0.95 if prof_by_persona[persona] == "SKEPTIC" else 0.05
    return (-1 if p > .5 else 1), ro(p), 1, 1, kw["provider"], kw["model"]
orchestrator._call_agent = stub
for nes in (False, True):
    r = orchestrator.run_review("x=1", "LOGIC", pp, verbose=False, aggregate="logodds", log_path=log, no_early_stop=nes)
    rec = session_dict(r, "x.py")
    print(f"no_early_stop={nes}: {r.decision.value} [{r.confidence.value}] L={r.sprt_lambda:.3f} n={len(r.votes)} fired={rec['sprt_fired']}",
          [(v.agent_name, round(v.evidence,3), v.calibration) for v in r.votes])
# Reverse order: SKEPTIC last (give others higher omega via agents order? use profile ordering with SKEPTIC last)
panel2 = panel[1:] + panel[:1]; save_profiles(pp, panel2)
r = orchestrator.run_review("x=1", "LOGIC", pp, verbose=False, aggregate="logodds", log_path=log)
print("SKEPTIC last:", r.decision.value, r.confidence.value, round(r.sprt_lambda,3), len(r.votes))
