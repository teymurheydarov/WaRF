"""Did Claude's blinded batches hold the same text Jev got as its state, for the 100 commits?
Reads jev-five/verify/refute/states.jsonl, laya-near-chance/claude-review/{key.json,batches/}."""
import json
import re
from pathlib import Path

EXP = Path(__file__).resolve().parents[2]
sel = [json.loads(l) for l in (EXP / "laya-five" / "selection.jsonl").open(encoding="utf-8")]
states = {json.loads(l)["id"]: json.loads(l)["state"] for l in (EXP / "jev-five/verify/refute/states.jsonl").open(encoding="utf-8")}
key = json.loads((EXP / "laya-near-chance/claude-review/key.json").read_text(encoding="utf-8"))
bykey = {(k["commit"], k["file"]): k for k in key}
items = {}
for b in sorted((EXP / "laya-near-chance/claude-review/batches").glob("*.txt")):
    parts = re.split(r"<<<ITEM (\w+)>>>\n", b.read_text(encoding="utf-8"))
    for i in range(1, len(parts), 2):
        items[parts[i]] = parts[i + 1]
same = differ = missing = 0
for s in sel:
    k = bykey.get((s["commit"], s["file"]))
    if k is None or k["id"] not in items:
        missing += 1
        continue
    a = re.sub(r"\n<<<END \w+>>>\s*$", "", items[k["id"]]).strip()
    j = states[s["id"]].strip()
    if a == j:
        same += 1
    else:
        differ += 1
        if differ <= 3:
            print(s["id"], len(a), len(j), "claude-starts-with-jev" if a.startswith(j[:200]) else "")
print(f"same text {same}, differ {differ}, not found {missing} (of {len(sel)})")
