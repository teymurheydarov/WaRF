import json, sys, tempfile, os
from pathlib import Path
sys.path.insert(0, r"C:/workdir/warf/WaRF")
os.environ["WARF_HOME"] = tempfile.mkdtemp()
from warf.calibration import Calibrator
from warf.state import default_profiles
prof = [p for p in default_profiles() if p.name == "SKEPTIC"][0]
h = prof.persona_hash
def ro(p):
    return f"{'REJECT' if p>0.5 else 'APPROVE'}\np(APPROVE)={1-p:.2f}  p(REJECT)={p:.2f}  [laya-x: decision model, no reasoning]"
sess = []
for i in range(10):  # clean, laya rejects at 0.9
    sess.append({"profile":"laya-five","votes":[{"agent":"SKEPTIC","vote":-1,"persona":h,"provider":"laya","model":"laya-x","reasoning":ro(0.9)}],"oracle":{"type":"DEVELOPER","x_star":1}})
for i in range(10):  # defective, laya approves at 0.1
    sess.append({"profile":"laya-five","votes":[{"agent":"SKEPTIC","vote":1,"persona":h,"provider":"laya","model":"laya-x","reasoning":ro(0.1)}],"oracle":{"type":"DEVELOPER","x_star":-1}})
d = Path(tempfile.mkdtemp()); log = d/"s.jsonl"
log.write_text("".join(json.dumps(s)+"\n" for s in sess), encoding="utf-8")
c = Calibrator(log)
print("history", c.history_size(prof))
# a claude text SKEPTIC (different provider) -> same profile name+hash
print("claude text SKEPTIC REJECT ->", c.evidence(prof, -1, None, 0.5))
print("claude text SKEPTIC APPROVE ->", c.evidence(prof, 1, None, 0.5))
print("jev SKEPTIC p=0.9 ->", c.evidence(prof, -1, 0.9, 0.5))
# control: same-model calibration would also flip -- i.e. the issue is only cross-model sharing
