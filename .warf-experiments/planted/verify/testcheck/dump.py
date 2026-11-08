import json, glob, sys
from pathlib import Path
H = Path(__file__).resolve().parents[2]
items = [json.loads(l) for l in (H/"items.jsonl").open(encoding="utf-8")]
recs = {}
for seat in ("claude","jev","laya"):
    recs[seat] = {}
    for p in sorted(H.glob(f"{seat}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); recs[seat][r["planted"]["id"]] = r
def pr(seat, i):
    b = recs[seat][i]["planted"]["call"]["body"]["answers"]["verdict"]["probabilities"]["REJECT"]
    return b
mode = sys.argv[1]
n = 0
for it in items:
    if it["kind"] != "planted": continue
    n += 1
    i = it["id"]; c = i.replace(":planted", ":clean")
    cd = lambda x: recs["claude"][x]["decision"][0]
    print(f"### {n} {it['base']} op={it['operator']} domain={it['domain']}  Claude clean/planted={cd(c)}/{cd(i)}  Jev pR clean/planted={pr('jev',c):.2f}/{pr('jev',i):.2f}  Laya {pr('laya',c):.2f}/{pr('laya',i):.2f}")
    print("  ORIG:", it["original"].strip())
    print("  MUT :", it["mutated"].strip())
    if mode == "full":
        patch = it["code"].split("\n\n" + "─"*60)[0]
        # print hunk lines around mutated
        L = patch.splitlines()
        k = [j for j, x in enumerate(L) if x == it["mutated"]][0]
        for x in L[max(0,k-int(sys.argv[2])):k+int(sys.argv[3])]:
            print("    |", x)
