"""Completeness-critic checks on stored data only (no model calls).
Inputs: verify-labels-metrics/v1_data.json + feats.json (per-item scores and labeller-rule features),
jev-five/verify/refute/states.jsonl (the exact Jev states), jev-five/sessions_one.jsonl, selection.jsonl."""
import json, math, random
from pathlib import Path
EXP = Path(__file__).resolve().parents[2]
SW = EXP / "something-wrong"
d = json.loads((SW / "verify-labels-metrics/v1_data.json").read_text(encoding="utf-8"))
feats = json.loads((SW / "verify-labels-metrics/feats.json").read_text(encoding="utf-8"))
ids, y = d["ids"], d["y"]
y = [1 if (v is True or v == 1 or v == "REJECT") else 0 for v in y]
S = d["sel"] if "sel" in d else None
sc = d["scores"]
sel = [json.loads(l) for l in (EXP / "laya-five/selection.jsonl").open(encoding="utf-8")]
assert [s["id"] for s in sel] == ids
assert y == [1 if s["label"] == "REJECT" else 0 for s in sel]
assert sc["Claude"] == [s["p_claude"] for s in sel]
states = {r["id"]: r for r in map(json.loads, (EXP / "jev-five/verify/refute/states.jsonl").open(encoding="utf-8"))}
one = {r["jev"]["id"]: r for r in map(json.loads, (EXP / "jev-five/sessions_one.jsonl").open(encoding="utf-8"))}
assert sc["Jev one"] == [one[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids]

def auc(s, yy):
    P = [a for a, t in zip(s, yy) if t]; N = [a for a, t in zip(s, yy) if not t]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))

def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]: j += 1
        for k in range(i, j + 1): r[o[k]] = (i + j) / 2
        i = j + 1
    return r

def pear(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb) if sa and sb else float("nan")

def spear_within(a, b):
    out = []
    for lab in (1, 0):
        idx = [i for i in range(len(y)) if y[i] == lab]
        out.append(pear(rank([a[i] for i in idx]), rank([b[i] for i in idx])))
    return out

F = {k: [feats[i][k] for i in ids] for k in ("added", "removed", "added_noncosmetic")}
jev, cl = sc["Jev one"], sc["Claude"]
j5 = sc["Jev five R1 mean"]
# context lines in the exact Jev state
ctx, chg = [], []
for i in ids:
    code = states[i]["code"].split("\n")
    body = [l for l in code if not l.startswith(("diff --git", "index ", "--- ", "+++ ", "@@", "new file", "deleted file", "similarity", "rename ", "old mode", "new mode"))]
    ctx.append(sum(1 for l in body if l.startswith(" ")))
    chg.append(sum(1 for l in body if l.startswith(("+", "-"))))
frac = [c / (c + x) if c + x else 0 for c, x in zip(chg, ctx)]
pairs = [(2 * k, 2 * k + 1) for k in range(50)]
for a, b in pairs: assert y[a] == 1 and y[b] == 0

print("== C1 paired bootstrap over the 50 pairs (2000 draws, seed 7) ==")
def boot(sa, sb, B=2000):
    rng = random.Random(7); diffs = []
    for _ in range(B):
        pk = [pairs[rng.randrange(50)] for _ in range(50)]
        idx = [i for p in pk for i in p]; yy = [y[i] for i in idx]
        diffs.append(auc([sa[i] for i in idx], yy) - auc([sb[i] for i in idx], yy))
    diffs.sort(); return diffs[int(0.025 * B)], diffs[int(0.975 * B) - 1], sum(x > 0 for x in diffs) / B
nc = F["added_noncosmetic"]; ad = F["added"]
for name, a, b in [("Jev one - added lines", jev, ad), ("Jev one - noncosmetic added", jev, nc),
                   ("Jev five R1 - added lines", j5, ad), ("Claude - added lines", cl, ad),
                   ("Claude - noncosmetic added", cl, nc), ("Claude - Jev one", cl, jev), ("Claude - Jev five R1", cl, j5)]:
    lo, hi, pp = boot(a, b)
    print(f"  {name:<28} {auc(a, y) - auc(b, y):+.3f} [{lo:+.3f}, {hi:+.3f}]  P(>0) {pp:.3f}")

print("\n== C2 conditional logistic on pair differences (no intercept); LR test of adding the reviewer ==")
def logit(p): p = min(max(p, 0.005), 0.995); return math.log(p / (1 - p))
def fit(X):  # X: list of rows of pair differences, outcome always 1 (REJECT member first)
    k = len(X[0]); w = [0.0] * k
    for _ in range(100):
        g = [0.0] * k; H = [[0.0] * k for _ in range(k)]; ll = 0.0
        for r in X:
            z = sum(wi * xi for wi, xi in zip(w, r)); p = 1 / (1 + math.exp(-z)); ll += math.log(max(p, 1e-300))
            for a in range(k):
                g[a] += (1 - p) * r[a]
                for b in range(k): H[a][b] -= p * (1 - p) * r[a] * r[b]
        # solve H dw = -g (k <= 3) by Gauss
        M = [H[a][:] + [-g[a]] for a in range(k)]
        for c in range(k):
            piv = max(range(c, k), key=lambda r_: abs(M[r_][c])); M[c], M[piv] = M[piv], M[c]
            for r_ in range(k):
                if r_ != c:
                    f = M[r_][c] / M[c][c]; M[r_] = [u - f * v for u, v in zip(M[r_], M[c])]
        dw = [M[a][k] / M[a][a] for a in range(k)]
        w = [wi + di for wi, di in zip(w, dw)]
        if max(abs(x) for x in dw) < 1e-10: break
    ll = sum(math.log(max(1 / (1 + math.exp(-sum(wi * xi for wi, xi in zip(w, r)))), 1e-300)) for r in X)
    return w, ll
def pdiff(f): return [f(a) - f(b) for a, b in pairs]
lnc = [math.log1p(v) for v in nc]; lad = [math.log1p(v) for v in ad]
for basename, base in [("log1p added", lad), ("log1p noncosmetic added", lnc)]:
    bd = pdiff(lambda i: base[i])
    w0, ll0 = fit([[x] for x in bd])
    for rname, rv in [("Claude", cl), ("Jev one", jev), ("Jev five R1", j5)]:
        rd = pdiff(lambda i: logit(rv[i]))
        w1, ll1 = fit([[x, z] for x, z in zip(bd, rd)])
        lr = 2 * (ll1 - ll0); p = math.erfc(math.sqrt(max(lr, 0) / 2))
        print(f"  {rname:<12} after {basename:<24} coef {w1[1]:+.3f}  LR {lr:6.2f}  p {p:.4f}")

print("\n== C3 within-label Spearman (REJECT, APPROVE) of the score with change features ==")
for fname, fv in [("log removed", [math.log1p(v) for v in F["removed"]]), ("log added", lad),
                  ("log noncosmetic added", lnc), ("context lines", ctx), ("changed fraction", frac)]:
    for rname, rv in [("Jev one", jev), ("Claude", cl)]:
        a, b = spear_within(rv, fv)
        print(f"  {fname:<22} {rname:<8} R {a:+.2f}  A {b:+.2f}")

print("\n== C4 AUC by how buried the change is (pairs split at the median of the pair's mean changed fraction) ==")
pm = sorted(range(50), key=lambda k: (frac[pairs[k][0]] + frac[pairs[k][1]]) / 2)
for nm, ks in [("change buried (low fraction)", pm[:25]), ("change dominant (high fraction)", pm[25:])]:
    idx = [i for k in ks for i in pairs[k]]; yy = [y[i] for i in idx]
    print(f"  {nm:<32} Jev {auc([jev[i] for i in idx], yy):.3f}  Claude {auc([cl[i] for i in idx], yy):.3f}  "
          f"noncosm-added {auc([nc[i] for i in idx], yy):.3f}  median ctx lines {sorted(ctx[i] for i in idx)[len(idx)//2]}")

print("\n== C5 domain header and Jev one p distribution ==")
from collections import Counter
print("  domains:", Counter(s["domain"] for s in sel))
print("  Jev one: distinct", len(set(jev)), " p>=0.95:", sum(p >= 0.95 for p in jev), " p<=0.05:", sum(p <= 0.05 for p in jev),
      " most common:", Counter(jev).most_common(3))

print("\n== C6 within-APPROVE Spearman with noncosmetic added, only items with >= 1 blameable added line ==")
idx = [i for i in range(100) if y[i] == 0 and nc[i] >= 1]
for rname, rv in [("Jev one", jev), ("Claude", cl)]:
    print(f"  {rname:<8} n {len(idx)}  rho {pear(rank([rv[i] for i in idx]), rank([lnc[i] for i in idx])):+.2f}")
idx = [i for i in range(100) if y[i] == 1]
print(f"  (REJECT, all have >=1: n {len(idx)}, min nc {min(nc[i] for i in idx)})")

print("\n== C7 does the Jev-Claude gap widen when the change is buried? bootstrap of (gap_low - gap_high) ==")
lowk, highk = pm[:25], pm[25:]
def gap(ks, rng=None):
    idx = [i for k in ks for i in pairs[k]]; yy = [y[i] for i in idx]
    return auc([cl[i] for i in idx], yy) - auc([jev[i] for i in idx], yy)
obs = gap(lowk) - gap(highk); rng = random.Random(3); bs = []
for _ in range(2000):
    a = [lowk[rng.randrange(25)] for _ in range(25)]; b = [highk[rng.randrange(25)] for _ in range(25)]
    bs.append(gap(a) - gap(b))
bs.sort(); print(f"  gap low {gap(lowk):+.3f}, gap high {gap(highk):+.3f}, difference {obs:+.3f} [{bs[50]:+.3f}, {bs[1949]:+.3f}]")
newf = [k for k in range(50) if all(states[ids[i]]["code"].count("\nnew file mode") or states[ids[i]]["code"].startswith("new file") for i in pairs[k])]
print("  pairs where both are new files:", len(newf))
lowj = [k for k in range(50) if ctx[pairs[k][0]] <= 6 and ctx[pairs[k][1]] <= 6]
