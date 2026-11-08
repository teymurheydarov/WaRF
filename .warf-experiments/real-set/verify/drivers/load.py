import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parents[2]
items = [json.loads(l) for l in (HERE/"items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
recs = {}
for arm in ("claude","claude-strict","claude-advocate","claude-standard","jev"):
    recs[arm] = {}
    for p in sorted(HERE.glob(f"{arm}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); recs[arm][r["planted"]["id"]] = r
def rej(arm, i): return recs[arm][i]["decision"] == "REJECT"
def reply(arm, i):
    r = recs[arm][i]
    c = r["planted"].get("call")
    if c and c.get("reply"): return c["reply"]
    return "\n----\n".join(f'[{v["agent"]} {v["label"]}] {v.get("reasoning","")}' for v in r["votes"])
