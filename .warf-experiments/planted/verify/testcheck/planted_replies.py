import json, sys
from pathlib import Path
H = Path(__file__).resolve().parents[2]
items = [json.loads(l) for l in (H/"items.jsonl").open(encoding="utf-8")]
pl = [i for i in items if i["kind"]=="planted"]
rc = {}
for p in sorted(H.glob("claude.w*.jsonl")):
    for l in p.open(encoding="utf-8"):
        r = json.loads(l); rc[r["planted"]["id"]] = r
want = [int(x) for x in sys.argv[1].split(",")]
for n in want:
    it = pl[n-1]
    print(f"===== #{n} {it['id']} {rc[it['id']]['decision']}  MUT: {it['mutated'].strip()[:90]}")
    print(rc[it["id"]]["planted"]["call"]["reply"][:int(sys.argv[2])].replace("\n"," "))
