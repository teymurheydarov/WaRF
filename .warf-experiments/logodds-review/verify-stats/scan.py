import json, glob, collections
for f in [".warf/sessions.jsonl"] + glob.glob(".warf-experiments/*/sessions.jsonl") + glob.glob(".warf-experiments/*/*/sessions.jsonl"):
    keys = collections.defaultdict(set); n = 0
    try:
        lines = open(f, encoding="utf-8").read().splitlines()
    except OSError: continue
    for l in lines:
        try: s = json.loads(l)
        except Exception: continue
        o = s.get("oracle") or {}
        if o.get("type") != "DEVELOPER": continue
        n += 1
        for v in s.get("votes", []):
            if v.get("persona"):
                keys[(v.get("agent"), v.get("persona"))].add((v.get("provider"), v.get("model"), s.get("profile")))
    mixed = {k: m for k, m in keys.items() if len({(p, mo) for p, mo, _ in m}) > 1}
    print(f, "labelled", n, "keys", len(keys), "mixed-model keys", len(mixed), list(mixed.items())[:2])
