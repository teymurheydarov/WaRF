import json, collections
c = collections.defaultdict(set); lab = collections.Counter()
for ln in open("C:/workdir/warf/WaRF/.warf/sessions.jsonl", encoding="utf-8"):
    try: s = json.loads(ln)
    except Exception: continue
    o = s.get("oracle") or {}
    if o.get("type") != "DEVELOPER": continue
    for v in s.get("votes", []):
        key = (v.get("agent"), v.get("persona"))
        c[key].add((s.get("profile"), v.get("provider"), v.get("model")))
        lab[key] += 1
for k, vals in c.items():
    provs = {(p, m) for _, p, m in vals}
    if len(provs) > 1:
        print(k, lab[k], sorted(map(str, vals))[:6])
print("keys", len(c))
