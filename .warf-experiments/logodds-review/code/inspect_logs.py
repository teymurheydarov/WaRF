import json, sys, collections
for path in sys.argv[1:]:
    print("==", path)
    oracle_types = collections.Counter(); keys = collections.Counter(); vkeys = collections.Counter()
    agents = collections.Counter(); persona_present = 0; nvotes = 0; prov = collections.Counter()
    xs = collections.Counter(); tag = 0; readout_vote = 0
    for line in open(path, encoding="utf-8"):
        if not line.strip(): continue
        s = json.loads(line)
        keys.update(s.keys())
        o = s.get("oracle")
        oracle_types[(o or {}).get("type")] += 1
        if o: xs[o.get("x_star")] += 1
        for v in s.get("votes", []):
            nvotes += 1; vkeys.update(v.keys()); agents[v.get("agent")] += 1
            if v.get("persona"): persona_present += 1
            prov[(v.get("provider"), v.get("model"))] += 1
            if "decision model, no reasoning" in (v.get("reasoning") or ""): tag += 1
    print("session keys", dict(keys)); print("oracle", dict(oracle_types), "x_star", dict(xs))
    print("vote keys", dict(vkeys)); print("votes", nvotes, "with persona", persona_present, "with decision tag", tag)
    print("agents", dict(agents)); print("provider/model", dict(prov))
