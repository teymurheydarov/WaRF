import sys, os, io, json, tempfile, contextlib, subprocess, math, random
from pathlib import Path
sys.path.insert(0, r"C:/workdir/warf/WaRF")
os.environ["WARF_HOME"] = tempfile.mkdtemp()
import warf.orchestrator as orch
from warf.state import default_profiles, save_profiles, DomainWeight, AgentProfile, persona_hash
from warf.logger import session_dict, result_from_session
from warf.engine import LLR_REJECT, LLR_APPROVE, A, B
from warf.calibration import Calibrator

def readout(p):
    return f"p(APPROVE)={1-p:.2f}  p(REJECT)={p:.2f}  confidence=0.50  [jev-x: decision model, no reasoning]"
BEH = {}; TIMEOUTS = set()
def stub(persona, code, domain, *, user_message=None, input_label="", context=None, provider=None, model=None):
    name = next(p.name for p in PROFS if p.persona == persona)
    if name in TIMEOUTS: raise subprocess.TimeoutExpired("x", 1)
    kind, val = BEH[name]
    if kind == "dec":
        return (-1 if val > .5 else 1), readout(val), 1, 1, provider or "jev", model or "jev-latest"
    return val, "some reasoning", 1, 1, provider if provider is not None else "anthropic", model if model is not None else "m"
orch._call_agent = stub
orch.bandit_vote = lambda p: (-1, "B101 high", 1, 1)

tmp = Path(tempfile.mkdtemp()); pp = tmp / "p.json"
PROFS = default_profiles()
for p in PROFS: p.provider, p.model = "jev", "jev-latest"
save_profiles(pp, PROFS)

def run(label, log, **kw):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            r = orch.run_review("code", kw.pop("domain", "LOGIC"), pp, aggregate="logodds", log_path=log, sast_path=kw.pop("sast_path", None), **kw)
        d = session_dict(r, "a")
        print(f"[{label}] {r.decision.value} [{r.confidence.value}] L={r.sprt_lambda:+.3f} n={len(r.votes)} norm={r.normalised_score}",
              [(v['agent'], v['calibration'], v['evidence']) for v in d['votes']])
        # label path
        rr = result_from_session(json.loads(json.dumps(d)))
        orch.apply_oracle(rr, -1, "DEVELOPER", pp, verbose=False); save_profiles(pp, PROFS)
        return r, buf.getvalue()
    except Exception as e:
        print(f"[{label}] EXC {e!r}"); return None, buf.getvalue()

nolog = tmp / "none.jsonl"
for p in PROFS: BEH[p.name] = ("dec", 0.99)
run("uncal decision, all reject", nolog)
r, out = run("verbose+demo+reason", nolog, verbose=True, demo=True, reason=True)
run("sast logodds SECURITY", nolog, domain="SECURITY", sast_path=Path("x.py"))
r, out = run("sast demo", nolog, domain="SECURITY", sast_path=Path("x.py"), verbose=False, demo=True)
TIMEOUTS.update(["SKEPTIC", "AUDITOR"]); run("timeouts", nolog)
TIMEOUTS.update([p.name for p in PROFS]); run("all timeout", nolog); TIMEOUTS.clear()
run("agents filter", nolog, agents=["skeptic"])
run("max_agents", nolog, max_agents=2)

# calibrated log: SKEPTIC decision votes where p is strongly informative
rng = random.Random(1); sess = []
for k in range(60):
    y = 1 if k % 2 else -1
    p = 0.95 if y == -1 else 0.05
    sess.append({"votes": [{"agent": "SKEPTIC", "vote": -y, "persona": PROFS[0].persona_hash, "reasoning": readout(p)}], "oracle": {"type": "DEVELOPER", "x_star": y}})
cal = tmp / "cal.jsonl"; cal.write_text("".join(json.dumps(s)+"\n" for s in sess), encoding="utf-8")
# order: weights equal -> SKEPTIC first
BEH["SKEPTIC"] = ("dec", 0.95)
for n in ["ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY"]: BEH[n] = ("dec", 0.05)
run("early stop on first seat", cal)
run("no_early_stop", cal, no_early_stop=True)
# text agents with empty provider
for p in PROFS: p.provider, p.model = None, None
save_profiles(pp, PROFS)
for p in PROFS: BEH[p.name] = ("txt", -1)
_old = orch._call_agent
orch._call_agent = lambda *a, **k: (lambda r: (r[0], r[1], r[2], r[3], "", ""))(_old(*a, **k))
run("empty provider text agents", nolog)
