import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, r"C:/workdir/warf/WaRF")
from warf.calibration import Calibrator
from warf.state import default_profiles
def readout(p): return f"p(APPROVE)={1-p:.2f}  p(REJECT)={p:.2f}  confidence=0.50  [laya: decision model, no reasoning]"
sk = default_profiles()[0]   # SKEPTIC, same persona text on every provider
tmp = Path(tempfile.mkdtemp()) / "s.jsonl"
rows = []
# 20 labelled sessions from a LAYA panel (profile laya_five) whose SKEPTIC is anti-informative:
for k in range(20):
    y = 1 if k % 2 else -1
    p = 0.9 if y == 1 else 0.1          # says REJECT on clean, APPROVE on defective
    rows.append({"profile": "laya_five", "votes": [{"agent": "SKEPTIC", "vote": 1 if p < .5 else -1, "provider": "laya", "model": "multilingual",
                 "persona": sk.persona_hash, "reasoning": readout(p)}], "oracle": {"type": "DEVELOPER", "x_star": y}})
tmp.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
cal = Calibrator(tmp)
# Now review with the default Claude (text) profile: SKEPTIC votes REJECT
print("claude text SKEPTIC REJECT ->", cal.evidence(sk, -1, None, 0.5))
print("claude text SKEPTIC APPROVE ->", cal.evidence(sk, 1, None, 0.5))
# and a Jev SKEPTIC (decision) saying p(REJECT)=0.9
print("jev SKEPTIC p=0.9 ->", cal.evidence(sk, -1, 0.9, 0.5))
