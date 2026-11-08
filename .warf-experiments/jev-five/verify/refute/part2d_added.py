"""Part 2d: is Jev's ranking more than the number of added lines (and the trivially safe changes)?
Unconditional (ridge logistic) and pair-matched (conditional logistic) models, sensitivity to the
ridge, and Jev's AUC within bins of added lines."""
import math
import random
from load import S, y, F, DATE
from vstats import auc, delong_single, delong_paired, spearman, mean, logit_fit, logit_predict, standardize_cols, chi2_sf_1, solve

yy = [float(t) for t in y]


def lgt(v):
    v = max(1e-4, min(1 - 1e-4, v))
    return math.log(v / (1 - v))


col = {
    "log1p added": [math.log1p(f["added"]) for f in F],
    "log1p removed": [math.log1p(f["removed"]) for f in F],
    "comment-only": [float(f["comment_only"]) for f in F],
    "deletion-only/deleted": [float(f["status"] in ("deleted", "deletion-only")) for f in F],
    "new": [float(f["status"] == "new") for f in F],
    "header": [float(f["header"]) for f in F],
    "test/example": [float(f["test_or_example"]) for f in F],
    "log patch chars": [math.log(f["patch_chars"]) for f in F],
    "extensions/": [float(f["extensions_dir"]) for f in F],
    "enriched": [float(f["enriched"]) for f in F],
    "year": DATE,
    "logit Jev": [lgt(v) for v in S["jev0"]],
    "logit Jev3": [lgt(v) for v in S["jev3"]],
    "logit Claude": [lgt(v) for v in S["claude"]],
    "logit Laya": [lgt(v) for v in S["laya1"]],
}
ALL11 = ["new", "deletion-only/deleted", "comment-only", "header", "test/example", "log1p added", "log1p removed",
         "log patch chars", "extensions/", "enriched", "year"]


def design(names):
    return standardize_cols([[col[n][k] for n in names] for k in range(100)])


def lr_test(base, extra, ridge):
    X0 = design(base)
    X1 = design(base + [extra])
    b0, ll0, _ = logit_fit(X0, yy, ridge)
    b1, ll1, cv = logit_fit(X1, yy, ridge)
    lr = 2 * (ll1 - ll0)
    return lr, chi2_sf_1(lr), b1[-1], b1[-1] / math.sqrt(cv[-1][-1])


print("== Part 2d: does Jev add to simple features? (unconditional logistic, ridge on standardised slopes)")
for base in (["log1p added"], ["log1p added", "comment-only", "deletion-only/deleted"], ALL11):
    for extra in ("logit Jev", "logit Jev3", "logit Claude", "logit Laya"):
        cells = []
        for ridge in (0.01, 1.0, 10.0):
            lr, p, b, z = lr_test(base, extra, ridge)
            cells.append(f"ridge {ridge:g}: LR {lr:5.2f} p {p:.3f} (z {z:+.2f})")
        print(f"  {'+'.join(base) if len(base) < 4 else '11 features':<52} + {extra:<12} " + " | ".join(cells))
# The reverse: do the features add to Jev?
for extra in ("log1p added", "comment-only"):
    lr, p, b, z = lr_test(["logit Jev"], extra, 0.01)
    print(f"  logit Jev + {extra}: LR {lr:.2f} p {p:.4f} (z {z:+.2f})")


# Pair-matched (conditional logistic): P(row 2k is the later-fixed one) = sigma(beta . (x_2k - x_2k+1))
def clogit(names, ridge=0.0, iters=100):
    D = [[col[n][2 * k] - col[n][2 * k + 1] for n in names] for k in range(50)]
    # scale each column by its SD across the 100 rows so ridge is comparable
    sd = []
    for n in names:
        v = col[n]
        m = mean(v)
        sd.append(math.sqrt(sum((x - m) ** 2 for x in v) / 99) or 1.0)
    D = [[d / s for d, s in zip(r, sd)] for r in D]
    p = len(names)
    beta = [0.0] * p
    for _ in range(iters):
        eta = [sum(b * v for b, v in zip(beta, r)) for r in D]
        mu = [1 / (1 + math.exp(-e)) for e in eta]
        g = [sum((1 - m) * r[i] for r, m in zip(D, mu)) - ridge * beta[i] for i in range(p)]
        H = [[sum(m * (1 - m) * r[i] * r[j] for r, m in zip(D, mu)) + (ridge if i == j else 0) for j in range(p)] for i in range(p)]
        st = solve(H, g)
        beta = [b + s for b, s in zip(beta, st)]
        if max(abs(s) for s in st) < 1e-10:
            break
    eta = [sum(b * v for b, v in zip(beta, r)) for r in D]
    ll = sum(-math.log1p(math.exp(-e)) for e in eta)
    return beta, ll


print("\n  pair-matched conditional logistic (50 pairs), ridge 0.1:")
for base in ([], ["log1p added"], ["log1p added", "comment-only", "deletion-only/deleted"], ALL11):
    for extra in ("logit Jev", "logit Jev3", "logit Claude", "logit Laya"):
        _, ll0 = clogit(base, 0.1) if base else ([], 50 * math.log(0.5))
        b1, ll1 = clogit(base + [extra], 0.1)
        lr = 2 * (ll1 - ll0)
        print(f"    {('+'.join(base) if len(base) < 4 else '11 features') or '(nothing)':<52} + {extra:<12} LR {lr:5.2f}, p {chi2_sf_1(lr):.4f}, beta {b1[-1]:+.2f}")

print("\n  Jev's AUC within bins of added lines:")
bins = [(0, 0), (1, 1), (2, 3), (4, 7), (8, 15), (16, 10 ** 6)]
num = den = 0.0
numc = 0.0
for lo, hi in bins:
    idx = [k for k, f in enumerate(F) if lo <= f["added"] <= hi]
    nr = sum(y[k] for k in idx)
    na = len(idx) - nr
    if nr and na:
        a = auc([S["jev0"][k] for k in idx], [y[k] for k in idx])
        c = auc([S["claude"][k] for k in idx], [y[k] for k in idx])
        num += a * nr * na
        numc += c * nr * na
        den += nr * na
        print(f"    added {lo}-{hi if hi < 10 ** 6 else 'more'}: R {nr:>2} A {na:>2}  Jev AUC {a:.3f}  Claude AUC {c:.3f}  mean Jev p R {mean([S['jev0'][k] for k in idx if y[k]]):.3f} A {mean([S['jev0'][k] for k in idx if not y[k]]):.3f}")
    else:
        print(f"    added {lo}-{hi if hi < 10 ** 6 else 'more'}: R {nr:>2} A {na:>2}  (one label only)  mean Jev p {mean([S['jev0'][k] for k in idx]) if idx else float('nan'):.3f}")
print(f"    pooled within-bin AUC: Jev {num / den:.3f}, Claude {numc / den:.3f} ({int(den)} comparisons)")
# permutation p for the within-bin AUC: shuffle labels within bins
key = [next(b for b, (lo, hi) in enumerate(bins) if lo <= f["added"] <= hi) for f in F]
def within(s, lab):
    n = d = 0.0
    for b in set(key):
        P = [s[k] for k in range(100) if key[k] == b and lab[k]]
        N = [s[k] for k in range(100) if key[k] == b and not lab[k]]
        n += sum((p > q) + 0.5 * (p == q) for p in P for q in N)
        d += len(P) * len(N)
    return n / d
obs = within(S["jev0"], y)
rng = random.Random(4)
ge = 0
B = 3000
for _ in range(B):
    lab = y[:]
    for b in set(key):
        idx = [k for k in range(100) if key[k] == b]
        vals = [lab[k] for k in idx]
        rng.shuffle(vals)
        for k, v in zip(idx, vals):
            lab[k] = v
    if within(S["jev0"], lab) >= obs:
        ge += 1
print(f"    permutation within bins: Jev within-bin AUC {obs:.3f}, one-sided p {(ge + 1) / (B + 1):.3f}")
print(f"\n  added lines: mean R {mean([f['added'] for f, t in zip(F, y) if t]):.1f}, A {mean([f['added'] for f, t in zip(F, y) if not t]):.1f}; "
      f"median R {sorted(f['added'] for f, t in zip(F, y) if t)[25]}, A {sorted(f['added'] for f, t in zip(F, y) if not t)[25]}")
print(f"  Spearman(Jev, added) among R {spearman([S['jev0'][k] for k in range(100) if y[k]], [F[k]['added'] for k in range(100) if y[k]]):+.2f}, "
      f"among A {spearman([S['jev0'][k] for k in range(100) if not y[k]], [F[k]['added'] for k in range(100) if not y[k]]):+.2f}")
