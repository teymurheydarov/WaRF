"""Independent re-check of the 'theory' audit (something-wrong/expectation) on the 100 gismo6 commits.
Stored data only, pure Python. Written from scratch; does not import the audited script.

    python -B .warf-experiments/something-wrong/verify-theory/verify.py
"""
import json
import math
import random
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
N = NormalDist()
SEATS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")


def rows(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


sel = rows(EXP / "laya-five" / "selection.jsonl")
ids = [s["id"] for s in sel]
lab = {s["id"]: s["label"] for s in sel}
y = [lab[i] == "REJECT" for i in ids]

# ---------- alignment checks, done independently --------------------------------------------
print("== alignment")
print("n", len(ids), "distinct ids", len(set(ids)), "distinct commits", len({s["commit"] for s in sel}),
      "REJECT", sum(y))
pairs_ok = all(y[2 * k] and not y[2 * k + 1] for k in range(50))
print("rows alternate REJECT,APPROVE:", pairs_ok)

# Claude score: straight from the Claude result file, not from selection.jsonl
res = json.loads((EXP / "laya-near-chance" / "laya-probe" / "claude_review_result.json").read_text(encoding="utf-8"))
cl = {}
for b in res["reviews"]:
    for it in b["items"]:
        assert it["id"] not in cl
        cl[it["id"]] = it["p_defect"]
key = {k["id"]: k for k in json.loads((EXP / "laya-near-chance" / "claude-review" / "key.json").read_text(encoding="utf-8"))}
mism = [i for i in ids if abs(cl[i] - next(s for s in sel if s["id"] == i)["p_claude"]) > 1e-12]
print("claude p in selection == claude_review_result:", not mism, "| key labels agree:",
      all(key[i]["label"] == lab[i] and key[i]["commit"] == next(s for s in sel if s["id"] == i)["commit"] for i in ids))
batches = {}
for b in res["reviews"]:
    for it in b["items"]:
        batches[it["id"]] = b["batch"]
print("claude batches among the 100:", sorted({batches[i] for i in ids}),
      "counts", {b: sum(batches[i] == b for i in ids) for b in sorted({batches[i] for i in ids})})


def by_id(path, keyname):
    d = {}
    for r in rows(path):
        i = r[keyname]["id"]
        assert i not in d, ("dup", path, i)
        d[i] = r
    return d


one = by_id(EXP / "jev-five" / "sessions_one.jsonl", "jev")
five = by_id(EXP / "jev-five" / "sessions_five.jsonl", "jev")
rA = by_id(EXP / "jev-five" / "verify" / "refute" / "rerun_A.jsonl", "jev")
rB = by_id(EXP / "jev-five" / "verify" / "refute" / "rerun_B.jsonl", "jev")
lf = by_id(EXP / "laya-five" / "sessions.jsonl", "five")
feat = {r["id"]: r for r in rows(EXP / "jev-five" / "verify" / "refute" / "features.jsonl")}
for name, d, k in (("one", one, "jev"), ("five", five, "jev"), ("rerunA", rA, "jev"), ("rerunB", rB, "jev"),
                   ("laya5", lf, "five")):
    bad = [i for i in ids if i not in d or d[i][k]["label"] != lab[i]
           or d[i]["artifact"] != next(s for s in sel if s["id"] == i)["commit"] + ":" + next(s for s in sel if s["id"] == i)["file"]]
    extra = set(d) - set(ids)
    plant = [i for i in ids if d[i][k].get("plant")]
    print(f"  {name:7s} n={len(d)} missing/mislabelled/wrong artifact={len(bad)} extra={len(extra)} planted={len(plant)}")
print("  features: missing/mislabelled", sum(1 for i in ids if i not in feat or feat[i]["label"] != lab[i]))

# votes vs round1 p: is the stored p the one that drove WaRF's vote? (parse sanity)
inc = 0
for i in ids:
    r = five[i]
    for v in r["votes"]:
        p = r["jev"]["round1"][v["agent"]]["p_reject"]
        txt = v["reasoning"]
        pr = float(txt.split("p(REJECT)=")[1].split()[0])
        if abs(pr - p) > 0.0051 or (v["vote"] == -1) != (p > 0.5):
            inc += 1; print("   inconsistent", i, v["agent"], p, v["vote"], txt[:40])
print("  five: round1 p vs vote reasoning/vote inconsistencies:", inc)
nseat = [len(five[i]["votes"]) for i in ids]
print("  five: votes per session min/max", min(nseat), max(nseat))


def lg(p):
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


S = {}
S["claude"] = [cl[i] for i in ids]
S["jev"] = [one[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids]
S["jevA"] = [rA[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids]
S["jevB"] = [rB[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids]
for a in SEATS:
    S["J_" + a] = [five[i]["jev"]["round1"][a]["p_reject"] for i in ids]
    S["L_" + a] = [lf[i]["five"]["round1"][a]["p_reject"] for i in ids]
S["jev5"] = [sum(S["J_" + a][k] for a in SEATS) / 5 for k in range(100)]
S["laya"] = [next(s for s in sel if s["id"] == i)["p_single_laya"] for i in ids]
S["added"] = [feat[i]["added"] for i in ids]
Lg = {k: [lg(v) for v in vs] for k, vs in S.items() if k != "added"}
Lg["log_added"] = [math.log1p(a) for a in S["added"]]
Lg["jev5_meanlogit"] = [sum(Lg["J_" + a][k] for a in SEATS) / 5 for k in range(100)]


def auc(s, idx=None):
    idx = range(len(s)) if idx is None else idx
    P = [s[i] for i in idx if y[i]]
    Q = [s[i] for i in idx if not y[i]]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in Q) / (len(P) * len(Q))


def mean(a):
    return sum(a) / len(a)


def dpa(a):
    return math.sqrt(2) * N.inv_cdf(a)


def dparam(x):
    a = [v for v, t in zip(x, y) if t]
    b = [v for v, t in zip(x, y) if not t]
    va = sum((v - mean(a)) ** 2 for v in a) / (len(a) - 1)
    vb = sum((v - mean(b)) ** 2 for v in b) / (len(b) - 1)
    return (mean(a) - mean(b)) / math.sqrt((va + vb) / 2)


def resid(x, idx=None):
    idx = list(range(100)) if idx is None else idx
    mp = mean([x[i] for i in idx if y[i]])
    mn = mean([x[i] for i in idx if not y[i]])
    return [x[i] - (mp if y[i] else mn) for i in idx]


def corr(a, b):
    ma, mb = mean(a), mean(b)
    sab = sum((u - ma) * (v - mb) for u, v in zip(a, b))
    return sab / math.sqrt(sum((u - ma) ** 2 for u in a) * sum((v - mb) ** 2 for v in b))


def wcorr(x1, x2, idx=None):
    return corr(resid(x1, idx), resid(x2, idx))


def ranks(x):
    o = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and x[o[j + 1]] == x[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def wspear(x1, x2):  # within-label Spearman: rank within each label separately
    out1, out2 = [], []
    for t in (True, False):
        idx = [i for i in range(100) if y[i] == t]
        r1 = ranks([x1[i] for i in idx])
        r2 = ranks([x2[i] for i in idx])
        m1, m2 = mean(r1), mean(r2)
        out1 += [v - m1 for v in r1]
        out2 += [v - m2 for v in r2]
    return corr(out1, out2)


def pw(s):
    return sum((s[2 * k] > s[2 * k + 1]) + 0.5 * (s[2 * k] == s[2 * k + 1]) for k in range(50))


print("\n== AUCs (d' from AUC / parametric on logits), pairs won")
for k in ("claude", "jev", "jevA", "jevB", "jev5", "jev5_meanlogit", *("J_" + a for a in SEATS), "laya", "log_added"):
    x = Lg[k] if k in Lg else S[k]
    print(f"  {k:16s} AUC {auc(x):.3f}  d'(AUC) {dpa(auc(x)):.3f}  d'(param) {dparam(x):.3f}  pairs {pw(x)}")
print("  distinct values: claude", len(set(S["claude"])), " jev", len(set(S["jev"])),
      " ties in claude AUC pairs:", sum(1 for i in range(100) if y[i] for j in range(100) if not y[j] and S["claude"][i] == S["claude"][j]))

print("\n== within-label correlation of five Jev seats (Pearson on logits | Spearman)")
rs, rsp = [], []
for i, a in enumerate(SEATS):
    line = []
    for j, b in enumerate(SEATS):
        r = wcorr(Lg["J_" + a], Lg["J_" + b])
        sp = wspear(S["J_" + a], S["J_" + b])
        line.append(f"{r:.2f}|{sp:.2f}")
        if i < j:
            rs.append(r)
            rsp.append(sp)
    print("  ", " ".join(line), a)
rbar, rbars = mean(rs), mean(rsp)
neff = 5 / (1 + 4 * rbar)
dseat = mean([dpa(auc(Lg["J_" + a])) for a in SEATS])
dseat_p = mean([dparam(Lg["J_" + a]) for a in SEATS])
print(f"  mean r {rbar:.3f} (range {min(rs):.2f}..{max(rs):.2f}), Spearman mean {rbars:.3f}; n_eff {neff:.3f}")
print(f"  mean seat d' {dseat:.3f} (param {dseat_p:.3f}); predicted panel AUC {N.cdf(dseat * math.sqrt(neff) / math.sqrt(2)):.3f};"
      f" observed mean p {auc(S['jev5']):.3f}, mean logit {auc(Lg['jev5_meanlogit']):.3f}")
print(f"  5 independent seats {N.cdf(dseat * math.sqrt(5) / math.sqrt(2)):.3f}; infinite at r {N.cdf(dseat / math.sqrt(2 * rbar)):.3f}")
# WaRF's own combiner, as stored
lam5 = [-five[i]["sprt_lambda"] for i in ids]
ns5 = [-(five[i]["normalised_score"] or 0.0) for i in ids]; print("  normalised_score None:", sum(five[i]["normalised_score"] is None for i in ids))
lam5d = [-(five[i].get("debate") or five[i])["sprt_lambda"] for i in ids]; print("  no debate:", sum("debate" not in five[i] for i in ids))
print(f"  WaRF five-seat -Lambda AUC {auc(lam5):.3f}, after debate {auc(lam5d):.3f}, -normalised_score {auc(ns5):.3f};"
      f" vote count AUC {auc([sum(v['vote'] == -1 for v in five[i]['votes']) for i in ids]):.3f}")
print(f"  one-Jev -Lambda AUC {auc([-one[i]['sprt_lambda'] for i in ids]):.3f}")

print("\n== Claude target")
dC = dpa(auc(S["claude"]))
dCp = dparam(Lg["claude"])
for nm, d in (("seat d'(AUC)", dseat), ("seat d'(param)", dseat_p), ("one-Jev d'(AUC)", dpa(auc(S["jev"])))):
    dd = dC if "param" not in nm else dCp
    ne = (dd / d) ** 2
    r_need = (5 / ne - 1) / 4
    print(f"  {nm:16s} n_eff needed {ne:.2f} -> r needed {r_need:+.3f}")
# bootstrap within label (resample REJECTs and APPROVEs separately)
rng = random.Random(7)
P_idx = [i for i in range(100) if y[i]]
Q_idx = [i for i in range(100) if not y[i]]
bs = []
for _ in range(1000):
    idx = [rng.choice(P_idx) for _ in P_idx] + [rng.choice(Q_idx) for _ in Q_idx]
    rr = mean([wcorr(Lg["J_" + a], Lg["J_" + b], idx) for ii, a in enumerate(SEATS) for b in SEATS[ii + 1:]])
    bs.append(rr)
bs.sort()
print(f"  bootstrap r: 2.5% {bs[25]:.3f} 97.5% {bs[974]:.3f}")
# pair bootstrap of AUC difference Claude - jev5
rng = random.Random(11)
diffs = []
for _ in range(2000):
    ks = [rng.randrange(50) for _ in range(50)]
    idx = [i for k in ks for i in (2 * k, 2 * k + 1)]
    diffs.append(auc(S["claude"], idx) - auc(S["jev5"], idx))
diffs.sort()
print(f"  Claude - jev5 AUC {auc(S['claude']) - auc(S['jev5']):+.3f} [{diffs[50]:+.3f}, {diffs[1949]:+.3f}]")

print("\n== two-member theory")


def two(a, b):
    d1, d2 = dparam(Lg[a]), dparam(Lg[b])
    r = wcorr(Lg[a], Lg[b])
    if d2 > d1:
        d1, d2 = d2, d1
    dopt = math.sqrt(d1 ** 2 + (d2 - r * d1) ** 2 / (1 - r ** 2))
    deq = (d1 + d2) / math.sqrt(2 * (1 + r))
    thr = d1 * (math.sqrt(2 * (1 + r)) - 1)
    return d1, d2, r, N.cdf(dopt / math.sqrt(2)), N.cdf(deq / math.sqrt(2)), thr


for a, b in (("claude", "jev"), ("claude", "jev5_meanlogit"), ("claude", "laya"), ("claude", "log_added"),
             ("jev", "laya"), ("J_ADVOCATE", "J_AUDITOR")):
    d1, d2, r, ao, ae, thr = two(a, b)
    print(f"  {a}+{b:15s} d1 {d1:.3f} d2 {d2:.3f} r {r:+.2f} (spearman {wspear(Lg[a], Lg[b]):+.2f})"
          f" oracle {ao:.3f} equal {ae:.3f} need d2>{thr:.3f}")


def z(x):
    m = mean(x)
    s = math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))
    return [(v - m) / s for v in x]


def zavg(keys):
    zs = [z(Lg[k]) for k in keys]
    return [mean([zz[i] for zz in zs]) for i in range(100)]


def pboot(sc, base, n=2000, seed=3):
    rng = random.Random(seed)
    d = []
    for _ in range(n):
        ks = [rng.randrange(50) for _ in range(50)]
        idx = [i for k in ks for i in (2 * k, 2 * k + 1)]
        d.append(auc(sc, idx) - auc(base, idx))
    d.sort()
    return auc(sc) - auc(base), d[int(0.025 * n)], d[int(0.975 * n) - 1], sum(v > 0 for v in d) / n


print("\n== equal-weight z averages (no fitting) vs Claude")
for ks in (["claude", "jev"], ["claude", "laya"], ["claude", "log_added"], ["claude", "laya", "log_added"],
           ["claude", "jev", "laya", "log_added"], ["claude", *("J_" + a for a in SEATS)], ["jev", "laya"]):
    sc = zavg(ks)
    dd, lo, hi, pp = pboot(sc, S["claude"])
    print(f"  {'+'.join(ks):55s} {auc(sc):.3f}  {dd:+.3f} [{lo:+.3f}, {hi:+.3f}] P>0 {pp:.2f}")


# ---------- pure-Python ridge logistic regression, LOPO ---------------------------------------
def solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def fit(X, t, lam):
    k = len(X[0])
    w = [0.0] * (k + 1)
    for _ in range(30):
        g = [0.0] * (k + 1)
        H = [[0.0] * (k + 1) for _ in range(k + 1)]
        for x, tt in zip(X, t):
            xx = [1.0] + x
            e = w[0] + sum(a * b for a, b in zip(w[1:], x))
            p = 1 / (1 + math.exp(-e))
            for i in range(k + 1):
                g[i] += (p - tt) * xx[i]
                for j in range(k + 1):
                    H[i][j] += p * (1 - p) * xx[i] * xx[j]
        for i in range(1, k + 1):
            g[i] += lam * w[i]
            H[i][i] += lam
        step = solve(H, g)
        w = [a - b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-9:
            break
    return w


def lopo(keys, lam):
    cols = [Lg[k] for k in keys]
    out = [0.0] * 100
    for k in range(50):
        tr = [i for i in range(100) if i // 2 != k]
        mu = [mean([c[i] for i in tr]) for c in cols]
        sd = [math.sqrt(sum((c[i] - m) ** 2 for i in tr) / (len(tr) - 1)) for c, m in zip(cols, mu)]
        X = [[(c[i] - m) / s for c, m, s in zip(cols, mu, sd)] for i in tr]
        w = fit(X, [1.0 if y[i] else 0.0 for i in tr], lam)
        for i in (2 * k, 2 * k + 1):
            out[i] = w[0] + sum(ww * (c[i] - m) / s for ww, c, m, s in zip(w[1:], cols, mu, sd))
    return out


print("\n== LOPO ridge logistic (lam on standardized coefs)")
oof = {}
for lam in (1.0, 10.0):
    base = lopo(["claude"], lam)
    oof[("claude", lam)] = base
    print(f"  lam {lam:g}: Claude through LOPO {auc(base):.3f} (raw {auc(S['claude']):.3f}); within-pair wins {pw(base)} vs raw {pw(S['claude'])}")
    for ks in (["claude", "jev"], ["claude", "jev5_meanlogit"], ["claude", "laya"], ["claude", "log_added"],
               ["claude", *("J_" + a for a in SEATS)]):
        sc = lopo(ks, lam)
        d1 = pboot(sc, S["claude"])
        d2 = pboot(sc, base)
        print(f"   {'+'.join(ks):55s} {auc(sc):.3f} vs raw {d1[0]:+.3f} [{d1[1]:+.3f},{d1[2]:+.3f}]"
              f"  vs LOPO-Claude {d2[0]:+.3f} [{d2[1]:+.3f},{d2[2]:+.3f}] P>0 {d2[3]:.2f}")

# Why is LOPO Claude below raw? within-pair order is kept (monotone map per fold), so loss is cross-fold.
base = oof[("claude", 1.0)]
print("\n== LOPO-Claude bias check: identical-rank check", ranks(base) == ranks(S["claude"]),
      "| pairs whose order flipped:", sum((base[2 * k] > base[2 * k + 1]) != (S["claude"][2 * k] > S["claude"][2 * k + 1]) for k in range(50)))
# permutation null: shuffle labels within pairs? -> pure noise feature LOPO AUC
rng = random.Random(5)
nulls = []
for _ in range(20):
    noise = [rng.gauss(0, 1) for _ in range(100)]
    Lg["_noise"] = noise
    nulls.append(auc(lopo(["_noise"], 1.0)))
print(f"  LOPO AUC of pure-noise feature, 20 draws: mean {mean(nulls):.3f} min {min(nulls):.3f} max {max(nulls):.3f}")
