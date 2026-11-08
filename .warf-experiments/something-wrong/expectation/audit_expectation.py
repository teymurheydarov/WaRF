"""Audit the expectation "a panel should beat its best member" on the 100 gismo6 commits.
Stored scores only; no model is asked. Pure Python (numpy's BLAS crashes in gs\\cf\\python.exe).

Part A: binormal arithmetic. d' of every reviewer, within-label correlation of the five Jev seats,
n_eff, the r five Jev-quality seats would need to reach Claude, and the best any weighting of
the members could do if the weights were known (d_comb^2 = d' R^-1 d).
Part B: out-of-fold search for any combination of stored scores and simple features that beats
Claude. Pure-Python ridge logistic regression, leave-one-pair-out and repeated 5-fold-by-pair CV,
bootstrap over pairs of (OOF AUC - Claude AUC).

    python -B .warf-experiments/something-wrong/expectation/audit_expectation.py
"""
import json
import math
import random
from datetime import datetime
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
JEV = EXP / "jev-five"
LAYA = EXP / "laya-five"
AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
N01 = NormalDist()
SQ2 = math.sqrt(2)


def jl(p):
    return [json.loads(line) for line in Path(p).open(encoding="utf-8")]


sel = jl(LAYA / "selection.jsonl")
ids = [s["id"] for s in sel]
y = [s["label"] == "REJECT" for s in sel]
assert all(y[2 * k] and not y[2 * k + 1] for k in range(50)), "pairs are (REJECT, APPROVE)"
pair = [i // 2 for i in range(100)]
one = {r["jev"]["id"]: r for r in jl(JEV / "sessions_one.jsonl")}
five = {r["jev"]["id"]: r for r in jl(JEV / "sessions_five.jsonl")}
lfive = {r["five"]["id"]: r for r in jl(LAYA / "sessions.jsonl")}
runA = {r["jev"]["id"]: r for r in jl(JEV / "verify" / "refute" / "rerun_A.jsonl")}
runB = {r["jev"]["id"]: r for r in jl(JEV / "verify" / "refute" / "rerun_B.jsonl")}
feat = {r["id"]: r for r in jl(JEV / "verify" / "refute" / "features.jsonl")}
assert set(ids) <= set(one) and set(ids) <= set(five) and set(ids) <= set(feat) and set(ids) <= set(lfive)
for i, s in zip(ids, sel):  # labels agree across files
    assert (one[i]["jev"]["label"] == s["label"]) and (five[i]["jev"]["label"] == s["label"]) and feat[i]["label"] == s["label"]


def logit(p):
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


def year(d):
    t = datetime.fromisoformat(d.replace("Z", "+00:00"))
    return t.year + (t.timetuple().tm_yday - 1) / 366


P = {}
P["jev"] = [one[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids]
P["jevA"] = [runA[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids]
P["jevB"] = [runB[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids]
for a in AGENTS:
    P["jev_" + a] = [five[i]["jev"]["round1"][a]["p_reject"] for i in ids]
    P["laya_" + a] = [lfive[i]["five"]["round1"][a]["p_reject"] for i in ids]
P["jev5"] = [sum(P["jev_" + a][k] for a in AGENTS) / 5 for k in range(100)]
P["laya"] = [s["p_single_laya"] for s in sel]
P["claude"] = [s["p_claude"] for s in sel]
L = {k: [logit(v) for v in vs] for k, vs in P.items()}
F = [feat[i] for i in ids]
X = dict(L)
X["log_added"] = [math.log1p(f["added"]) for f in F]
X["log_removed"] = [math.log1p(f["removed"]) for f in F]
X["log_chars"] = [math.log(f["patch_chars"]) for f in F]
X["new"] = [float(f["new_file"]) for f in F]
X["del"] = [float(f["deleted_file"] or f["deletion_only"]) for f in F]
X["comment"] = [float(f["comment_only"]) for f in F]
X["header"] = [float(f["header"]) for f in F]
X["test"] = [float(f["test_or_example"]) for f in F]
X["ext"] = [float(f["extensions_dir"]) for f in F]
X["enriched"] = [float(f["enriched"]) for f in F]
X["year"] = [year(f["commit_date"]) for f in F]
FEAT11 = ["new", "del", "comment", "header", "test", "log_added", "log_removed", "log_chars", "ext", "enriched", "year"]


# ---------------------------------------------------------------- basic statistics
def auc(score, pos=None):
    pos = y if pos is None else pos
    Pz = [s for s, t in zip(score, pos) if t]
    Nz = [s for s, t in zip(score, pos) if not t]
    return sum((p > q) + 0.5 * (p == q) for p in Pz for q in Nz) / (len(Pz) * len(Nz))


def pairs_won(score):
    return sum((score[2 * k] > score[2 * k + 1]) + 0.5 * (score[2 * k] == score[2 * k + 1]) for k in range(50))


def mean(a):
    return sum(a) / len(a)


def dprime_param(x, idx=None):
    idx = range(100) if idx is None else idx
    a = [x[i] for i in idx if y[i]]
    b = [x[i] for i in idx if not y[i]]
    ma, mb = mean(a), mean(b)
    va = sum((v - ma) ** 2 for v in a) / (len(a) - 1)
    vb = sum((v - mb) ** 2 for v in b) / (len(b) - 1)
    return (ma - mb) / math.sqrt((va + vb) / 2)


def d_from_auc(a):
    return SQ2 * N01.inv_cdf(min(max(a, 1e-6), 1 - 1e-6))


def auc_from_d(d):
    return N01.cdf(d / SQ2)


def within_corr(x1, x2, idx=None):
    """pooled within-label correlation (label means removed, pooled covariance)."""
    idx = list(range(100)) if idx is None else idx
    out = []
    for lab in (True, False):
        g = [i for i in idx if y[i] == lab]
        m1, m2 = mean([x1[i] for i in g]), mean([x2[i] for i in g])
        out.append(([x1[i] - m1 for i in g], [x2[i] - m2 for i in g]))
    sxy = sum(a * b for r1, r2 in out for a, b in zip(r1, r2))
    sxx = sum(a * a for r1, _ in out for a in r1)
    syy = sum(b * b for _, r2 in out for b in r2)
    return sxy / math.sqrt(sxx * syy)


def solve(A, b):
    """Gauss-Jordan with partial pivoting; A is small and square."""
    n = len(A)
    M = [list(map(float, A[i])) + [float(b[i])] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            raise ZeroDivisionError("singular")
        piv = M[c][c]
        M[c] = [v / piv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c] != 0.0:
                f = M[r][c]
                M[r] = [vr - f * vc for vr, vc in zip(M[r], M[c])]
    return [M[i][n] for i in range(n)]


def oracle(names, idx=None):
    """Best AUC any fixed linear weighting can reach under the binormal model, weights known:
    d_comb = sqrt(d' R^-1 d) with d the parametric d's and R the within-label correlation matrix."""
    d = [dprime_param(X[n], idx) for n in names]
    R = [[1.0 if a == b else within_corr(X[a], X[b], idx) for b in names] for a in names]
    w = solve(R, d)
    dc = math.sqrt(max(sum(a * b for a, b in zip(d, w)), 0.0))
    return dc, auc_from_d(dc)


def strat_boot_idx(rng):
    Pi = [i for i in range(100) if y[i]]
    Ni = [i for i in range(100) if not y[i]]
    return [rng.choice(Pi) for _ in Pi] + [rng.choice(Ni) for _ in Ni]


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(q * len(v))))]


out = {}
print("\n  100 commits, 50 later fixed, 50 size-matched pairs; stored scores only\n")
print("=" * 100)
print("  A. Binormal arithmetic")
print("=" * 100)
print(f"\n  {'reviewer':<22}{'AUC':>7}{'d(AUC)':>8}{'d(param)':>10}{'pairs':>7}")
for n in ["claude", "jev", "jevA", "jevB", "jev5"] + ["jev_" + a for a in AGENTS] + ["laya", "log_added"]:
    a = auc(X[n])
    print(f"  {n:<22}{a:>7.3f}{d_from_auc(a):>8.3f}{dprime_param(X[n]):>10.3f}{pairs_won(X[n]):>7.1f}")
    out.setdefault("reviewers", {})[n] = {"auc": a, "d_auc": d_from_auc(a), "d_param": dprime_param(X[n])}

seats = ["jev_" + a for a in AGENTS]
print("\n  within-label correlation of the five Jev seats (logit p, pooled over labels):")
rs = []
for i in range(5):
    row = []
    for j in range(5):
        r = within_corr(X[seats[i]], X[seats[j]]) if i != j else 1.0
        row.append(r)
        if j > i:
            rs.append(r)
    print("   " + " ".join(f"{v:6.2f}" for v in row) + f"   {AGENTS[i]}")
rbar = mean(rs)
n = 5
neff = n / (1 + (n - 1) * rbar)
d_seats_auc = mean([d_from_auc(auc(X[s])) for s in seats])
d_seats_par = mean([dprime_param(X[s]) for s in seats])
dC_auc = d_from_auc(auc(X["claude"]))
dC_par = dprime_param(X["claude"])
dJ_auc = d_from_auc(auc(X["jev"]))
print(f"\n  mean within-label r {rbar:.3f} (range {min(rs):.2f} to {max(rs):.2f}); n_eff = {neff:.3f}")
print(f"  mean seat d' {d_seats_auc:.3f} (from AUC) / {d_seats_par:.3f} (parametric)")
print(f"  predicted panel AUC Phi(d sqrt(n_eff)/sqrt2) = {auc_from_d(d_seats_auc * math.sqrt(neff)):.3f}; "
      f"observed (mean p) {auc(P['jev5']):.3f}, (mean logit) {auc([mean([X[s][k] for s in seats]) for k in range(100)]):.3f}")
print(f"  five independent Jev-quality seats (r=0): {auc_from_d(d_seats_auc * math.sqrt(5)):.3f}; "
      f"infinitely many at r={rbar:.2f}: Phi(d/sqrt(2r)) = {auc_from_d(d_seats_auc / math.sqrt(rbar)):.3f}")


def r_needed(dseat, dtarget, n=5):
    need = (dtarget / dseat) ** 2
    return need, (n / need - 1) / (n - 1)


print(f"\n  Claude d' {dC_auc:.3f} (from AUC {auc(X['claude']):.3f}) / {dC_par:.3f} parametric")
for lab, ds, dc in (("mean seat d' (AUC), Claude d' (AUC)", d_seats_auc, dC_auc),
                    ("mean seat d' (param), Claude d' (param)", d_seats_par, dC_par),
                    ("one-question Jev d' (AUC), Claude (AUC)", dJ_auc, dC_auc)):
    need, rn = r_needed(ds, dc)
    print(f"  {lab:<44} n_eff needed {need:5.2f}  -> r needed for 5 seats {rn:+.3f}"
          f"   (seats needed at the measured r: {'impossible' if 1 / rbar < need else f'{need * (1 - rbar) / (1 - need * rbar):.1f}'})")
out["seat_panel"] = {"r_within_mean": rbar, "r_pairs": rs, "n_eff": neff, "d_seat_auc": d_seats_auc, "d_seat_param": d_seats_par,
                     "d_claude_auc": dC_auc, "d_claude_param": dC_par,
                     "r_needed_auc": r_needed(d_seats_auc, dC_auc)[1], "r_needed_param": r_needed(d_seats_par, dC_par)[1]}

# bootstrap the r gap
rng = random.Random(11)
gap, rnb, rmb = [], [], []
for _ in range(1000):
    idx = strat_boot_idx(rng)
    yy = [y[i] for i in idx]
    ds = mean([d_from_auc(auc([X[s][i] for i in idx], yy)) for s in seats])
    dc = d_from_auc(auc([X["claude"][i] for i in idx], yy))
    rr = mean([within_corr(X[seats[a]], X[seats[b]], idx) for a in range(5) for b in range(a + 1, 5)])
    if ds <= 0:
        rn = float("-inf")
    else:
        rn = r_needed(ds, dc)[1]
    rnb.append(rn)
    rmb.append(rr)
    gap.append(rr - rn)
print(f"  bootstrap (1000, within label): measured r {pct(rmb, .025):.3f} to {pct(rmb, .975):.3f}; "
      f"r needed {pct(rnb, .025):+.3f} to {pct(rnb, .975):+.3f}; "
      f"share of resamples where measured r <= needed r: {sum(g <= 0 for g in gap) / len(gap):.3f}")
out["seat_panel"]["boot_share_r_ok"] = sum(g <= 0 for g in gap) / len(gap)

print("\n  Two-member theory (equal-variance binormal): optimal weights give")
print("  d_comb^2 = d_best^2 + (d_other - r d_best)^2 / (1 - r^2); equal weights give (d1+d2)/sqrt(2(1+r)).")
print(f"  {'pair':<26}{'d1':>7}{'d2':>7}{'r':>7}{'oracle AUC':>12}{'equal-wt AUC':>14}{'equal beats best if d2 >':>26}")
for a, b in (("claude", "jev"), ("claude", "jev5"), ("claude", "laya"), ("claude", "log_added"), ("jev", "log_added"), ("jev", "laya"), ("jev_ADVOCATE", "jev_AUDITOR")):
    d1, d2 = dprime_param(X[a]), dprime_param(X[b])
    r = within_corr(X[a], X[b])
    hi, lo = max(d1, d2), min(d1, d2)
    orc = math.sqrt(hi ** 2 + (lo - r * hi) ** 2 / (1 - r ** 2))
    eq = (d1 + d2) / math.sqrt(2 * (1 + r))
    print(f"  {a + ' + ' + b:<26}{d1:>7.3f}{d2:>7.3f}{r:>7.2f}{auc_from_d(orc):>12.3f}{auc_from_d(eq):>14.3f}"
          f"{hi * (math.sqrt(2 * (1 + r)) - 1):>20.3f} (has {lo:.3f})")

print("\n  Many members, oracle weights (in-sample, an UPPER bound; binormal, parametric d'):")
SETS = [["claude"], ["claude", "jev"], ["claude", "laya"], ["claude", "log_added"], ["claude", "jev", "laya"],
        ["claude", "jev", "laya", "log_added"], ["claude"] + seats, ["claude", "jev", "laya", "log_added", "comment", "del"],
        ["claude"] + FEAT11, ["claude", "jev", "laya"] + FEAT11, seats, ["jev", "laya", "log_added"], FEAT11]
for s in SETS:
    dc, a = oracle(s)
    print(f"  {' + '.join(s) if len(s) < 8 else s[0] + ' + ' + str(len(s) - 1) + ' more':<60} d {dc:.3f}  AUC {a:.3f}")
    out.setdefault("oracle", {})["+".join(s)] = a


# ---------------------------------------------------------------- B. out-of-fold
def fit_lr(rows, ys, lam):
    """ridge logistic regression (intercept unpenalised), Newton. rows: list of feature lists."""
    k = len(rows[0])
    w = [0.0] * (k + 1)
    for _ in range(50):
        g = [0.0] * (k + 1)
        H = [[0.0] * (k + 1) for _ in range(k + 1)]
        for xr, t in zip(rows, ys):
            z = w[0] + sum(a * b for a, b in zip(w[1:], xr))
            p = 1 / (1 + math.exp(-max(min(z, 30), -30)))
            xv = [1.0] + xr
            e = p - t
            s = p * (1 - p)
            for i in range(k + 1):
                g[i] += e * xv[i]
                for j in range(i, k + 1):
                    H[i][j] += s * xv[i] * xv[j]
        for i in range(k + 1):
            for j in range(i):
                H[i][j] = H[j][i]
        for i in range(1, k + 1):
            g[i] += lam * w[i]
            H[i][i] += lam
        step = solve(H, g)
        w = [a - b for a, b in zip(w, step)]
        if max(abs(v) for v in step) < 1e-8:
            break
    return w


def standardise(train_idx, cols):
    mus, sds = [], []
    for c in cols:
        v = [X[c][i] for i in train_idx]
        m = mean(v)
        sd = math.sqrt(sum((a - m) ** 2 for a in v) / len(v)) or 1.0
        mus.append(m)
        sds.append(sd)
    return mus, sds


def oof(cols, lam, folds):
    pred = [None] * 100
    for test in folds:
        ts = set(test)
        train = [i for i in range(100) if i not in ts]
        mus, sds = standardise(train, cols)
        row = lambda i: [(X[c][i] - m) / s for c, m, s in zip(cols, mus, sds)]
        w = fit_lr([row(i) for i in train], [float(y[i]) for i in train], lam)
        for i in test:
            pred[i] = w[0] + sum(a * b for a, b in zip(w[1:], row(i)))
    return pred


LOPO = [[2 * k, 2 * k + 1] for k in range(50)]


def kfold_pairs(seed, k=5):
    ps = list(range(50))
    random.Random(seed).shuffle(ps)
    return [[i for p in ps[f::k] for i in (2 * p, 2 * p + 1)] for f in range(k)]


def pair_boot(score, ref, B=2000, seed=7):
    rng = random.Random(seed)
    d = []
    for _ in range(B):
        ks = [rng.randrange(50) for _ in range(50)]
        idx = [i for k in ks for i in (2 * k, 2 * k + 1)]
        yy = [y[i] for i in idx]
        d.append(auc([score[i] for i in idx], yy) - auc([ref[i] for i in idx], yy))
    return pct(d, .025), pct(d, .975), sum(v > 0 for v in d) / B


print("\n" + "=" * 100)
print("  B. Out of fold: can anything stored beat Claude (raw AUC %.3f, %.1f of 50 pairs)?" % (auc(X["claude"]), pairs_won(X["claude"])))
print("=" * 100)
COMBOS = [
    ["claude"], ["jev"], ["log_added"], ["claude", "jev"], ["claude", "jev5"], ["claude", "laya"], ["claude", "log_added"],
    ["claude", "jev", "laya"], ["claude", "jev", "laya", "log_added"], ["claude", "log_added", "comment", "del"],
    ["claude", "jev", "log_added", "comment", "del"], ["claude", "jev", "laya", "log_added", "comment", "del"],
    ["claude"] + seats, ["claude", "laya"] + seats, ["jev", "laya"], ["jev", "laya", "log_added"], ["jev", "log_added"],
    FEAT11, ["claude"] + FEAT11, ["jev"] + FEAT11, ["claude", "jev", "laya"] + FEAT11,
    ["claude", "jev", "laya", "jevA", "jevB"] + seats + ["laya_" + a for a in AGENTS] + FEAT11,
]
print(f"\n  {'combination':<52}{'lam':>5}{'LOPO AUC':>10}{'pairs':>7}{'5fold x20':>14}{'minus Claude [95% pair-boot]':>34}{'P(>0)':>7}")
best = []
for cols in COMBOS:
    for lam in (1.0, 10.0):
        pr = oof(cols, lam, LOPO)
        a = auc(pr)
        kf = [auc(oof(cols, lam, kfold_pairs(s))) for s in range(20)]
        lo, hi, pp = pair_boot(pr, X["claude"])
        lo2, hi2, pp2 = pair_boot(pr, oof(["claude"], lam, LOPO))
        hide = set(seats) | {"laya_" + a for a in AGENTS} | (set(FEAT11) if FEAT11[0] in cols else set())
        name = " + ".join(c for c in cols if c not in hide)
        if any(c in seats for c in cols):
            name += " + 5 Jev seats"
        if any(c.startswith("laya_") for c in cols):
            name += " + 5 Laya seats"
        if FEAT11[0] in cols:
            name = (name + " + " if name else "") + "11 features"
        oof_claude = auc(oof(["claude"], lam, LOPO))
        name += f"  [Claude via same CV {oof_claude:.3f}]" if cols == ["claude"] else ""
        print(f"  {name:<52}{lam:>5.0f}{a:>10.3f}{pairs_won(pr):>7.1f}{mean(kf):>8.3f}±{math.sqrt(sum((v - mean(kf)) ** 2 for v in kf) / 19):.3f}"
              f"{a - auc(X['claude']):>+12.3f} [{lo:+.3f}, {hi:+.3f}]{pp:>7.2f}"
              f"   vs Claude-OOF {a - oof_claude:+.3f} [{lo2:+.3f}, {hi2:+.3f}]")
        out.setdefault("oof", []).append({"name": name, "cols": cols, "lam": lam, "lopo_auc": a, "kfold_mean": mean(kf),
                                          "minus_claude": a - auc(X["claude"]), "ci": [lo, hi], "p_gt0": pp,
                                          "minus_claude_oof": a - oof_claude, "ci_oof": [lo2, hi2]})
        best.append((a, name, lam))

print("\n  No fitting at all: equal-weight mean of z-scored members (signs fixed a priori, unsupervised scaling)")


def zs(v):
    m = mean(v)
    sd = math.sqrt(sum((a - m) ** 2 for a in v) / len(v))
    return [(a - m) / sd for a in v]


for cols in (["claude", "jev"], ["claude", "laya"], ["claude", "log_added"], ["claude", "jev", "laya"],
             ["claude", "jev", "laya", "log_added"], ["claude", "laya", "log_added"], ["claude"] + seats, ["jev", "laya", "log_added"]):
    Z = [zs(X[c]) for c in cols]
    sc = [mean([z[k] for z in Z]) for k in range(100)]
    a = auc(sc)
    lo, hi, pp = pair_boot(sc, X["claude"])
    print(f"  {' + '.join(cols) if len(cols) < 6 else 'claude + five Jev seats':<52}{a:>15.3f}{pairs_won(sc):>7.1f}"
          f"{a - auc(X['claude']):>+26.3f} [{lo:+.3f}, {hi:+.3f}]{pp:>7.2f}")
    out.setdefault("equal_weight", []).append({"cols": cols, "auc": a, "minus_claude": a - auc(X["claude"]), "ci": [lo, hi], "p_gt0": pp})

best.sort(reverse=True)
print(f"\n  best out-of-fold: {best[0][1]} (lam {best[0][2]:.0f}) {best[0][0]:.3f}; {len(best)} fitted variants were tried, "
      "so the best one is optimistic.")
(HERE / "audit_expectation.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
