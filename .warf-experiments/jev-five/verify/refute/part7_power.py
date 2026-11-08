"""Part 7, positive control for the adjustment test: a planted score that ranks the labels at about
AUC 0.64 but is independent of added lines - how often does the pair-matched test after added
lines detect it (p < 0.05)? And a planted score made only of added lines + noise, at Jev's
correlation with added lines - how often does it pass?"""
import math
import random
from part2d_added import col
from load import y, F, S
from vstats import auc, chi2_sf_1, solve, mean, spearman

def clogit_vals(cols, ridge=0.1):
    D = [[c[2 * k] - c[2 * k + 1] for c in cols] for k in range(50)]
    sd = [math.sqrt(sum((x - mean(c)) ** 2 for x in c) / 99) or 1.0 for c in cols]
    D = [[d / s for d, s in zip(r, sd)] for r in D]
    p = len(cols)
    beta = [0.0] * p
    for _ in range(60):
        eta = [sum(b * v for b, v in zip(beta, r)) for r in D]
        mu = [1 / (1 + math.exp(-max(-35, min(35, e)))) for e in eta]
        g = [sum((1 - m) * r[i] for r, m in zip(D, mu)) - ridge * beta[i] for i in range(p)]
        H = [[sum(m * (1 - m) * r[i] * r[j] for r, m in zip(D, mu)) + (ridge if i == j else 0) for j in range(p)] for i in range(p)]
        st = solve(H, g)
        beta = [b + s for b, s in zip(beta, st)]
        if max(abs(s) for s in st) < 1e-9:
            break
    eta = [sum(b * v for b, v in zip(beta, r)) for r in D]
    return sum(-math.log1p(math.exp(-max(-35, min(35, e)))) for e in eta)

add = col["log1p added"]
ll0 = clogit_vals([add])
rng = random.Random(17)
print("== Part 7: power of the pair-matched 'beyond added lines' test")
for delta in (0.5, 0.6, 0.7):
    hits = 0
    aucs = []
    for _ in range(300):
        s = [delta * float(t) + rng.gauss(0, 1) for t in y]
        aucs.append(auc(s, y))
        lr = 2 * (clogit_vals([add, s]) - ll0)
        hits += chi2_sf_1(lr) < 0.05
    print(f"  independent planted signal, mean AUC {mean(aucs):.3f}: detected beyond added lines in {hits / 3:.0f} % of 300")
# a score built from added lines plus noise, tuned to Jev's correlation with added lines
for w in (0.35, 0.5):
    hits = 0
    aucs = []
    rhos = []
    for _ in range(300):
        za = [(a - mean(add)) / (sum((x - mean(add)) ** 2 for x in add) / 99) ** 0.5 for a in add]
        s = [w * z + rng.gauss(0, 1) for z in za]
        aucs.append(auc(s, y))
        rhos.append(spearman(s, [f['added'] for f in F]))
        lr = 2 * (clogit_vals([add, s]) - ll0)
        hits += chi2_sf_1(lr) < 0.05
    print(f"  added lines + noise (weight {w}), mean AUC {mean(aucs):.3f}, mean rho with added {mean(rhos):.2f}: 'beyond added lines' p<0.05 in {hits / 3:.0f} % (nominal 5 %)")
print(f"  for reference: Jev AUC {auc(S['jev0'], y):.3f}, rho(Jev, added) {spearman(S['jev0'], [f['added'] for f in F]):.2f}")
