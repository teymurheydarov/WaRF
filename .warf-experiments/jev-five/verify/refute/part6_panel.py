"""Part 6: the five-agent panel and the debate against one question (with the 3-run mean), and a
trivial baseline (number of added lines) against Jev."""
import math
from load import S, y, F, AGENTS, five, ids
from vstats import auc, delong_single, delong_paired, corr, mean, logit_fit, standardize_cols, chi2_sf_1

J, J3 = S["jev0"], S["jev3"]
added = [float(f["added"]) for f in F]
nb = [float(f["nonblank_added"]) for f in F]

print("== Part 6a: panel and debate vs one question")
for a_, b_ in (("five_r1", "jev0"), ("five_r1", "jev3"), ("five_final", "jev3"), ("five_final", "five_r1")):
    d, se, z, p, _ = delong_paired(S[a_], S[b_], y)
    print(f"  {a_} - {b_}: {d:+.3f} ± {se:.3f}, 95 % [{d - 1.96 * se:+.3f}, {d + 1.96 * se:+.3f}], p {p:.2f}")
for a in AGENTS:
    d, se, z, p, _ = delong_paired(S[f"five_{a}"], J3, y)
    print(f"  {a:<13} R1 {auc(S[f'five_{a}'], y):.3f}, minus jev3 {d:+.3f} ± {se:.3f}; corr with jev3 {corr(S[f'five_{a}'], J3):.2f}")
both = [(a + b) / 2 for a, b in zip(J3, S["five_r1"])]
print(f"  mean of jev3 and panel R1: {auc(both, y):.3f}")
lg = lambda v: math.log(max(1e-4, min(1 - 1e-4, v)) / (1 - max(1e-4, min(1 - 1e-4, v))))
X0 = standardize_cols([[lg(v)] for v in J3])
X1 = standardize_cols([[lg(v)] + [lg(S[f'five_{a}'][k]) for a in AGENTS] for k, v in enumerate(J3)])
_, ll0, _ = logit_fit(X0, [float(t) for t in y], 0.01)
_, ll1, _ = logit_fit(X1, [float(t) for t in y], 0.01)
lr = 2 * (ll1 - ll0)
from vstats import chi2_sf_1
# 5 extra df: chi2 sf by series
def chi2_sf(x, k):
    # regularised upper gamma for integer/half-integer k via series
    import math
    s = k / 2.0
    xx = x / 2.0
    term = math.exp(-xx + s * math.log(xx) - math.lgamma(s + 1)) if xx > 0 else 0.0
    tot = term
    n = 1
    while term > 1e-15 * tot and n < 10000:
        term *= xx / (s + n)
        tot += term
        n += 1
    return max(0.0, 1 - tot)
print(f"  label ~ jev3 + five agents' logits: LR {lr:.2f} on 5 df, p {chi2_sf(lr, 5):.2f}")
D = [i for i in ids if len(five[i]["jev"]["round2"]) == 5]
print(f"  debated commits {len(D)}; Round-2 choice changes {sum(five[i]['jev']['round1'][a]['choice'] != five[i]['jev']['round2'][a]['choice'] for i in D for a in AGENTS)} of {5 * len(D)}")

print("\n== Part 6b: a trivial baseline against Jev")
for name, s in (("added lines", added), ("nonblank added lines", nb)):
    for other in ("jev0", "jev3", "claude"):
        d, se, z, p, _ = delong_paired(s, S[other], y)
        print(f"  {name} ({auc(s, y):.3f}) - {other} ({auc(S[other], y):.3f}): {d:+.3f} ± {se:.3f}, p {p:.2f}")
