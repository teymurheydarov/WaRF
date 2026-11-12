"""Score run_gismo.py's answers against the generic checks of run_narrow.py (development, ../DEV.md 2026-11-09).

Same measures as score_narrow.py: AUC, AUC within thirds of added-line count, and LOO AUC of a logistic
model log(added+1) + score. The G+Smo checks were written from these items' defect descriptions, so
their numbers here are in-sample.

    python .warf-experiments/real-set/jev-narrow/score_gismo.py      # writes score_gismo.log"""
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


def load(name):
    whole, hunk = {}, {}
    for l in (HERE / name).open(encoding="utf-8"):
        r = json.loads(l)
        p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
        (whole.__setitem__(r["id"], p) if r["state"] == "whole" else hunk.setdefault(r["id"], []).append(p))
    assert set(whole) == set(ids), f"{name}: whole-change answers missing"
    return whole, hunk


def lg(p):
    p = min(0.99, max(0.01, p)); return math.log(p / (1 - p))


def added(c):
    return sum(1 for ln in c.splitlines() if ln.startswith("+") and not ln.startswith("+++"))


gw, gh = load("answers.jsonl")
sw, sh = load("answers_gismo.jsonl")
GEN = [q for q in next(iter(gw.values())) if q != "verdict"]
GIS = [q for q in next(iter(sw.values())) if q != "verdict"]


def hmax(w, h, i, q):
    return max((x[q] for x in h.get(i, [])), default=w[i][q])


def meanlg(w, h, qs, i):
    return sum(lg(hmax(w, h, i, q)) for q in qs) / len(qs)


A = {i: added(items[i]["code"]) for i in ids}


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
        M = [row[:] + [gv] for row, gv in zip(H, g)]
        for c in range(k):
            piv = max(range(c, k), key=lambda r: abs(M[r][c])); M[c], M[piv] = M[piv], M[c]
            for r in range(k):
                if r != c and M[c][c]:
                    f = M[r][c] / M[c][c]; M[r] = [u - f * v for u, v in zip(M[r], M[c])]
        w = [a + M[c][k] / M[c][c] for c, a in enumerate(w)]
    return w


def loo(feats):
    X = {i: [1.0] + [f(i) for f in feats] for i in ids}; pred = {}
    for i in ids:
        rest = [j for j in ids if j != i]
        w = fit([X[j] for j in rest], [int(D[j]) for j in rest])
        pred[i] = sum(a * b for a, b in zip(w, X[i]))
    return auc(pred)[0]


S = {"verdict, whole (generic run)": {i: gw[i]["verdict"] for i in ids},
     "verdict, whole (G+Smo run)": {i: sw[i]["verdict"] for i in ids},
     "generic 7, hunks, mean logit (frozen N)": {i: meanlg(gw, gh, GEN, i) for i in ids},
     "G+Smo 10, whole, mean logit": {i: sum(lg(sw[i][q]) for q in GIS) / len(GIS) for i in ids},
     "G+Smo 10, hunks, mean logit": {i: meanlg(sw, sh, GIS, i) for i in ids},
     "G+Smo 10, hunks, max": {i: max(hmax(sw, sh, i, q) for q in GIS) for i in ids},
     "all 17, hunks, mean logit": {i: (7 * meanlg(gw, gh, GEN, i) + 10 * meanlg(sw, sh, GIS, i)) / 17 for i in ids}}
for q in GIS:
    S[f"  check '{q}', hunks max"] = {i: hmax(sw, sh, i, q) for i in ids}

size = lambda i: math.log(A[i] + 1)
say(f"132 items; thirds at {cuts}; added-lines AUC {auc(A)[0]:.3f}; LOO size-only {loo([size]):.3f}")
say(f"{'score':<42} {'AUC':>6} {'within':>7} {'LOO size+score':>15}")
for name, s in S.items():
    t = (lambda s: (lambda i: lg(s[i]) if 0 <= s[i] <= 1 else s[i]))(s)
    say(f"{name:<42} {auc(s)[0]:6.3f} {within(s):7.3f} {loo([size, t]):15.3f}")
# which defects does each check flag (hunk max >= 0.5)?
say("\ncheck hits at p >= 0.5 (hunk max): defective / clean")
for q in GIS:
    say(f"  {q:<10} {sum(hmax(sw, sh, i, q) >= .5 for i in ids if D[i]):3d} / {sum(hmax(sw, sh, i, q) >= .5 for i in ids if not D[i]):3d}")
(HERE / "score_gismo.log").write_text("\n".join(out) + "\n", encoding="utf-8")
