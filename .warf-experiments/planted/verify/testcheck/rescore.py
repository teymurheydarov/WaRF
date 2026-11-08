import json, random
from pathlib import Path
OUT = Path(__file__).resolve().parent; H = OUT.parents[1]
items = [json.loads(l) for l in (H/"items.jsonl").open(encoding="utf-8")]
R = json.loads((OUT/"replay.json").read_text(encoding="utf-8"))
pl = [i for i in items if i["kind"]=="planted"]
num = {it["base"]: k+1 for k, it in enumerate(pl)}
bases = sorted(it["base"] for it in pl)
HARMLESS = {15,18,22,31,33}
NOCOMPILE = {17,32,35,47,54}
DEAD = {46,50}
ORIG_DEFECT = {5,7,26,31,36,39,52,53}   # clean original has a verified defect that Claude named
arms = {"claude": lambda i: R[i]["claude"]=="REJECT", "cal": lambda i: R[i]["cal"]["decision"]=="REJECT",
        "cold": lambda i: R[i]["cold"]["decision"]=="REJECT"}
def ba(arm, bs):
    f = arms[arm]
    return (sum(f(b+":planted") for b in bs)/len(bs) + sum(not f(b+":clean") for b in bs)/len(bs))/2
def run(name, bs):
    rng = random.Random(4); boots = [[rng.choice(bs) for _ in bs] for _ in range(2000)]
    row = [f"{name:<58} n={len(bs):2d}"]
    for a in arms: row.append(f"{a} {ba(a,bs):.3f}")
    for a in ("cal","cold"):
        d = ba(a,bs)-ba("claude",bs); xs = sorted(ba(a,s)-ba("claude",s) for s in boots)
        row.append(f"{a}-claude {d:+.3f} [{xs[49]:+.3f},{xs[1949]:+.3f}]")
    print("  ".join(row))
run("S0 as scored", bases)
run("S1 drop harmless plants", [b for b in bases if num[b] not in HARMLESS])
run("S2 drop non-compiling plants", [b for b in bases if num[b] not in NOCOMPILE])
run("S3 drop originals with verified defect", [b for b in bases if num[b] not in ORIG_DEFECT])
run("S4 drop harmless+noncompile+dead plants", [b for b in bases if num[b] not in HARMLESS|NOCOMPILE|DEAD])
run("S5 = S4 and drop verified-defect originals", [b for b in bases if num[b] not in HARMLESS|NOCOMPILE|DEAD|ORIG_DEFECT])
# relabel: clean original with verified defect counts as defective (REJECT right)
def ba_relabel(arm, bs):
    f = arms[arm]; P=[]; N=[]
    for b in bs:
        P.append(f(b+":planted"))
        (P if num[b] in ORIG_DEFECT else N).append(f(b+":clean") if num[b] in ORIG_DEFECT else not f(b+":clean"))
    return (sum(P)/len(P)+sum(N)/len(N))/2
print("S6 relabel verified-defect originals as defective:", {a: round(ba_relabel(a,bases),3) for a in arms})
# summary counts
for a in arms:
    f = arms[a]
    print(a, "caught", sum(f(b+":planted") for b in bases), "passed", sum(not f(b+":clean") for b in bases))
