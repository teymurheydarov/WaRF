"""Print the replies of the six discordant items (Claude alone and the five seats), and the plant."""
import json
import sys
from pathlib import Path

H = Path(__file__).resolve().parents[2]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
items = {json.loads(l)["id"]: json.loads(l) for l in (H / "items.jsonl").open(encoding="utf-8")}
pl = [i for i in items.values() if i["kind"] == "planted"]
num = {it["base"]: k + 1 for k, it in enumerate(pl)}


def load(arm):
    d = {}
    for f in sorted(H.glob(f"{arm}.w*.jsonl")):
        for l in f.open(encoding="utf-8"):
            r = json.loads(l)
            d[r["planted"]["id"]] = r
    return d


one, five = load("claude"), load("claude-standard")
ids = sys.argv[2:] or [i for i in items if one[i]["decision"] != five[i]["decision"]]
for i in ids:
    it = items[i]
    print("=" * 100)
    print(f"{i}  #{num[it['base']]}  kind={it['kind']}  operator={it.get('operator')}  plant={ {k: v for k, v in it.items() if k not in ('code', 'context')} }")
    print(f"--- CLAUDE ALONE: {one[i]['decision']}\n{one[i]['planted']['call']['reply'][:N]}")
    for c in five[i]["planted"]["calls"]:
        print(f"--- {c['agent']}\n{c['reply'][:N]}")
