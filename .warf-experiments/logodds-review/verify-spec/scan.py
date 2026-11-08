import json, re, sys
from pathlib import Path
pat = re.compile(r"p\(APPROVE\)=([0-9.]+)\s+p\(REJECT\)=([0-9.]+)")
tot = zero = disagree = 0
for f in Path(".").rglob("*.jsonl"):
    if "logodds-review" in str(f): continue
    try: lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError: continue
    for l in lines:
        if "decision model, no reasoning" not in l: continue
        try: s = json.loads(l)
        except Exception: continue
        if not isinstance(s, dict): continue
        for v in s.get("votes", []) or []:
            if not isinstance(v, dict): continue
            m = pat.search(v.get("reasoning", "") or "")
            if not m: continue
            tot += 1
            pa, pr = float(m.group(1)), float(m.group(2))
            if pa + pr < 0.5: zero += 1
            elif (pr > 0.5 and v.get("vote") == 1) or (pr < 0.5 and v.get("vote") == -1): disagree += 1
print("readouts", tot, "near-zero probs", zero, "vote disagrees with p side", disagree)
