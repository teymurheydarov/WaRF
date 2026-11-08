"""Critic checks on the second preregistration (W3). Pure Python, reads only; no warf import.
    python -B verify/critic3/critic.py   (from real-set/)"""
import itertools, json, math, random, re
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
items = [json.loads(l) for l in (HERE / "items.jsonl").open(encoding="utf-8")]
by = {i["id"]: i for i in items}
ids = [i["id"] for i in items]
D = {i: by[i]["kind"] == "defective" for i in ids}
cin = {json.loads(l)["id"]: json.loads(l) for l in (HERE / "commit_inputs.jsonl").open(encoding="utf-8")}

def load(arm):
    out = {}
    for p in sorted(HERE.glob(f"{arm}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); out[r["planted"]["id"]] = r
    return out

ARMS = ["claude", "claude-strict", "claude-advocate", "claude-commit", "claude-commit-strict"]
R = {a: load(a) for a in ARMS}
rej = {a: {i: R[a][i]["decision"] == "REJECT" for i in ids} for a in ARMS}
std = load("claude-standard")
for persona in ("ADVOCATE", "SKEPTIC"):
    rej["W1." + persona] = {}
    for i in ids:
        v = [x for x in std[i]["votes"] if x["agent"] == persona]
        rej["W1." + persona][i] = (v[0]["label"] == "REJECT") if v else None
w3 = json.load(open(HERE / "verify/what-drives-w3/replay_w3.json", encoding="utf-8"))

def ba(r, s=ids):
    P = [i for i in s if D[i]]; N = [i for i in s if not D[i]]
    return (sum(r[i] for i in P) / len(P) + sum(not r[i] for i in N) / len(N)) / 2

def mc(a, b, s=ids):
    k1 = sum(a[i] == D[i] and b[i] != D[i] for i in s); k2 = sum(b[i] == D[i] and a[i] != D[i] for i in s)
    n = k1 + k2
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k1, k2) + 1)) / 2 ** n)
    return k1, k2, p

OR = lambda a, b: {i: rej[a][i] or rej[b][i] for i in ids}
AND = lambda a, b: {i: rej[a][i] and rej[b][i] for i in ids}
print("W3 replay keys sample:", list(w3)[:1] if isinstance(w3, dict) else type(w3))

print("\n== single arms ==")
for a in rej:
    if None in rej[a].values():
        print(a, "missing on", sum(v is None for v in rej[a].values())); continue
    print(f"  {a:<22} BA {ba(rej[a]):.3f}")

print("\n== OR / AND of every pair (BA; vs commit-strict only-rule/only-cs, p) ==")
pool = [a for a in rej if None not in rej[a].values()]
rows = []
for a, b in itertools.combinations(pool, 2):
    o = {i: rej[a][i] or rej[b][i] for i in ids}; n = {i: rej[a][i] and rej[b][i] for i in ids}
    agree = sum(rej[a][i] == rej[b][i] for i in ids)
    rows.append((ba(o), a, b, ba(n), agree, mc(o, rej["claude-commit-strict"])))
for r in sorted(rows, reverse=True):
    print(f"  OR {r[1]:>20} + {r[2]:<20} {r[0]:.3f}  AND {r[3]:.3f}  agree {r[4]}/132  vs cs {r[5][0]}/{r[5][1]} p {r[5][2]:.3f}")

# W3 = OR(strict, commit-strict) gain split by whether the commit had other files
o = OR("claude-strict", "claude-commit-strict")
print("\n== OR(strict, commit-strict) vs each seat, by other_files ==")
for lab, s in (("no other files", [i for i in ids if cin[i]["other_files"] == 0]),
               ("other files", [i for i in ids if cin[i]["other_files"] > 0])):
    nd = sum(D[i] for i in s)
    print(f"  {lab}: {len(s)} items ({nd} defective)")
    for seat in ("claude-strict", "claude-commit-strict"):
        print(f"    vs {seat}: only OR / only seat {mc(o, rej[seat], s)[:2]}")
    print(f"    seats disagree on {sum(rej['claude-strict'][i] != rej['claude-commit-strict'][i] for i in s)}")

# trivial size rules
def added(code):
    return sum(1 for l in code.splitlines() if l.startswith("+") and not l.startswith("+++"))
sz = {i: added(by[i]["code"]) for i in ids}
csz = {i: len(cin[i]["code"]) for i in ids}
def auc(x):
    P = [x[i] for i in ids if D[i]]; N = [x[i] for i in ids if not D[i]]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))
print(f"\n== size ==  AUC added lines {auc(sz):.3f}; AUC commit-input chars {auc(csz):.3f}; AUC other_files chars {auc({i: cin[i]['other_files'] for i in ids}):.3f}")
rng = random.Random(7); fold = {}
for cls in (True, False):
    m = [i for i in ids if D[i] == cls]; rng.shuffle(m)
    for k, i in enumerate(m): fold[i] = k % 5
for name, x in (("added lines", sz), ("commit chars", csz)):
    best_in = max((ba({i: x[i] >= t for i in ids}), t) for t in sorted(set(x.values())))
    pred = {}
    for k in range(5):
        tr = [i for i in ids if fold[i] != k]
        t = max((ba({i: x[i] >= t for i in ids}, tr), t) for t in sorted(set(x[i] for i in tr)))[1]
        for i in ids:
            if fold[i] == k: pred[i] = x[i] >= t
    print(f"  threshold on {name}: in-sample best BA {best_in[0]:.3f} (t={best_in[1]}), out-of-fold BA {ba(pred):.3f}")
# W3 by size tercile of added lines among defects vs clean
print("\n== discordant items W3(OR) vs commit-strict, with added lines / other_files ==")
for i in ids:
    if o[i] != rej["claude-commit-strict"][i] or o[i] != rej["claude-strict"][i]:
        print(f"  {i:<50} def={D[i]!s:<5} strict={rej['claude-strict'][i]!s:<5} cs={rej['claude-commit-strict'][i]!s:<5} added={sz[i]} other={cin[i]['other_files']}")
# timing: when were the claude-strict records written vs README
ts = sorted(R["claude-strict"][i]["created_at"] for i in ids)
tc = sorted(R["claude-commit-strict"][i]["created_at"] for i in ids)
print(f"\n== timing == claude-strict records {ts[0]} .. {ts[-1]}; commit-strict {tc[0]} .. {tc[-1]}")
