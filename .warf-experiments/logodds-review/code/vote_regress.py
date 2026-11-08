"""Run vote-mode scenarios against a given warf package root; print JSON results.
usage: python vote_regress.py <root>"""
import sys, json, io, contextlib, subprocess, tempfile, os
from pathlib import Path
root = sys.argv[1]
sys.path.insert(0, root)
os.environ["WARF_HOME"] = tempfile.mkdtemp()
import warf.orchestrator as orch
from warf.state import default_profiles, save_profiles, DomainWeight
from warf.logger import session_dict

# deterministic stub: vote pattern per scenario
PATTERN = {}
TIMEOUTS = set()
def stub(persona, code, domain, *, user_message=None, input_label="", context=None, provider=None, model=None):
    name = next(p.name for p in PROFS if p.persona == persona)
    if name in TIMEOUTS and user_message is None:
        raise subprocess.TimeoutExpired("x", 1)
    rnd2 = user_message is not None
    v = PATTERN[name][1 if rnd2 else 0]
    return v, f"{'APPROVE' if v==1 else 'REJECT'} reason for {name} r{2 if rnd2 else 1}\nline2", 10, 5, provider or "anthropic", model or "m"
orch._call_agent = stub

def sast_stub(path):
    return SAST_RESULT
orch.bandit_vote = sast_stub
SAST_RESULT = None

tmp = Path(tempfile.mkdtemp())
pp = tmp / "p.json"
PROFS = default_profiles()
ws = [(8, 2), (5, 3), (3, 3), (2, 4), (1, 1)]
for p, (a, b) in zip(PROFS, ws):
    for d in p.weights: p.weights[d] = DomainWeight(alpha=a, beta=b)
save_profiles(pp, PROFS)

scen = []
def add(name, pattern, **kw):
    scen.append((name, pattern, kw))
allR = {p.name: (-1, -1) for p in PROFS}
allA = {p.name: (1, 1) for p in PROFS}
mixed = {"SKEPTIC": (-1, -1), "ADVOCATE": (1, -1), "AUDITOR": (-1, 1), "TEST-FOCUSED": (1, 1), "BOUNDARY": (1, -1)}
mixed2 = {"SKEPTIC": (1, 1), "ADVOCATE": (-1, -1), "AUDITOR": (1, 1), "TEST-FOCUSED": (-1, -1), "BOUNDARY": (1, 1)}
for dom in ("LOGIC", "SECURITY", "PERFORMANCE"):
    for pn, pat in (("allR", allR), ("allA", allA), ("mixed", mixed), ("mixed2", mixed2)):
        for kw in ({}, {"no_early_stop": True}, {"debate": True}, {"debate": True, "no_early_stop": True},
                   {"agents": ["advocate", "BOUNDARY"]}, {"max_agents": 2}, {"demo": True, "verbose": False, "reason": True},
                   {"timeouts": ["SKEPTIC", "AUDITOR"]}, {"sast": (-1, "issue x", 1, 2)}, {"sast": (1, "No security findings detected.", 0, 0)},
                   {"sast": (-1, "issue x", 1, 2), "no_early_stop": True}, {"sast": (-1, "issue", 1, 1), "demo": True, "verbose": False}):
            add(f"{dom}-{pn}-{sorted(kw)}", pat, domain=dom, **kw)
add("all-timeout", allR, domain="LOGIC", timeouts=[p.name for p in PROFS])

out = []
for name, pat, kw in scen:
    PATTERN.clear(); PATTERN.update(pat)
    TIMEOUTS.clear(); TIMEOUTS.update(kw.pop("timeouts", []))
    s = kw.pop("sast", None)
    SAST_RESULT = s
    dom = kw.pop("domain")
    sast_path = Path("x.py") if s is not None else None
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            r = orch.run_review("code", dom, pp, sast_path=sast_path, **{"verbose": True, **kw})
        d = session_dict(r, "art")
        d.pop("session_id"); d.pop("created_at")
        res = {"result": d, "conf": r.confidence.value}
        updates = orch.apply_oracle(r, -1, "DEVELOPER", pp, verbose=False)
        save_profiles(pp, PROFS)  # restore weights
        res["updates"] = [{k: v for k, v in u.items() if k != "timestamp"} for u in updates]
    except Exception as e:
        res = {"error": repr(e)}
    res["stdout"] = buf.getvalue()
    out.append((name, res))
print(json.dumps(out, sort_keys=True, default=str))
