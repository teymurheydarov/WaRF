import json
from load import *
J = {}
for l in (HERE/"judgements.jsonl").open(encoding="utf-8"):
    j = json.loads(l); J.setdefault(j["base"], []).append(j)
D = [it["id"] for it in items if it["kind"]=="defective"]
ms = [i for i in D if not rej("claude-strict", i)]; mw = [i for i in D if not rej("claude-standard", i)]
print("strict missed", len(ms), "W1 missed", len(mw), "both", len(set(ms)&set(mw)))
for i in sorted(set(ms)|set(mw), key=lambda i: by_id[i]["date"]):
    it = by_id[i]
    print(f"\n### {i} {it['date']} vis={it.get('visible')} strictMiss={i in ms} W1Miss={i in mw} claude={rej('claude',i)} adv={rej('claude-advocate',i)} jev={rej('jev',i)} fix='{it['fix_subject']}'")
    print("  DEFECT:", it["defect"][0][:300])
    print("  judges vis:", [j["visible"] for j in J.get(it["base"], [])])
    print("  STRICT:", reply("claude-strict", i)[:700].replace("\n"," "))
    print("  W1 votes:", [(v["agent"], v["label"]) for v in recs["claude-standard"][i]["votes"]], recs["claude-standard"][i].get("sprt_fired"))
