"""Part 2: simple features that might drive Jev's p and the labels."""
import math
import random
from load import S, y, ids, F, DATE
from vstats import (auc, delong_single, delong_paired, corr, spearman, mean, ols, logit_fit, logit_predict,
                    standardize_cols, chi2_sf_1, norm_sf)

J = S["jev0"]
J3 = S["jev3"]
C = S["claude"]
L = S["laya1"]

feat = {
    "new file": [f["status"] == "new" for f in F],
    "deleted file or deletion-only": [f["status"] in ("deleted", "deletion-only") for f in F],
    "modified (adds and keeps)": [f["status"] == "modified" for f in F],
    "header (.h/.hpp)": [f["header"] for f in F],
    "test or example path": [f["test_or_example"] for f in F],
    "comment-only change": [f["comment_only"] for f in F],
    "addition-only (no removed line)": [f["addition_only"] for f in F],
    "extensions/ dir": [f["extensions_dir"] for f in F],
    "src/ dir": [f["top"] == "src" for f in F],
    "domain SECURITY": [f["domain"] == "SECURITY" for f in F],
    "enriched with function bodies": [f["enriched"] for f in F],
    "hunks": [f["hunks"] for f in F],
    "added lines": [f["added"] for f in F],
    "removed lines": [f["removed"] for f in F],
    "nonblank added lines": [f["nonblank_added"] for f in F],
    "added - removed": [f["added"] - f["removed"] for f in F],
    "added share a/(a+r)": [f["added"] / (f["added"] + f["removed"]) if f["added"] + f["removed"] else 0.5 for f in F],
    "patch chars": [f["patch_chars"] for f in F],
    "state tokens": [f["state_tokens"] for f in F],
    "files in commit": [f["files_in_commit"] for f in F],
    "commit date (year)": DATE,
}

print("== Part 2a: each feature's own AUC against the labels; its link to Jev (one question) and Claude")
print(f"  {'feature':<34} {'n true/mean':>11} {'AUC(label)':>10} {'±':>6}  {'rho(Jev)':>8} {'rho(Claude)':>11}  mean Jev p if true/false")
for name, v in feat.items():
    x = [float(t) for t in v]
    a, se = delong_single(x, y)
    rj, rc = spearman(x, J), spearman(x, C)
    if all(t in (0.0, 1.0) for t in x):
        on = [j for j, t in zip(J, x) if t]
        off = [j for j, t in zip(J, x) if not t]
        extra = f"{mean(on):.3f} / {mean(off):.3f}" if on and off else ""
        cnt = f"{int(sum(x))} (R {sum(1 for t, l in zip(x, y) if t and l)})"
    else:
        extra = ""
        cnt = f"{mean(x):.1f}"
    print(f"  {name:<34} {cnt:>11} {a:>10.3f} {se:>6.3f}  {rj:>8.2f} {rc:>11.2f}  {extra}")

# Status x label table with Jev mean p
print("\n  status by label, mean Jev p (one question) and Claude p:")
for st in ("new", "modified", "deletion-only", "deleted"):
    for lab in (True, False):
        idx = [k for k, f in enumerate(F) if f["status"] == st and y[k] == lab]
        if idx:
            print(f"    {st:<14} {'REJECT ' if lab else 'APPROVE'} n={len(idx):>2}  Jev {mean([J[k] for k in idx]):.3f}  Claude {mean([C[k] for k in idx]):.3f}  Laya {mean([L[k] for k in idx]):.3f}")
idx = [k for k, f in enumerate(F) if f["comment_only"]]
print(f"    comment-only   APPROVE n={len(idx)}  Jev {mean([J[k] for k in idx]):.3f} (others {mean([J[k] for k in range(100) if k not in idx]):.3f})")

print("\n== Part 2b: Jev's AUC within strata")
def sub_auc(idx, s):
    yy = [y[k] for k in idx]
    if sum(yy) == 0 or sum(yy) == len(yy):
        return None
    a = auc([s[k] for k in idx], yy)
    return a, delong_single([s[k] for k in idx], yy)[1], sum(yy), len(yy) - sum(yy)

trivial = [f["status"] in ("deleted", "deletion-only") or f["comment_only"] for f in F]
strata = {
    "all 100": list(range(100)),
    "modified files only": [k for k, f in enumerate(F) if f["status"] == "modified"],
    "new files only": [k for k, f in enumerate(F) if f["status"] == "new"],
    "headers only": [k for k, f in enumerate(F) if f["header"]],
    "sources only (.cpp etc.)": [k for k, f in enumerate(F) if not f["header"]],
    "adds a non-comment line (no deletion-only, no comment-only)": [k for k in range(100) if not trivial[k]],
    "  ... and modified (not new)": [k for k in range(100) if not trivial[k] and F[k]["status"] == "modified"],
    "src/ only": [k for k, f in enumerate(F) if f["top"] == "src"],
    "not test/example": [k for k, f in enumerate(F) if not f["test_or_example"]],
    "LOGIC domain": [k for k, f in enumerate(F) if f["domain"] == "LOGIC"],
}
for name, idx in strata.items():
    row = []
    for key in ("jev0", "jev3", "laya1", "claude"):
        r = sub_auc(idx, S[key])
        row.append(f"{key} {r[0]:.3f}±{r[1]:.3f}" if r else f"{key} n/a")
    r = sub_auc(idx, S["jev0"])
    print(f"  {name:<62} R {r[2]:>2} A {r[3]:>2}  " + "  ".join(row))

# Stratified AUC: only comparisons within the same stratum (status x header)
def strat_auc(s, key):
    num = den = 0.0
    for g in set(key):
        P = [s[k] for k in range(100) if key[k] == g and y[k]]
        N = [s[k] for k in range(100) if key[k] == g and not y[k]]
        num += sum((p > q) + 0.5 * (p == q) for p in P for q in N)
        den += len(P) * len(N)
    return num / den, den
print("\n  stratified AUC (comparisons only within a stratum):")
for name, key in (("status (new/modified/deletion)", [("del" if f["status"] in ("deleted", "deletion-only") else f["status"]) for f in F]),
                  ("trivial vs not", trivial),
                  ("status x header", [(f["status"] if f["status"] in ("new", "modified") else "del", f["header"]) for f in F]),
                  ("trivial x new x header", [(trivial[k], F[k]["status"] == "new", F[k]["header"]) for k in range(100)])):
    out = []
    for kname in ("jev0", "jev3", "laya1", "claude"):
        a, den = strat_auc(S[kname], key)
        out.append(f"{kname} {a:.3f}")
    print(f"    {name:<32} ({int(den)} comparisons of 2500)  " + "  ".join(out))

print("\n== Part 2c: adjusting for the features")
def lg(x):
    return math.log1p(x)
cov_names = ["new", "del/deletion-only", "comment-only", "header", "test/example", "log1p added", "log1p removed",
             "log patch chars", "extensions/", "enriched", "year"]
X = [[float(f["status"] == "new"), float(f["status"] in ("deleted", "deletion-only")), float(f["comment_only"]),
      float(f["header"]), float(f["test_or_example"]), lg(f["added"]), lg(f["removed"]),
      math.log(f["patch_chars"]), float(f["extensions_dir"]), float(f["enriched"]), DATE[k]] for k, f in enumerate(F)]
Xs = standardize_cols(X)
yy = [float(t) for t in y]

# (i) OLS of Jev p on the features: how much of Jev's p do they explain; AUC of the residual
for key in ("jev0", "jev3", "claude", "laya1"):
    beta, res, fit = ols(Xs, S[key])
    ss_tot = sum((v - mean(S[key])) ** 2 for v in S[key])
    r2 = 1 - sum(r * r for r in res) / ss_tot
    print(f"  {key}: R^2 on the 11 features {r2:.3f}; AUC of the features' fitted {key} {auc(fit, y):.3f}; "
          f"AUC of the residual {auc(res, y):.3f} ± {delong_single(res, y)[1]:.3f}")
beta, res, fit = ols(Xs, S["jev0"])
print("    OLS coefficients of Jev p (standardised features): " + ", ".join(f"{n} {b:+.3f}" for n, b in zip(cov_names, beta[1:])))

# (ii) logistic: label ~ features (ridge) vs label ~ features + Jev; likelihood ratio and leave-one-pair-out AUC
def logit_jev(key, ridge):
    lp = [math.log(max(1e-4, min(1 - 1e-4, v)) / (1 - max(1e-4, min(1 - 1e-4, v)))) for v in S[key]]
    lps = standardize_cols([[v] for v in lp])
    Xf = Xs
    Xj = [r + j for r, j in zip(Xs, lps)]
    b0, ll0, _ = logit_fit(Xf, yy, ridge)
    b1, ll1, cov1 = logit_fit(Xj, yy, ridge)
    lr = 2 * (ll1 - ll0)
    z = b1[-1] / math.sqrt(cov1[-1][-1])
    # leave one pair out
    cv0, cv1 = [0.0] * 100, [0.0] * 100
    for p in range(50):
        tr = [k for k in range(100) if k // 2 != p]
        te = [2 * p, 2 * p + 1]
        c0, _, _ = logit_fit([Xf[k] for k in tr], [yy[k] for k in tr], ridge)
        c1, _, _ = logit_fit([Xj[k] for k in tr], [yy[k] for k in tr], ridge)
        for k in te:
            cv0[k] = logit_predict(c0, [Xf[k]])[0]
            cv1[k] = logit_predict(c1, [Xj[k]])[0]
    return lr, chi2_sf_1(lr), b1[-1], z, auc(cv0, y), auc(cv1, y), cv0, cv1

for key in ("jev0", "jev3", "claude", "laya1"):
    for ridge in (1.0,):
        lr, p, b, z, a0, a1, cv0, cv1 = logit_jev(key, ridge)
        d = delong_paired(cv1, cv0, y)
        print(f"  label ~ 11 features (+ {key}), ridge {ridge}: {key} coefficient {b:+.3f} (z {z:.2f}); LR {lr:.2f}, p {p:.4f}; "
              f"leave-one-pair-out AUC features {a0:.3f} -> features+{key} {a1:.3f} (diff {d[0]:+.3f} ± {d[1]:.3f})")

# (iii) the subset without the trivially safe changes, size-adjusted
idx = [k for k in range(100) if not trivial[k]]
print(f"\n  without deletion-only and comment-only changes ({sum(y[k] for k in idx)} R, {len(idx) - sum(y[k] for k in idx)} A):")
for key in ("jev0", "jev3", "claude", "laya1"):
    a, se = delong_single([S[key][k] for k in idx], [y[k] for k in idx])
    print(f"    {key}: AUC {a:.3f} ± {se:.3f}, one-sided p vs 0.5 {norm_sf((a - 0.5) / se):.4f}")
for name in ("new file", "added lines", "added share a/(a+r)", "hunks", "addition-only (no removed line)", "header (.h/.hpp)", "patch chars"):
    v = [float(t) for t in feat[name]]
    print(f"    feature {name:<32} AUC {auc([v[k] for k in idx], [y[k] for k in idx]):.3f}; Spearman with Jev {spearman([v[k] for k in idx], [J[k] for k in idx]):+.2f}")
