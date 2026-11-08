import json, re, glob, collections
pat = re.compile(r"p\(APPROVE\)=([0-9.]+)\s+p\(REJECT\)=([0-9.]+)")
stats = collections.Counter(); examples=[]
def walk(o, vote=None):
    if isinstance(o, dict):
        v = o.get("vote", vote)
        for k, x in o.items(): yield from walk(x, v)
    elif isinstance(o, list):
        for x in o: yield from walk(x, vote)
    elif isinstance(o, str) and "decision model, no reasoning" in o:
        yield o, vote
seen=set()
for f in glob.glob("C:/workdir/warf/WaRF/.warf-experiments/**/*.jsonl", recursive=True):
    try: lines = open(f, encoding="utf-8").read().splitlines()
    except Exception: continue
    for ln in lines:
        try: o = json.loads(ln)
        except Exception: continue
        for s, vote in walk(o):
            m = pat.search(s)
            if not m: stats["noparse"] += 1; continue
            pa, pr = float(m.group(1)), float(m.group(2))
            stats["n"] += 1
            if pa == 0 and pr == 0: stats["both_zero"] += 1
            if pr <= 0.01 or pr >= 0.99: stats["at_clamp"] += 1
            if abs(pa+pr-1) > 0.011: stats["sum_not_1"] += 1
            if vote in (1,-1):
                stats["with_vote"] += 1
                if (vote == -1) != (pr > 0.5) and pr != 0.5:
                    stats["vote_vs_p_mismatch"] += 1
                    if len(examples)<5: examples.append((f.split("experiments")[1], vote, pr))
                if pr == 0.5: stats["p_half"] += 1
print(dict(stats)); print(*examples, sep="\n")
