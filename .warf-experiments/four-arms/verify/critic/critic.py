"""Critic checks on four-arms and the two verifier reports. Pure Python, reads only stored data."""
import json, re, random
from pathlib import Path
FA = Path(__file__).resolve().parents[2]; EXP = FA.parent
sel = [json.loads(l) for l in (EXP / "laya-five/selection.jsonl").open(encoding="utf-8")]
lab = {s["id"]: s["label"] == "REJECT" for s in sel}
pc = {s["id"]: s.get("p_claude") for s in sel}
t18 = set(json.loads((EXP / "something-wrong/verify-labels-metrics/v2_data.json").read_text(encoding="utf-8"))["t18"])
recs = {}
for arm in ("claude-one", "claude-standard", "jev-one", "jev-standard"):
    recs[arm] = {}
    for p in sorted(FA.glob(f"{arm}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); recs[arm][r["four"]["id"]] = r
rej = {a: {i: r["decision"] == "REJECT" for i, r in d.items()} for a, d in recs.items()}
ids = [s["id"] for s in sel]
P = [i for i in ids if lab[i]]; N = [i for i in ids if not lab[i]]
print("== 1. independent BA / counts")
for a in rej:
    tpr = sum(rej[a][i] for i in P) / 50; tnr = sum(not rej[a][i] for i in N) / 50
    print(f"  {a:<16} BA {(tpr+tnr)/2:.3f}  TPR {tpr:.2f}  FPR {1-tnr:.2f}  REJECT {sum(rej[a].values())}")
# paired agreement claude-one vs jev-one, McNemar-style exact on correctness
c1 = {i: rej["claude-one"][i] == lab[i] for i in ids}; j1 = {i: rej["jev-one"][i] == lab[i] for i in ids}
b = sum(c1[i] and not j1[i] for i in ids); c = sum(j1[i] and not c1[i] for i in ids)
from math import comb
pv = min(1, 2 * sum(comb(b + c, k) for k in range(0, min(b, c) + 1)) / 2 ** (b + c))
print(f"  claude-one vs jev-one: verdicts agree {sum(rej['claude-one'][i]==rej['jev-one'][i] for i in ids)}/100; "
      f"only-Claude-right {b}, only-Jev-right {c}, exact McNemar p {pv:.2f}")
# minimal detectable difference: SE of BA difference from bootstrap
rng = random.Random(11)
def ba(a, s): 
    Ps=[i for i in s if lab[i]]; Ns=[i for i in s if not lab[i]]
    return (sum(rej[a][i] for i in Ps)/len(Ps) + sum(not rej[a][i] for i in Ns)/len(Ns))/2
ds = []
for _ in range(2000):
    s = [rng.choice(P) for _ in P] + [rng.choice(N) for _ in N]
    ds.append(ba("claude-one", s) - ba("jev-one", s))
m = sum(ds)/len(ds); sd = (sum((x-m)**2 for x in ds)/len(ds))**.5
print(f"  SD of BA difference claude-one - jev-one: {sd:.3f}  -> 80% power at alpha .05 needs |diff| >~ {2.8*sd:.2f}")

print("== 2. equal-count comparison old p_claude top-47 vs new claude-one REJECTs (verifier 2 says 72/100)")
order = sorted(ids, key=lambda i: -pc[i]); top = set(order[:47])
thr = pc[order[46]]; ties = sum(pc[i] == thr for i in ids)
agree = sum((i in top) == rej["claude-one"][i] for i in ids)
print(f"  threshold p {thr}, {ties} changes tied at it (top-47 cut is tie-dependent); agree {agree}/100")
for g, s in (("later fixed", P), ("t18", [i for i in N if i in t18]), ("other never", [i for i in N if i not in t18])):
    print(f"   {g:<12} old top-47 {sum(i in top for i in s)}  new {sum(rej['claude-one'][i] for i in s)}")

print("== 3. circularity of the hand classification (visible.py bins, classified after reading Claude's replies)")
src = (FA / "verify/explain/visible.py").read_text(encoding="utf-8")
C = {}
for k, v in re.findall(r'"([^"]+)":\s*\n?\s*"([0-9a-f ]+)"\.split\(\)', src): C[k] = v.split()
V = C["visible defect, fix addresses it"] + C["visible doc slip, fix addresses it"]
ARG = C["arguable"]; NV = C["real defect, not visible in this diff"]; ND = [i for k, v in C.items() if k.startswith("no defect") for i in v]
Aoth = [i for i in N if i not in t18]
for a in rej:
    pos = V + ARG; neg = NV + ND
    agree = sum(rej[a][i] for i in pos) + sum(not rej[a][i] for i in neg)
    print(f"  {a:<16} verdict matches bin (V+arguable=REJECT, rest=APPROVE) on {agree}/50;"
          f" REJECT rate: V {sum(rej[a][i] for i in V)}/{len(V)}, ND {sum(rej[a][i] for i in ND)}/{len(ND)}, never-fixed other {sum(rej[a][i] for i in Aoth)}/{len(Aoth)}")
print("  ND later-fixed should behave like never-fixed if the bins were blind; Claude ND vs never-fixed REJECT rate differ, Jev's do not.")
both = [i for i in V if rej["jev-one"][i] and rej["claude-one"][i]]
print(f"  V caught by both one-agent arms {len(both)}/{len(V)}; jev-only {[i for i in V if rej['jev-one'][i] and not rej['claude-one'][i]]}; claude-only {[i for i in V if rej['claude-one'][i] and not rej['jev-one'][i]]}")
print(f"  ND rejected by Jev, approved by Claude: {[i for i in ND if rej['jev-one'][i] and not rej['claude-one'][i]]}")

print("== 4. ceiling of a perfect diff-only reviewer on these labels")
slips = ["ad25c5", "99e575", "4cc013", "299349", "556f50"]
for name, tp, fp in (("rejects V only", len(V), 0), ("V+arguable", len(V)+len(ARG), 0),
                     ("V, also flags 5 unfixed slips", len(V), 5), ("V+arg, also 5 slips", len(V)+len(ARG), 5)):
    print(f"  {name:<30} BA {(tp/50 + (50-fp)/50)/2:.3f}")

print("== 5. panel vs own one agent on the visible set")
for m, one, std in (("Claude", "claude-one", "claude-standard"), ("Jev", "jev-one", "jev-standard")):
    print(f"  {m}: one agent rejects {sum(rej[one][i] for i in V)}/17, panel {sum(rej[std][i] for i in V)}/17; "
          f"never-fixed REJECT one {sum(rej[one][i] for i in N)}/50 panel {sum(rej[std][i] for i in N)}/50")

print("== 6. Claude replies mentioning tools / files / environment")
pat = re.compile(r"tool|\bgrep\b|\bls\b|read the file|I (?:ran|checked|looked at|opened|searched)|working directory|git (?:log|show)|repository history|later commit", re.I)
hits = 0
for a in ("claude-one", "claude-standard"):
    for i, r in recs[a].items():
        for call in r["four"]["calls"]:
            t = call.get("reply", "")
            for mm in pat.finditer(t):
                hits += 1
                if hits <= 25:
                    print(f"  {a} {i} {call['agent']}: ...{t[max(0,mm.start()-80):mm.end()+80].replace(chr(10),' ')}...")
print(f"  total matches {hits}")
