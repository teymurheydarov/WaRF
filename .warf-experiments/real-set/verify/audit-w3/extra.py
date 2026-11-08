import json, random
from pathlib import Path
SET = Path(__file__).resolve().parents[2]
ci = [json.loads(l) for l in (SET / "commit_inputs.jsonl").open(encoding="utf-8")]
s = sorted(len(r["code"]) for r in ci); print("median input chars", s[len(s)//2], (s[65]+s[66])/2, "max", s[-1])
items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
defect = {it["id"]: it["kind"] == "defective" for it in items}; ids = [it["id"] for it in items]
pure = json.load((Path(__file__).parent / "w3_pure.json").open())
def rej(a):
    out = {}
    for p in SET.glob(f"{a}.w*.jsonl"):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); out[r["planted"]["id"]] = r["decision"] == "REJECT"
    return out
R = {"adv": rej("claude-advocate"), "w3": {i: pure[i]["decision"] == "REJECT" for i in ids}}
def ba(a, s):
    P = [i for i in s if defect[i]]; N = [i for i in s if not defect[i]]
    return (sum(R[a][i] for i in P)/len(P) + sum(not R[a][i] for i in N)/len(N)) / 2
br = random.Random(4); Pi = [i for i in ids if defect[i]]; Ni = [i for i in ids if not defect[i]]
boots = [[br.choice(Pi) for _ in Pi] + [br.choice(Ni) for _ in Ni] for _ in range(2000)]
xs = sorted(ba("w3", b) - ba("adv", b) for b in boots); print("W3-ADVOCATE xs[49]", xs[49], "xs[50]", xs[50], "share <=0", sum(x <= 0 for x in xs)/2000)
