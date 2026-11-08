import json
from pathlib import Path
H = Path(__file__).resolve().parents[2]
items = [json.loads(l) for l in (H/"items.jsonl").open(encoding="utf-8")]
num = {it["base"]: k+1 for k, it in enumerate([i for i in items if i["kind"]=="planted"])}
rc = {}
for p in sorted(H.glob("claude.w*.jsonl")):
    for l in p.open(encoding="utf-8"):
        r = json.loads(l); rc[r["planted"]["id"]] = r
for it in items:
    if it["kind"]=="clean" and rc[it["id"]]["decision"]=="REJECT":
        print(f"===== #{num[it['base']]} {it['id']}")
        print(rc[it["id"]]["planted"]["call"]["reply"][:1500])
