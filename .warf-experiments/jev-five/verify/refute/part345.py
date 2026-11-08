"""Part 3: memorisation (older vs newer commits). Part 4: Jev vs Laya, paired, and what would settle
it. Part 5: is the Jev-Claude agreement more than shared size/file effects?"""
import math
import random
from load import S, y, F, DATE, ids
from vstats import (auc, delong_single, delong_paired, delong, corr, spearman, mean, ols, standardize_cols,
                    norm_sf, norm_ppf, logit_fit, chi2_sf_1, binom_two_sided)

J, J3, C, L = S["jev0"], S["jev3"], S["claude"], S["laya1"]

print("== Part 3: older vs newer commits")
med = sorted(DATE)[50]
for name, cut in (("median commit date", med), ("2017-01-01 (git era)", 2017.0), ("2020-01-01", 2020.0)):
    old = [k for k in range(100) if DATE[k] < cut]
    new = [k for k in range(100) if DATE[k] >= cut]
    row = []
    for grp, idx in (("older", old), ("newer", new)):
        yy = [y[k] for k in idx]
        a, se = delong_single([J[k] for k in idx], yy)
        a3 = auc([J3[k] for k in idx], yy)
        ac = auc([C[k] for k in idx], yy)
        al = auc([L[k] for k in idx], yy)
        row.append((grp, len(idx), sum(yy), a, se, a3, ac, al))
    d = row[0][3] - row[1][3]
    se = math.sqrt(row[0][4] ** 2 + row[1][4] ** 2)
    print(f"  split at {name} ({cut:.2f}):")
    for grp, n, r, a, s_, a3, ac, al in row:
        print(f"    {grp}: n {n} (R {r}, A {n - r})  Jev {a:.3f} ± {s_:.3f}  Jev3 {a3:.3f}  Claude {ac:.3f}  Laya {al:.3f}")
    print(f"    older minus newer, Jev: {d:+.3f} ± {se:.3f} (z {d / se:+.2f})")
# Jev x date interaction in a logistic model (standardised)
lg = [math.log(max(1e-4, min(1 - 1e-4, v)) / (1 - max(1e-4, min(1 - 1e-4, v)))) for v in J]
Z = standardize_cols([[a, b] for a, b in zip(lg, DATE)])
X0 = [[a, b] for a, b in Z]
X1 = [[a, b, a * b] for a, b in Z]
b0, ll0, _ = logit_fit(X0, [float(t) for t in y], 0.0)
b1, ll1, cv = logit_fit(X1, [float(t) for t in y], 0.0)
lr = 2 * (ll1 - ll0)
print(f"  logistic label ~ Jev + date + Jev x date: interaction {b1[-1]:+.3f} (z {b1[-1] / math.sqrt(cv[-1][-1]):+.2f}), LR p {chi2_sf_1(lr):.3f}  [negative = Jev better on older commits]")
# Correlation of date with the label and with Jev
print(f"  date AUC against labels {auc(DATE, y):.3f} (later-fixed commits are older); Spearman(date, Jev) {spearman(DATE, J):+.2f}, "
      f"(date, Claude) {spearman(DATE, C):+.2f}")
# within-pair: does Jev win the pair more often when the pair is old?
pdate = [(DATE[2 * k] + DATE[2 * k + 1]) / 2 for k in range(50)]
pm = sorted(pdate)[25]
for grp, sel_ in (("older pairs", [k for k in range(50) if pdate[k] < pm]), ("newer pairs", [k for k in range(50) if pdate[k] >= pm])):
    w = sum(J[2 * k] > J[2 * k + 1] for k in sel_)
    wc = sum(C[2 * k] > C[2 * k + 1] for k in sel_)
    print(f"    {grp}: {len(sel_)} pairs, Jev won {w} (sign p {binom_two_sided(w, len(sel_)):.2f}), Claude won {wc}")
gap = [abs(DATE[2 * k] - DATE[2 * k + 1]) for k in range(50)]
print(f"    years between the two commits of a pair: median {sorted(gap)[25]:.1f}")
# For later-fixed commits: when the fix landed (all before Jev 1.14's date 2026-10-14)
fixd = [min(f["fix_dates"]) for f in F if f["label"] == "REJECT"]
print(f"  later-fixed: first fix dates from {min(fixd)[:10]} to {max(fixd)[:10]}; all {len(fixd)} before 2026-10-14; "
      f"{sum(d >= '2024' for d in fixd)} fixed in 2024 or later")
# Jev's p on later-fixed commits: fixed quickly vs slowly (a recall effect would not care how fast)
days = [min(f["fix_days"]) for f in F if f["label"] == "REJECT"]
jr = [J[k] for k in range(100) if y[k]]
print(f"  among later-fixed: Spearman(Jev p, days to fix) {spearman(jr, days):+.2f}; kinds {sorted(set(k for f in F for k in f['fix_kinds']))}")
for kind in ("build", "defect"):
    idx = [k for k in range(100) if y[k] and kind in F[k]["fix_kinds"]]
    neg = [k for k in range(100) if not y[k]]
    print(f"    later-fixed by a '{kind}' fix: n {len(idx)}, Jev AUC vs all never-fixed {auc([J[k] for k in idx + neg], [y[k] for k in idx + neg]):.3f}, "
          f"Claude {auc([C[k] for k in idx + neg], [y[k] for k in idx + neg]):.3f}")
svn = [k for k in range(100) if F[k]["author"].startswith("svn_")]
print(f"  svn-imported authors: {len(svn)} commits (R {sum(y[k] for k in svn)})")

print("\n== Part 4: Jev vs Laya on the same 100, paired")
for a_, b_ in (("jev0", "laya1"), ("jev3", "laya1"), ("five_r1", "laya5_r1"), ("five_final", "laya5_final")):
    d, se, z, p, Sm = delong_paired(S[a_], S[b_], y)
    r = Sm[0][1] / math.sqrt(Sm[0][0] * Sm[1][1])
    print(f"  {a_} - {b_}: {d:+.3f} ± {se:.3f} (DeLong), z {z:.2f}, two-sided p {p:.3f}; corr of the AUC estimates {r:+.2f}; "
          f"score correlation {corr(S[a_], S[b_]):+.2f}")
# pair-level bootstrap (resample the 50 matched pairs)
rng = random.Random(21)
B = 4000
ds = []
for _ in range(B):
    pk = [rng.randrange(50) for _ in range(50)]
    idx = [2 * k for k in pk] + [2 * k + 1 for k in pk]
    yy = [y[i] for i in idx]
    ds.append(auc([J[i] for i in idx], yy) - auc([L[i] for i in idx], yy))
ds.sort()
print(f"  jev0 - laya1, bootstrap over matched pairs: 95 % [{ds[int(0.025 * B)]:+.3f}, {ds[int(0.975 * B)]:+.3f}], "
      f"P(diff <= 0) {sum(d <= 0 for d in ds) / B:.3f}")
# matched-pair wins
jw = [J[2 * k] > J[2 * k + 1] for k in range(50)]
lw = [L[2 * k] > L[2 * k + 1] for k in range(50)]
b10 = sum(a and not b for a, b in zip(jw, lw))
b01 = sum(b and not a for a, b in zip(jw, lw))
print(f"  pairs won: Jev {sum(jw)}, Laya {sum(lw)}; Jev only {b10}, Laya only {b01}; McNemar exact p {binom_two_sided(b10, b10 + b01):.2f}")
# after adjusting both for added lines: residual AUCs
fx = standardize_cols([[math.log1p(f["added"]), float(f["comment_only"]), float(f["status"] in ("deleted", "deletion-only"))] for f in F])
_, rj, _ = ols(fx, J)
_, rl, _ = ols(fx, L)
d, se, z, p, _ = delong_paired(rj, rl, y)
print(f"  residuals after added lines/comment-only/deletion: Jev {auc(rj, y):.3f}, Laya {auc(rl, y):.3f}, difference {d:+.3f} ± {se:.3f} (p {p:.2f})")
# What would settle it: n per class for 80 % power, two-sided alpha 0.05, using this variance structure
_, se0, _, _, _ = delong_paired(J, L, y)
za, zb = norm_ppf(0.975), norm_ppf(0.80)
for delta in (0.055, 0.10, 0.03):
    n = 50 * (se0 * (za + zb) / delta) ** 2
    print(f"  to detect a true difference of {delta:.3f} with 80 % power: about {math.ceil(n)} later-fixed + {math.ceil(n)} never-fixed changes")
# also: one-sided non-inferiority/superiority SE at n=50: half-width
print(f"  half-width of the 95 % interval at 50+50: {1.96 * se0:.3f}")

print("\n== Part 5: Jev's agreement with Claude")
def partial(a, b, Xc):
    _, ra, _ = ols(Xc, a)
    _, rb, _ = ols(Xc, b)
    return corr(ra, rb), spearman(ra, rb)

def fisher_ci(r, n, k):
    zr = math.atanh(r)
    se = 1 / math.sqrt(n - 3 - k)
    return math.tanh(zr - 1.96 * se), math.tanh(zr + 1.96 * se), 2 * norm_sf(abs(zr) / se)

def lgt(v):
    v = max(1e-4, min(1 - 1e-4, v))
    return math.log(v / (1 - v))

print(f"  raw: Pearson Jev-Claude {corr(J, C):.2f}, Spearman {spearman(J, C):.2f}; Jev3-Claude {corr(J3, C):.2f}; "
      f"Laya-Claude {corr(L, C):.2f}; Jev-Laya {corr(J, L):.2f}")
cov_sets = {
    "size (patch chars, state tokens)": [[math.log(f["patch_chars"]), f["state_tokens"]] for f in F],
    "added/removed lines": [[math.log1p(f["added"]), math.log1p(f["removed"])] for f in F],
    "file/kind (new, deletion, comment-only, header, test, extensions, enriched, SECURITY)":
        [[float(f["status"] == "new"), float(f["status"] in ("deleted", "deletion-only")), float(f["comment_only"]),
          float(f["header"]), float(f["test_or_example"]), float(f["extensions_dir"]), float(f["enriched"]),
          float(f["domain"] == "SECURITY")] for f in F],
    "all of the above + date": [[math.log(f["patch_chars"]), f["state_tokens"], math.log1p(f["added"]), math.log1p(f["removed"]),
          float(f["status"] == "new"), float(f["status"] in ("deleted", "deletion-only")), float(f["comment_only"]),
          float(f["header"]), float(f["test_or_example"]), float(f["extensions_dir"]), float(f["enriched"]),
          float(f["domain"] == "SECURITY"), DATE[k]] for k, f in enumerate(F)],
}
cov_sets["all of the above + date + label"] = [r + [float(t)] for r, t in zip(cov_sets["all of the above + date"], y)]
for name, Xc in cov_sets.items():
    Xc = standardize_cols(Xc)
    pr, ps = partial(J, C, Xc)
    pr3, _ = partial(J3, C, Xc)
    prl, _ = partial(L, C, Xc)
    prlg, _ = partial([lgt(v) for v in J], [lgt(v) for v in C], Xc)
    lo, hi, p = fisher_ci(pr, 100, len(Xc[0]))
    print(f"  partial on {name}: Jev-Claude r {pr:.2f} [{lo:.2f}, {hi:.2f}] p {p:.2g} (Spearman of residuals {ps:.2f}; logits {prlg:.2f}; Jev3 {pr3:.2f}); Laya-Claude {prl:.2f}")
# within label
for lab in (True, False):
    idx = [k for k in range(100) if y[k] == lab]
    print(f"  within {'later-fixed' if lab else 'never-fixed'} (n 50): Jev-Claude Pearson {corr([J[k] for k in idx], [C[k] for k in idx]):.2f}, "
          f"Spearman {spearman([J[k] for k in idx], [C[k] for k in idx]):.2f}")
# within matched pairs: differences
dj = [J[2 * k] - J[2 * k + 1] for k in range(50)]
dc = [C[2 * k] - C[2 * k + 1] for k in range(50)]
dl = [L[2 * k] - L[2 * k + 1] for k in range(50)]
print(f"  within matched pairs (difference R minus A): Jev-Claude Pearson {corr(dj, dc):.2f}, Spearman {spearman(dj, dc):.2f}; "
      f"Laya-Claude {corr(dl, dc):.2f}; sign agreement {sum((a > 0) == (b > 0) for a, b in zip(dj, dc))}/50")
# within-pair differences after removing the added-lines difference
dadd = [math.log1p(F[2 * k]["added"]) - math.log1p(F[2 * k + 1]["added"]) for k in range(50)]
dcom = [float(F[2 * k]["comment_only"]) - float(F[2 * k + 1]["comment_only"]) for k in range(50)]
ddel = [float(F[2 * k]["status"] in ("deleted", "deletion-only")) - float(F[2 * k + 1]["status"] in ("deleted", "deletion-only")) for k in range(50)]
dnew = [float(F[2 * k]["status"] == "new") - float(F[2 * k + 1]["status"] == "new") for k in range(50)]
Xd = [[a, b, c, d] for a, b, c, d in zip(dadd, dcom, ddel, dnew)]
pr, ps = partial(dj, dc, standardize_cols(Xd))
print(f"  within pairs, partial on the differences in added lines, comment-only, deletion, new file: r {pr:.2f} (Spearman {ps:.2f})")
# Mixed pairs: all 4950 pairs of commits, how often Jev and Claude order them the same way (concordance)
conc = disc = 0
for i in range(100):
    for j in range(i + 1, 100):
        s1 = (J[i] > J[j]) - (J[i] < J[j])
        s2 = (C[i] > C[j]) - (C[i] < C[j])
        if s1 * s2 > 0:
            conc += 1
        elif s1 * s2 < 0:
            disc += 1
print(f"  Kendall-type: concordant {conc}, discordant {disc}, tau-a-ish {(conc - disc) / 4950:.2f}")
# Permutation null for the fully adjusted partial correlation (shuffle Jev's residual)
Xc = standardize_cols(cov_sets["all of the above + date + label"])
_, ra, _ = ols(Xc, J)
_, rb, _ = ols(Xc, C)
obs = corr(ra, rb)
rng = random.Random(5)
ge = 0
B = 4000
for _ in range(B):
    sh = ra[:]
    rng.shuffle(sh)
    if corr(sh, rb) >= obs:
        ge += 1
print(f"  permutation (residuals shuffled), fully adjusted incl. label: r {obs:.2f}, one-sided p {(ge + 1) / (B + 1):.4f}")
# Without the trivially safe commits
idx = [k for k in range(100) if not (F[k]["comment_only"] or F[k]["status"] in ("deleted", "deletion-only"))]
Xs = standardize_cols([[math.log(F[k]["patch_chars"]), F[k]["state_tokens"], math.log1p(F[k]["added"]), math.log1p(F[k]["removed"]),
                        float(F[k]["status"] == "new"), float(F[k]["header"]), float(F[k]["test_or_example"]),
                        float(F[k]["extensions_dir"]), float(F[k]["enriched"]), DATE[k], float(y[k])] for k in idx])
_, ra, _ = ols(Xs, [J[k] for k in idx])
_, rb, _ = ols(Xs, [C[k] for k in idx])
print(f"  85 commits that add a non-comment line: raw r {corr([J[k] for k in idx], [C[k] for k in idx]):.2f}, "
      f"partial (features + label) r {corr(ra, rb):.2f}")
