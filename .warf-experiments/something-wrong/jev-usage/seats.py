"""How alike are the five Jev seats, and is any seat's difference from the others reproducible?
Stored p values only (../../jev-five/), no model is asked. Pure Python (numpy BLAS crashes here).

    python -B .warf-experiments/something-wrong/jev-usage/seats.py > .../seats.log
"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
JEV = EXP / "jev-five"
LAYA = EXP / "laya-five"
SEATS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")


def jl(p):
    return [json.loads(line) for line in p.open(encoding="utf-8")]


sel = jl(LAYA / "selection.jsonl")
ids = [s["id"] for s in sel]
y = {s["id"]: s["label"] == "REJECT" for s in sel}        # REJECT = later fixed
feat = {r["id"]: r for r in jl(JEV / "verify" / "refute" / "features.jsonl")}


def by_id(path):
    return {r["jev"]["id"]: r["jev"] for r in jl(path)}


five = by_id(JEV / "sessions_five.jsonl")
std = by_id(JEV / "sessions_standard.jsonl")
one = by_id(JEV / "sessions_one.jsonl")
rA = by_id(JEV / "verify" / "refute" / "rerun_A.jsonl")
rB = by_id(JEV / "verify" / "refute" / "rerun_B.jsonl")


def P(run, rnd, seat):
    return {i: run[i][rnd][seat]["p_reject"] for i in ids if i in run and seat in run[i][rnd]}


def logit(p):
    p = min(max(p, 0.005), 0.995)
    return math.log(p / (1 - p))


def auc(d):
    """d: {id: score}. P(later-fixed scores above never-fixed), ties half."""
    pos = [v for i, v in d.items() if y[i]]
    neg = [v for i, v in d.items() if not y[i]]
    s = 0.0
    for a in pos:
        for b in neg:
            s += 1.0 if a > b else 0.5 if a == b else 0.0
    return s / (len(pos) * len(neg))


def mean(x):
    return sum(x) / len(x)


def pearson(a, b):
    ma, mb = mean(a), mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


def ranks(a):
    order = sorted(range(len(a)), key=lambda i: a[i])
    r = [0.0] * len(a)
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a, b):
    return pearson(ranks(a), ranks(b))


def within(d1, d2):
    """Pearson r of logits after centring each within label (the 'error' correlation)."""
    common = [i for i in ids if i in d1 and i in d2]
    xs, zs = [], []
    for lab in (True, False):
        g = [i for i in common if y[i] == lab]
        m1 = mean([logit(d1[i]) for i in g])
        m2 = mean([logit(d2[i]) for i in g])
        xs += [logit(d1[i]) - m1 for i in g]
        zs += [logit(d2[i]) - m2 for i in g]
    return pearson(xs, zs), len(common)


def ols_resid(yv, xcols):
    """Residuals of yv on [1, xcols...] by normal equations (tiny Gauss-Jordan)."""
    n = len(yv)
    X = [[1.0] + [c[k] for c in xcols] for k in range(n)]
    m = len(X[0])
    A = [[sum(X[k][i] * X[k][j] for k in range(n)) for j in range(m)] + [sum(X[k][i] * yv[k] for k in range(n))]
         for i in range(m)]
    for c in range(m):
        piv = max(range(c, m), key=lambda r: abs(A[r][c]))
        A[c], A[piv] = A[piv], A[c]
        for r in range(m):
            if r != c:
                f = A[r][c] / A[c][c]
                A[r] = [a - f * b for a, b in zip(A[r], A[c])]
    beta = [A[i][m] / A[i][i] for i in range(m)]
    fit = [sum(b * x for b, x in zip(beta, row)) for row in X]
    return [a - b for a, b in zip(yv, fit)], beta


def r2(yv, res):
    my = mean(yv)
    return 1 - sum(e * e for e in res) / sum((v - my) ** 2 for v in yv)


def jacobi_eig(M):
    n = len(M)
    A = [row[:] for row in M]
    for _ in range(200):
        off = max((abs(A[i][j]), i, j) for i in range(n) for j in range(n) if i != j)
        if off[0] < 1e-12:
            break
        _, p, q = off
        th = 0.5 * math.atan2(2 * A[p][q], A[q][q] - A[p][p])
        c, s = math.cos(th), math.sin(th)
        for k in range(n):
            akp, akq = A[k][p], A[k][q]
            A[k][p], A[k][q] = c * akp - s * akq, s * akp + c * akq
        for k in range(n):
            apk, aqk = A[p][k], A[q][k]
            A[p][k], A[q][k] = c * apk - s * aqk, s * apk + c * aqk
    return sorted((A[i][i] for i in range(n)), reverse=True)


def perm_auc_sd(n_iter=2000, seed=1):
    """SD of AUC for a score unrelated to the labels, 50 vs 50 (permutation)."""
    rnd = random.Random(seed)
    lab = [y[i] for i in ids]
    vals = []
    for _ in range(n_iter):
        sc = [rnd.random() for _ in ids]
        pos = [s for s, l in zip(sc, lab) if l]
        neg = [s for s, l in zip(sc, lab) if not l]
        vals.append(sum(1.0 for a in pos for b in neg if a > b) / (len(pos) * len(neg)))
    m = mean(vals)
    return math.sqrt(mean([(v - m) ** 2 for v in vals]))


print("== 0. Data ==")
for name, run in (("five", five), ("standard", std), ("one", one), ("rerun_A", rA), ("rerun_B", rB)):
    print(f"  {name:9s} n={len(run)} models={sorted({m for r in run.values() for m in r['models']})}")
allp = [a["p_reject"] for r in five.values() for rnd in ("round1", "round2") for a in r[rnd].values()]
print(f"  five-arm p values: {len(allp)}, distinct {len(set(allp))}, all on a 0.01 grid: "
      f"{all(abs(p * 100 - round(p * 100)) < 1e-9 for p in allp)}")
conf_ok = sum(abs(a["confidence"] - abs(1 - 2 * a["p_reject"])) <= 0.0101
              for r in five.values() for rnd in ("round1",) for a in r[rnd].values())
print(f"  confidence == |p(A) - p(R)| (to 0.01) in {conf_ok} of 500 Round-1 answers")
tok = {s: mean([five[i]["round1"][s]["usage"]["input_tokens"] for i in ids]) for s in SEATS}
small = [i for i in ids if feat[i]["state_chars"] < 1000]
print(f"  mean input tokens per seat, Round 1: " + ", ".join(f"{s} {tok[s]:.0f}" for s in SEATS))
print(f"  persona minus shortest persona (tokens, same state): " +
      ", ".join(f"{s} {mean([five[i]['round1'][s]['usage']['input_tokens'] - min(five[i]['round1'][t]['usage']['input_tokens'] for t in SEATS) for i in ids]):.0f}" for s in SEATS))
print(f"  states under 1000 chars: {len(small)} of 100")

sd0 = perm_auc_sd()
print(f"  AUC SD of a label-unrelated score, 50 vs 50: {sd0:.3f}")

print("\n== 1. Per-seat AUC ==")
R1 = {s: P(five, "round1", s) for s in SEATS}
R2 = {s: {i: (five[i]["round2"].get(s) or five[i]["round1"][s])["p_reject"] for i in ids} for s in SEATS}  # Round 1 where no debate ran (16)
ST = {s: P(std, "round1", s) for s in SEATS}
for s in SEATS:
    rej = sum(v >= 0.5 for v in R1[s].values())
    print(f"  {s:13s} R1 {auc(R1[s]):.3f}  R2 {auc(R2[s]):.3f}  standard R1 {auc(ST[s]):.3f} (n {len(ST[s])})"
          f"  mean p R1 {mean(list(R1[s].values())):.2f}  REJECT votes {rej}")
ONE, A_, B_ = P(one, "round1", "JEV"), P(rA, "round1", "JEV"), P(rB, "round1", "JEV")
print(f"  one question: {auc(ONE):.3f}, rerun A {auc(A_):.3f}, rerun B {auc(B_):.3f}")
pm = {i: mean([logit(R1[s][i]) for s in SEATS]) for i in ids}
print(f"  five-seat mean logit R1: {auc(pm):.3f}")
added = {i: feat[i]["added"] for i in ids}
print(f"  added lines: {auc(added):.3f}")

print("\n== 2. Spearman (all 100) / within-label r of logits, Round 1 ==")
print("  " + " " * 13 + "".join(f"{s[:8]:>16s}" for s in SEATS + ("one",)))
for s in SEATS:
    row = []
    for t in SEATS + ("one",):
        d2 = ONE if t == "one" else R1[t]
        a = [R1[s][i] for i in ids]
        b = [d2[i] for i in ids]
        row.append(f"{spearman(a, b):7.2f}/{within(R1[s], d2)[0]:5.2f}   ")
    print(f"  {s:13s}" + "".join(f"{x:>16s}" for x in row))
wl = [[within(R1[s], R1[t])[0] for t in SEATS] for s in SEATS]
ev = jacobi_eig(wl)
print(f"  eigenvalues of the within-label correlation matrix: {', '.join(f'{e:.3f}' for e in ev)}"
      f"  (first = {ev[0] / 5:.1%} of the variance)")

print("\n== 3. Test-retest: same question asked again vs another seat ==")
print(f"  one vs rerun_A {within(ONE, A_)[0]:.3f}, one vs rerun_B {within(ONE, B_)[0]:.3f}, "
      f"A vs B {within(A_, B_)[0]:.3f}  (within-label r)")
for s in SEATS:
    same, n = within(R1[s], ST[s])
    cross = [within(R1[s], ST[t])[0] for t in SEATS if t != s]
    print(f"  {s:13s} five-R1 vs standard-R1, same seat {same:.3f} (n {n}); vs the other four seats "
          f"{min(cross):.3f} to {max(cross):.3f}")

print("\n== 4. Shift/scale: seat A's logit fitted as a + b * seat B's logit (all 100) ==")
print("  R^2 of the fit / AUC of A's residual (A after removing B's ranking)")
for s in SEATS:
    out = []
    for t in SEATS:
        if s == t:
            out.append(" " * 14)
            continue
        ya = [logit(R1[s][i]) for i in ids]
        xb = [logit(R1[t][i]) for i in ids]
        res, beta = ols_resid(ya, [xb])
        out.append(f"{r2(ya, res):5.2f}/{auc(dict(zip(ids, res))):.3f}  ")
    print(f"  {s:13s}" + "".join(out))

print("\n== 5. Each seat's own part: residual on the mean of the other four seats ==")
print("  (reproducible across the two independent panel runs? AUC of that part?)")
uniq = {}
for s in SEATS:
    for run_name, D in (("five", R1), ("standard", ST)):
        common = [i for i in ids if all(i in D[t] for t in SEATS)]
        ya = [logit(D[s][i]) for i in common]
        xo = [mean([logit(D[t][i]) for t in SEATS if t != s]) for i in common]
        res, beta = ols_resid(ya, [xo])
        uniq[(s, run_name)] = dict(zip(common, res))
        if run_name == "five":
            print(f"  {s:13s} R^2 on the others {r2(ya, res):.3f}, slope {beta[1]:.2f}, "
                  f"own part AUC {auc(dict(zip(common, res))):.3f}", end="")
    a, b = uniq[(s, "five")], uniq[(s, "standard")]
    c = [i for i in ids if i in a and i in b]
    print(f"; own part five vs standard: r {pearson([a[i] for i in c], [b[i] for i in c]):.3f} (n {len(c)}),"
          f" standard own part AUC {auc(b):.3f}")
# noise floor: the same question's own part, one vs rerun A (residual of one on the mean of A and B)
ya = [logit(ONE[i]) for i in ids]
res, _ = ols_resid(ya, [[mean([logit(A_[i]), logit(B_[i])]) for i in ids]])
print(f"  one-question asked again: R^2 of one on mean(rerun A, B) {r2(ya, res):.3f}, residual AUC "
      f"{auc(dict(zip(ids, res))):.3f}")

print("\n== 6. What the own parts track (Spearman with simple features, five R1) ==")
fn = {"log added": lambda i: math.log1p(feat[i]["added"]), "log removed": lambda i: math.log1p(feat[i]["removed"]),
      "state chars": lambda i: feat[i]["state_chars"], "header": lambda i: float(feat[i]["header"]),
      "comment only": lambda i: float(feat[i]["comment_only"])}
print("  " + " " * 13 + "".join(f"{k:>14s}" for k in fn))
for s in SEATS:
    u = uniq[(s, "five")]
    c = list(u)
    print(f"  {s:13s}" + "".join(f"{spearman([u[i] for i in c], [f(i) for i in c]):14.2f}" for f in fn.values()))
print("  raw seat logits for comparison:")
for s in SEATS:
    print(f"  {s:13s}" + "".join(f"{spearman([R1[s][i] for i in ids], [f(i) for i in ids]):14.2f}" for f in fn.values()))

print("\n== 7. Contrasts between seats (seat X logit minus seat Y logit) ==")
print("  AUC in the five run / in the standard run / r of the contrast between runs")
for a in range(5):
    for b in range(a + 1, 5):
        s, t = SEATS[a], SEATS[b]
        c5 = {i: logit(R1[s][i]) - logit(R1[t][i]) for i in ids}
        cs = {i: logit(ST[s][i]) - logit(ST[t][i]) for i in ids if i in ST[s] and i in ST[t]}
        c = [i for i in cs]
        print(f"  {s:13s} - {t:13s} {auc(c5):.3f} / {auc(cs):.3f} / r {pearson([c5[i] for i in c], [cs[i] for i in c]):.2f} (n {len(c)})")

print("\n== 8. Debate: Round 2 (Round 1 where no debate ran) vs Round 1 per seat ==")
for s in SEATS:
    print(f"  {s:13s} within-label r R1 vs R2 {within(R1[s], R2[s])[0]:.3f}, vote changes "
          f"{sum((R1[s][i] >= 0.5) != (R2[s][i] >= 0.5) for i in ids)}")

print("\n== 9. Are the seats' AUCs different? Paired bootstrap (resampling within label), 2000 draws ==")
rnd = random.Random(7)
pos = [i for i in ids if y[i]]
neg = [i for i in ids if not y[i]]


def auc_list(sc, P_, N_):
    t = 0.0
    for a in P_:
        for b in N_:
            t += 1.0 if sc[a] > sc[b] else 0.5 if sc[a] == sc[b] else 0.0
    return t / (len(P_) * len(N_))


pairs = [("ADVOCATE", "SKEPTIC"), ("AUDITOR", "SKEPTIC"), ("ADVOCATE", "TEST-FOCUSED")]
diffs = {pr: [] for pr in pairs}
spread = []
for _ in range(2000):
    P_ = [rnd.choice(pos) for _ in pos]
    N_ = [rnd.choice(neg) for _ in neg]
    a = {s: auc_list(R1[s], P_, N_) for s in SEATS}
    for pr in pairs:
        diffs[pr].append(a[pr[0]] - a[pr[1]])
    spread.append(max(a.values()) - min(a.values()))
for pr in pairs:
    d = sorted(diffs[pr])
    print(f"  {pr[0]} - {pr[1]}: {auc(R1[pr[0]]) - auc(R1[pr[1]]):+.3f} [{d[50]:+.3f}, {d[1949]:+.3f}]")
obs = max(auc(R1[s]) for s in SEATS) - min(auc(R1[s]) for s in SEATS)
print(f"  best minus worst seat observed {obs:.3f}")
# null for the spread: seats that are the one question plus the noise seen between reruns.
# Swap seat labels within each commit (exchangeable seats) and recompute the spread.
ge = 0
for _ in range(2000):
    perm = {s: {} for s in SEATS}
    for i in ids:
        vals = [R1[s][i] for s in SEATS]
        # remove each seat's mean shift first, so only the ranking content is exchanged
        rnd.shuffle(vals)
        for s, v in zip(SEATS, vals):
            perm[s][i] = v
    sp = max(auc(perm[s]) for s in SEATS) - min(auc(perm[s]) for s in SEATS)
    ge += sp >= obs
print(f"  seat labels shuffled within commit: spread >= observed in {ge} of 2000 (raw p; shuffling also mixes"
      " strictness, so this is only a rough null)")

print("\n== 10. Planted lines, per seat (controls_five.jsonl vs sessions_five Round 1, never-fixed changes) ==")
ctrl = [r["jev"] for r in jl(JEV / "controls_five.jsonl")]
for name in sorted({c["plant"] for c in ctrl}):
    print(f"  {name}:")
    for s in SEATS:
        before, after = [], []
        for c in ctrl:
            if c["plant"] != name:
                continue
            before.append(logit(R1[s][c["id"]]))
            after.append(logit(c["round1"][s]["p_reject"]))
        n = len(before)
        print(f"    {s:13s} n {n}: mean logit {mean(before):+.2f} -> {mean(after):+.2f} (rise {mean(after) - mean(before):+.2f}),"
              f" p>=0.5 after {sum(a >= 0 for a in after)}")
