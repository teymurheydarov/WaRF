"""Shared scoring for the Jev development experiments (../DEV.md). Importing has no side effects.

    from jevscore import ids, D, A, load, hmax, meanlg, lg, auc, within, loo_size, boot_diff, ref_N

- ids, D, A: the 132 dev item ids, defective flag, added-line count.
- load(path) -> (whole, hunk): whole[id] = {question: p}, hunk[id] = [{question: p}, ...]; p is
  P(REJECT) for "verdict" and P(YES) for every other question.
- ref_N(): the frozen reference score N (generic 7 checks, mean logit of each check's max over hunks,
  from answers.jsonl), the score every new lever is compared with.
- auc(s), within(s) (AUC inside thirds of added lines), loo_size(s) (LOO AUC of logistic size + score),
  boot_diff(s, r) -> (d, lo, hi): AUC(s) - AUC(r) with a 95% stratified bootstrap (2000, seed 4)."""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
_items = {json.loads(l)["id"]: json.loads(l) for l in (HERE.parent / "items.jsonl").open(encoding="utf-8")}
ids = list(_items)
ITEMS = _items
D = {i: _items[i]["kind"] == "defective" for i in ids}
GENERIC = ["offbyone", "condition", "wrongvar", "missing", "memory", "interface", "compile"]


def _added(c):
    return sum(1 for ln in c.splitlines() if ln.startswith("+") and not ln.startswith("+++"))


A = {i: _added(_items[i]["code"]) for i in ids}


def load(path, require_all=True):
    whole, hunk = {}, {}
    for l in Path(path).open(encoding="utf-8"):
        r = json.loads(l)
        p = {q: ((v.get("p") or v.get("probabilities") or {}).get("REJECT" if q == "verdict" else "YES", 0.0)
                 if isinstance(v, dict) else 0.0) for q, v in (r.get("answers") or {}).items()}
        if r.get("state", "whole") == "whole":
            whole[r["id"]] = p
        else:
            hunk.setdefault(r["id"], []).append(p)
    if require_all and not set(ids) <= set(whole):
        raise SystemExit(f"{path}: {len(set(ids) - set(whole))} whole-change answers missing")
    return whole, hunk


def lg(p):
    p = min(0.99, max(0.01, p)); return math.log(p / (1 - p))


def hmax(whole, hunk, i, q):
    return max((h[q] for h in hunk.get(i, []) if q in h), default=whole[i][q])


def meanlg(whole, hunk, qs, i):
    return sum(lg(hmax(whole, hunk, i, q)) for q in qs) / len(qs)


def ref_N():
    w, h = load(HERE / "answers.jsonl")
    return {i: meanlg(w, h, GENERIC, i) for i in ids}


def auc(s, sample=None):
    sample = ids if sample is None else sample
    P = [s[i] for i in sample if D[i]]; N = [s[i] for i in sample if not D[i]]
    return sum((a > b) + 0.5 * (a == b) for a in P for b in N) / (len(P) * len(N))


_qs = sorted(A.values()); CUTS = [_qs[len(_qs) // 3], _qs[2 * len(_qs) // 3]]
BINS = [[i for i in ids if lo < A[i] <= hi] for lo, hi in ((-1, CUTS[0]), (CUTS[0], CUTS[1]), (CUTS[1], 10 ** 9))]


def within(s):
    num = den = 0
    for b in BINS:
        n = sum(D[i] for i in b) * sum(not D[i] for i in b)
        if n:
            num += auc(s, b) * n; den += n
    return num / den


def _fit(X, y, ridge=1.0):
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


def loo(feats, ridge=1.0):
    """LOO AUC of a ridge logistic model on feature functions feats (each id -> float)."""
    X = {i: [1.0] + [f(i) for f in feats] for i in ids}; pred = {}
    for i in ids:
        rest = [j for j in ids if j != i]
        w = _fit([X[j] for j in rest], [int(D[j]) for j in rest], ridge)
        pred[i] = sum(a * b for a, b in zip(w, X[i]))
    return auc(pred)


def size(i):
    return math.log(A[i] + 1)


def loo_size(s):
    """A probability score enters as its logit; any other score (a mean logit, a count) enters raw. The choice
    is made for the whole score, never per value (a mean logit of 0.4 is not a probability)."""
    prob = all(0 <= s[i] <= 1 for i in ids)
    return loo([size, (lambda i: lg(s[i])) if prob else (lambda i: s[i])])


def boot_diff(s, r, n=2000, seed=4):
    rng = random.Random(seed)
    pos = [i for i in ids if D[i]]; neg = [i for i in ids if not D[i]]
    diffs = []
    for _ in range(n):
        smp = [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]
        diffs.append(auc(s, smp) - auc(r, smp))
    diffs.sort()
    return auc(s) - auc(r), diffs[int(0.025 * n)], diffs[int(0.975 * n) - 1]
