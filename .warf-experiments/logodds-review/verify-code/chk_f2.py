import json, sys, collections, glob
sys.path.insert(0, r"C:/workdir/warf/WaRF")
from pathlib import Path
log = Path(r"C:/workdir/warf/WaRF/.warf/sessions.jsonl")
ss = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
nv = sum(len(s.get("votes",[])) for s in ss); nop = sum(1 for s in ss for v in s.get("votes",[]) if not v.get("persona"))
lab = [s for s in ss if (s.get("oracle") or {}).get("type")=="DEVELOPER" and (s.get("oracle") or {}).get("x_star") in (1,-1)]
print("sessions", len(ss), "votes", nv, "no persona", nop, "labelled sessions", len(lab))
print("labelled LLM votes", sum(1 for s in lab for v in s["votes"] if v.get("agent")!="SAST-BANDIT"),
      "with persona", sum(1 for s in lab for v in s["votes"] if v.get("persona")))
print("profiles in log", collections.Counter(s.get("profile") for s in ss))
print("providers in log", collections.Counter((v.get("provider"), v.get("model")) for s in ss for v in s.get("votes",[])).most_common(8))
from warf.calibration import Calibrator
from warf.state import load_profiles
c = Calibrator(log)
for pf in glob.glob(r"C:/workdir/warf/WaRF/.warf/*.json"):
    try: ps = load_profiles(Path(pf))
    except Exception as e: print(pf, "skip", type(e).__name__); continue
    print(Path(pf).name, [(p.name, p.persona_hash, c.history_size(p)) for p in ps])
# hash equality across providers in experiment logs
m = collections.defaultdict(set)
for f in glob.glob(r"C:/workdir/warf/WaRF/.warf-experiments/*/**/*.jsonl", recursive=True):
    for l in open(f, encoding="utf-8"):
        try: s = json.loads(l)
        except Exception: continue
        if not isinstance(s, dict): continue
        for v in s.get("votes",[]) or []:
            if isinstance(v, dict) and v.get("persona"):
                m[(v.get("agent"), v["persona"])].add(v.get("provider"))
for k, provs in m.items():
    if len(provs) > 1: print("shared hash", k, provs)
print("---profiles dir")
for pf in glob.glob(r"C:/workdir/warf/WaRF/.warf/profiles/*.json"):
    try: ps = load_profiles(Path(pf))
    except Exception as e: print(pf, "skip", type(e).__name__); continue
    print(Path(pf).name, [(p.name, p.persona_hash, c.history_size(p)) for p in ps])
