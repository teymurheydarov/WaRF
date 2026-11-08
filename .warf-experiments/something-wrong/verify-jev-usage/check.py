"""Independent re-check of the jev-usage audit. Stored data only, pure Python."""
import json, math, random
from pathlib import Path
EXP = Path(__file__).resolve().parents[2]
J = EXP / "jev-five"
def jl(p): return [json.loads(l) for l in open(p, encoding="utf-8")]
sel = jl(EXP / "laya-five/selection.jsonl")
lab = {s["id"]: 1 if s["label"] == "REJECT" else 0 for s in sel}
ids = [s["id"] for s in sel]
def recs(p): return {r["jev"]["id"]: r["jev"] for r in jl(p)}
five, std, one = recs(J/"sessions_five.jsonl"), recs(J/"sessions_standard.jsonl"), recs(J/"sessions_one.jsonl")
rA, rB = recs(J/"verify/refute/rerun_A.jsonl"), recs(J/"verify/refute/rerun_B.jsonl")
SEATS = ["SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY"]
def lg(p):
    p = min(max(p, 0.005), 0.995); return math.log(p/(1-p))
def auc(score, keys=None):
    keys = [k for k in (keys or ids) if k in score]
    pos = [score[k] for k in keys if lab[k]]; neg = [score[k] for k in keys if not lab[k]]
    s = sum((a > b) + 0.5*(a == b) for a in pos for b in neg); return s/(len(pos)*len(neg))
def p_of(r, rnd, seat):
    a = r[rnd].get(seat); return None if a is None else a["p_reject"]
def col(R, rnd, seat, f=lg):
    return {k: f(p_of(R[k], rnd, seat)) for k in ids if k in R and p_of(R[k], rnd, seat) is not None}
def mean(x): return sum(x)/len(x)
def corr(x, y):
    mx, my = mean(x), mean(y); sx = math.sqrt(sum((a-mx)**2 for a in x)); sy = math.sqrt(sum((b-my)**2 for b in y))
    return sum((a-mx)*(b-my) for a, b in zip(x, y))/(sx*sy)
def wl_r(a, b):  # within-label: centre per label, pooled
    ks = [k for k in ids if k in a and k in b]
    xs, ys = [], []
    for L in (0, 1):
        kk = [k for k in ks if lab[k] == L]
        ma, mb = mean([a[k] for k in kk]), mean([b[k] for k in kk])
        xs += [a[k]-ma for k in kk]; ys += [b[k]-mb for k in kk]
    return sum(x*y for x, y in zip(xs, ys))/math.sqrt(sum(x*x for x in xs)*sum(y*y for y in ys)), len(ks)
def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0]*len(v); i = 0
    while i < len(v):
        j = i
        while j+1 < len(v) and v[o[j+1]] == v[o[i]]: j += 1
        for t in range(i, j+1): r[o[t]] = (i+j)/2
        i = j+1
    return r
def spear(x, y): return corr(rank(x), rank(y))
def jacobi(A):
    n = len(A); A = [row[:] for row in A]
    for _ in range(500):
        off = max((abs(A[i][j]), i, j) for i in range(n) for j in range(n) if i < j)
        if off[0] < 1e-12: break
        _, p, q = off
        th = 0.5*math.atan2(2*A[p][q], A[q][q]-A[p][p]); c, s = math.cos(th), math.sin(th)
        for k in range(n):
            akp, akq = A[k][p], A[k][q]; A[k][p] = c*akp - s*akq; A[k][q] = s*akp + c*akq
        for k in range(n):
            apk, aqk = A[p][k], A[q][k]; A[p][k] = c*apk - s*aqk; A[q][k] = s*apk + c*aqk
    return sorted((A[i][i] for i in range(n)), reverse=True)
def ols_resid(y, X):
    n = len(y); Z = [[1.0]+row for row in X]; m = len(Z[0])
    M = [[sum(Z[i][a]*Z[i][b] for i in range(n)) for b in range(m)] for a in range(m)]
    v = [sum(Z[i][a]*y[i] for i in range(n)) for a in range(m)]
    for a in range(m):
        piv = M[a][a]
        for b in range(a+1, m):
            f = M[b][a]/piv
            for c in range(a, m): M[b][c] -= f*M[a][c]
            v[b] -= f*v[a]
    beta = [0]*m
    for a in reversed(range(m)): beta[a] = (v[a]-sum(M[a][c]*beta[c] for c in range(a+1, m)))/M[a][a]
    fit = [sum(beta[a]*Z[i][a] for a in range(m)) for i in range(n)]
    res = [y[i]-fit[i] for i in range(n)]; my = mean(y)
    return res, 1 - sum(r*r for r in res)/sum((t-my)**2 for t in y), beta

print("== A. data/plumbing ==")
for nm, R in (("five", five), ("standard", std), ("one", one), ("rerun_A", rA), ("rerun_B", rB)):
    print(f"  {nm}: n {len(R)}, ids==selection {set(R)==set(ids)}, models {sorted({m for r in R.values() for m in r['models']})}")
ps = [a["p_reject"] for r in five.values() for rnd in ("round1", "round2") for a in r[rnd].values()]
print(f"  five-arm p values {len(ps)}, distinct {len(set(ps))}, on 0.01 grid {all(abs(p*100-round(p*100))<1e-9 for p in ps)}")
conf = [(a["confidence"], a["p_reject"]) for r in five.values() for a in r["round1"].values()]
print(f"  confidence==|1-2p| (0.01): {sum(abs(c-abs(1-2*p))<0.0101 for c,p in conf)} of {len(conf)}")
nor2 = [k for k in ids if not five[k]["round2"]]
print(f"  five-arm reviews without Round 2: {len(nor2)}; later-fixed among them {sum(lab[k] for k in nor2)}")
print(f"  standard: reviews with <5 R1 answers {sum(len(std[k]['round1'])<5 for k in ids)}")

print("== B. AUCs ==")
for s in SEATS:
    r1 = col(five, "round1", s)
    r2 = {k: lg(p_of(five[k], "round2", s) if five[k]["round2"] else p_of(five[k], "round1", s)) for k in ids}
    r2d = col(five, "round2", s); st = col(std, "round1", s)
    rej = sum(five[k]['round1'][s]['choice'] == 'REJECT' for k in ids)
    print(f"  {s:13s} R1 {auc(r1):.3f}  R2(fallback) {auc(r2):.3f}  R2 debated-only {auc(r2d):.3f} (n {len(r2d)})  std R1 {auc(st):.3f} (n {len(st)})  mean p {mean([p_of(five[k],'round1',s) for k in ids]):.2f}  REJ votes {rej}")
for nm, R in (("one", one), ("rerun_A", rA), ("rerun_B", rB)):
    print(f"  {nm} {auc(col(R,'round1','JEV')):.3f}")
ml = {k: mean([lg(p_of(five[k], 'round1', s)) for s in SEATS]) for k in ids}
mp = {k: mean([p_of(five[k], 'round1', s) for s in SEATS]) for k in ids}
print(f"  five mean logit R1 {auc(ml):.3f}, mean p R1 {auc(mp):.3f}")
states = {r["id"]: r for r in jl(J/"verify/refute/states.jsonl")}
added = {k: sum(1 for l in states[k]["code"].splitlines() if l.startswith("+") and not l.startswith("+++")) for k in ids}
print(f"  added lines (from states code) {auc(added):.3f}")
random.seed(1); sims = []
for _ in range(2000):
    sc = {k: random.random() for k in ids}; sims.append(auc(sc))
m = mean(sims); print(f"  null AUC SD (random scores) {math.sqrt(mean([(a-m)**2 for a in sims])):.4f}")

print("== C. state parity ==")
ok = tot = 0
for R in (five, one):
    for k in ids:
        for a in R[k]["round1"].values():
            tot += 1; ok += a["state_chars"] == len(states[k]["state"])
print(f"  state_chars == len(states.jsonl state): {ok} of {tot}; max state len {max(len(v['state']) for v in states.values())}")
same_r1 = sum(len({a['state_chars'] for a in five[k]['round1'].values()}) == 1 for k in ids)
print(f"  five R1 state_chars identical across seats: {same_r1} of 100")

print("== D. correlations / eigen ==")
L = {s: col(five, "round1", s) for s in SEATS}
C = [[wl_r(L[a], L[b])[0] for b in SEATS] for a in SEATS]
for s, row in zip(SEATS, C): print(f"  {s:13s} " + " ".join(f"{v:.3f}" for v in row))
ev = jacobi(C); print("  eigen " + ", ".join(f"{e:.3f}" for e in ev) + f"  first {ev[0]/5*100:.1f}%")
sp = [spear([L[a][k] for k in ids], [L[b][k] for k in ids]) for i, a in enumerate(SEATS) for b in SEATS[i+1:]]
print(f"  Spearman range {min(sp):.3f} to {max(sp):.3f}")
S = {s: col(std, "round1", s) for s in SEATS}
for s in SEATS: print(f"  {s:13s} five vs std same seat wl r {wl_r(L[s], S[s])[0]:.3f} (n {wl_r(L[s], S[s])[1]})")
O, A_, B_ = col(one, "round1", "JEV"), col(rA, "round1", "JEV"), col(rB, "round1", "JEV")
print(f"  one vs A {wl_r(O,A_)[0]:.3f}, one vs B {wl_r(O,B_)[0]:.3f}, A vs B {wl_r(A_,B_)[0]:.3f}")
print(f"  one vs seats: " + ", ".join(f"{s} {wl_r(O, L[s])[0]:.3f}" for s in SEATS))

print("== E. own parts ==")
common = [k for k in ids if all(k in S[s] for s in SEATS)]
for s in SEATS:
    others = [t for t in SEATS if t != s]
    def own(D, keys):
        y = [D[s][k] for k in keys]; x = [[mean([D[t][k] for t in others])] for k in keys]
        res, r2, beta = ols_resid(y, x); return dict(zip(keys, res)), r2, beta[1]
    o5, r2, b = own(L, ids); o5c, _, _ = own(L, common); osc, _, _ = own(S, common)
    print(f"  {s:13s} R2 {r2:.3f} slope {b:.2f} own AUC five {auc(o5):.3f}, std(n{len(common)}) {auc(osc):.3f}, five vs std own r {corr([o5c[k] for k in common],[osc[k] for k in common]):.3f}; Spearman own vs log added {spear([o5[k] for k in ids],[math.log1p(added[k]) for k in ids]):.2f}")
oneres, r2, _ = ols_resid([O[k] for k in ids], [[(A_[k]+B_[k])/2] for k in ids])
print(f"  one on mean(A,B): R2 {r2:.3f}, residual AUC {auc(dict(zip(ids, oneres))):.3f}")

print("== F. paired bootstrap ADVOCATE-SKEPTIC ==")
pos = [k for k in ids if lab[k]]; neg = [k for k in ids if not lab[k]]; random.seed(7); d = []
for _ in range(2000):
    kk = [random.choice(pos) for _ in pos] + [random.choice(neg) for _ in neg]
    sc = lambda D: (lambda P, N: sum((a > b) + 0.5*(a == b) for a in P for b in N)/(len(P)*len(N)))(
        [D[k] for k in kk if lab[k]], [D[k] for k in kk if not lab[k]])
    d.append(sc(L["ADVOCATE"]) - sc(L["SKEPTIC"]))
d.sort(); print(f"  {auc(L['ADVOCATE'])-auc(L['SKEPTIC']):+.3f} [{d[50]:+.3f}, {d[1949]:+.3f}]")

print("== G. controls ==")
ctl = jl(J/"controls_five.jsonl")
for plant in ("BUG comment", "null dereference"):
    rows = [r["jev"] for r in ctl if r["jev"]["plant"] == plant]
    for s in SEATS:
        b = [lg(p_of(five[r["id"]], "round1", s)) for r in rows]; a = [lg(r["round1"][s]["p_reject"]) for r in rows]
        ceil = sum(r["round1"][s]["p_reject"] >= 0.99 for r in rows)
        print(f"  {plant:16s} {s:13s} n {len(rows)} {mean(b):+.2f} -> {mean(a):+.2f} rise {mean(a)-mean(b):+.2f}  at p>=0.99 after {ceil}")
