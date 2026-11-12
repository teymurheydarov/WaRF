"""Score run_narrow.py's answers (development, ../DEV.md 2026-11-09). Stored answers only.

The measure that matters is signal beyond change size. Counting added lines alone scores AUC 0.834 on
this set, so each score is reported three ways: AUC; AUC within thirds of added-line count (pairs only
inside a third); and leave-one-out AUC of a logistic model log(added+1) + score against
log(added+1) alone.

    python .warf-experiments/real-set/jev-narrow/score_narrow.py      # writes score.log"""
import glob
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
items = {json.loads(l)["id"]: json.loads(l) for l in (HERE.parent / "items.jsonl").open(encoding="utf-8")}
ids = list(items)
D = {i: items[i]["kind"] == "defective" for i in ids}
out = []


def say(s=""):
    out.append(s); print(s)


def added(c):
    return sum(1 for ln in c.splitlines() if ln.startswith("+") and not ln.startswith("+++"))


A = {i: added(items[i]["code"]) for i in ids}
stored = {}
for f in glob.glob(str(HERE.parent / "jev.w*.jsonl")):
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        stored[r["planted"]["id"]] = r["planted"]["call"]["body"]["answers"]["verdict"]["probabilities"]["REJECT"]
whole, hunk = {}, {}
for l in (HERE / "answers.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
    (whole.__setitem__(r["id"], p) if r["state"] == "whole" else hunk.setdefault(r["id"], []).append(p))
assert set(whole) == set(ids), "whole-change answers missing"
CH = [q for q in next(iter(whole.values())) if q != "verdict"]


def lg(p):
    p = min(0.99, max(0.01, p)); return math.log(p / (1 - p))


def hmax(i, q):
    return max((h[q] for h in hunk.get(i, [])), default=whole[i][q])


S = {"stored verdict (earlier run)": {i: stored[i] for i in ids},
     "verdict, whole change (this run)": {i: whole[i]["verdict"] for i in ids},
     "verdict, max over hunks": {i: hmax(i, "verdict") for i in ids},
     "narrow checks, whole, max": {i: max(whole[i][q] for q in CH) for i in ids},
     "narrow checks, whole, mean logit": {i: sum(lg(whole[i][q]) for q in CH) / len(CH) for i in ids},
     "narrow checks, max over hunks of max": {i: max(hmax(i, q) for q in CH) for i in ids},
     "narrow checks, hunks, mean logit of hunk max": {i: sum(lg(hmax(i, q)) for q in CH) / len(CH) for i in ids}}
for q in CH:
    S[f"  check '{q}', whole"] = {i: whole[i][q] for i in ids}


def auc(s, sample=ids):
    P = [s[i] for i in sample if D[i]]; N = [s[i] for i in sample if not D[i]]
    return sum((a > b) + 0.5 * (a == b) for a in P for b in N) / (len(P) * len(N)), len(P) * len(N)


qs = sorted(A.values()); cuts = [qs[len(qs) // 3], qs[2 * len(qs) // 3]]
bins = [[i for i in ids if lo < A[i] <= hi] for lo, hi in ((-1, cuts[0]), (cuts[0], cuts[1]), (cuts[1], 10 ** 9))]


def within(s):
    num = den = 0
    for b in bins:
        a, n = auc(s, b); num += a * n; den += n
    return num / den


def fit(X, y, ridge=1.0):
    k = len(X[0]); w = [0.0] * k
    for _ in range(30):
        g = [0.0] * k; H = [[0.0] * k for _ in range(k)]
        for x, t in zip(X, y):
            z = sum(a * b for a, b in zip(w, x)); p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            for a in range(k):
                g[a] += (t - p) * x[a]
                for b in range(k):
                    H[a][b] += p * (1 - p) * x[a] * x[b]
        for a in range(1, k):
            g[a] -= ridge * w[a]; H[a][a] += ridge
        # solve H d = g
        M = [row[:] + [gv] for row, gv in zip(H, g)]
        for c in range(k):
            piv = max(range(c, k), key=lambda r: abs(M[r][c])); M[c], M[piv] = M[piv], M[c]
            for r in range(k):
                if r != c and M[c][c]:
                    f = M[r][c] / M[c][c]; M[r] = [u - f * v for u, v in zip(M[r], M[c])]
        d = [M[c][k] / M[c][c] for c in range(k)]
        w = [a + b for a, b in zip(w, d)]
    return w


def loo(feats):
    X = {i: [1.0] + [f(i) for f in feats] for i in ids}; pred = {}
    for i in ids:
        rest = [j for j in ids if j != i]
        w = fit([X[j] for j in rest], [int(D[j]) for j in rest])
        pred[i] = sum(a * b for a, b in zip(w, X[i]))
    return auc(pred)[0]


size = lambda i: math.log(A[i] + 1)
base = loo([size])
say(f"132 items; thirds of added lines at {cuts}; added-lines AUC {auc(A)[0]:.3f}; LOO size-only model {base:.3f}")
say(f"{'score':<46} {'AUC':>6} {'within':>7} {'LOO size+score':>15}")
for name, s in S.items():
    t = (lambda s: (lambda i: lg(s[i]) if 0 <= s[i] <= 1 else s[i]))(s)
    say(f"{name:<46} {auc(s)[0]:6.3f} {within(s):7.3f} {loo([size, t]):15.3f}")
allw = [(lambda q: (lambda i: lg(whole[i][q])))(q) for q in ["verdict"] + CH]
say(f"{'all 8 whole answers + size (LOO logistic)':<46} {'':6} {'':7} {loo([size] + allw):15.3f}")
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
