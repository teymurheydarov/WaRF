"""Lever "combine": new aggregations of Jev answers already paid for (no API calls). See README.md.

    python -B .warf-experiments/real-set/jev-narrow/combine/combine.py      # writes scores.json, combine.log

Scores (pre-registered, README.md): B_ridge_nested (primary), A_noisyor, A_top2, C_mean_plain_json."""
import json
import math
import operator
import sys
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import jevscore as J  # noqa: E402

RIDGES = [0.3, 1.0, 3.0, 10.0]
ALLQ = ["verdict"] + J.GENERIC


def clip(p):
    return min(0.99, max(0.01, p))


def hunk_vals(w, h, i, q):
    v = [x[q] for x in h.get(i, []) if q in x]
    return v if v else [w[i][q]]


def noisyor(w, h, i):
    s = 0.0
    for q in J.GENERIC:
        pi = 1.0
        for p in hunk_vals(w, h, i, q):
            pi *= 1 - clip(p)
        s += math.log((1 - pi) / pi)
    return s / len(J.GENERIC)


def top2(w, h, i):
    s = 0.0
    for q in J.GENERIC:
        v = sorted(hunk_vals(w, h, i, q), reverse=True)[:2]
        s += sum(J.lg(p) for p in v) / len(v)
    return s / len(J.GENERIC)


# ---- ridge logistic, same objective as jevscore._fit (penalty on all but the intercept), but
# ---- iterated to convergence with a warm start so the nested LOO is affordable
def solve(H, g):
    k = len(g); M = [row[:] + [gv] for row, gv in zip(H, g)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(M[r][c])); M[c], M[piv] = M[piv], M[c]
        for r in range(k):
            if r != c and M[c][c]:
                f = M[r][c] / M[c][c]
                if f:
                    M[r] = [u - f * v for u, v in zip(M[r], M[c])]
    return [M[c][k] / M[c][c] for c in range(k)]


def fit(X, y, ridge, w0=None, tol=1e-9, maxit=60):
    k = len(X[0]); w = list(w0) if w0 else [0.0] * k
    cols = [[x[a] for x in X] for a in range(k)]
    for _ in range(maxit):
        z = [sum(map(operator.mul, w, x)) for x in X]
        p = [1 / (1 + math.exp(-max(-30, min(30, t)))) for t in z]
        r = [t - q for t, q in zip(y, p)]; v = [q * (1 - q) for q in p]
        g = [sum(map(operator.mul, r, cols[a])) for a in range(k)]
        H = [[0.0] * k for _ in range(k)]
        for a in range(k):
            va = [s * c for s, c in zip(v, cols[a])]
            for b in range(a, k):
                H[a][b] = H[b][a] = sum(map(operator.mul, va, cols[b]))
        for a in range(1, k):
            g[a] -= ridge * w[a]; H[a][a] += ridge
        step = solve(H, g)
        w = [a + s for a, s in zip(w, step)]
        if max(abs(s) for s in step) < tol:
            break
    return w


def dot(w, x):
    return sum(map(operator.mul, w, x))


def auc_lists(sc, lab):
    P = [s for s, t in zip(sc, lab) if t]; N = [s for s, t in zip(sc, lab) if not t]
    return sum((a > b) + 0.5 * (a == b) for a in P for b in N) / (len(P) * len(N))


def _features():
    w, h = J.load(HERE.parent / "answers.jsonl")
    return {i: [1.0, J.size(i)] + [J.lg(w[i][q]) for q in ALLQ] + [J.lg(J.hmax(w, h, i, q)) for q in ALLQ]
            for i in J.ids}


X = _features()
Y = {i: int(J.D[i]) for i in J.ids}


def outer_fold(i):
    rest = [j for j in J.ids if j != i]
    best = None
    inner_aucs = {}
    for r in RIDGES:
        w_full = fit([X[j] for j in rest], [Y[j] for j in rest], r)
        preds = []
        for j in rest:
            sub = [m for m in rest if m != j]
            wj = fit([X[m] for m in sub], [Y[m] for m in sub], r, w0=w_full)
            preds.append(dot(wj, X[j]))
        a = auc_lists(preds, [Y[j] for j in rest]); inner_aucs[r] = a
        if best is None or a >= best[1]:          # ties go to the larger ridge (RIDGES ascending)
            best = (r, a, w_full)
    return i, dot(best[2], X[i]), best[0], inner_aucs


def nested():
    with Pool(4) as pool:
        res = pool.map(outer_fold, J.ids)
    return {i: s for i, s, _, _ in res}, {i: r for i, _, r, _ in res}, {i: a for i, _, _, a in res}


def main():
    t0 = time.time()
    out = HERE / "combine.log"; lines = []

    def say(s=""):
        print(s, flush=True); lines.append(s)

    # sanity: the converged fit must agree with jevscore._fit on the full data
    w_ref = J._fit([X[i] for i in J.ids], [Y[i] for i in J.ids], 1.0)
    w_me = fit([X[i] for i in J.ids], [Y[i] for i in J.ids], 1.0)
    say(f"fit check vs jevscore._fit (ridge 1, all 132): max |dw| = {max(abs(a - b) for a, b in zip(w_ref, w_me)):.2e}")

    w, h = J.load(HERE.parent / "answers.jsonl")
    wj, _ = J.load(HERE.parent / "answers_json.jsonl")
    ref = J.ref_N()
    njson = {i: sum(J.lg(wj[i][q]) for q in J.GENERIC) / len(J.GENERIC) for i in J.ids}
    scores = {
        "A_noisyor": {i: noisyor(w, h, i) for i in J.ids},
        "A_top2": {i: top2(w, h, i) for i in J.ids},
        "C_mean_plain_json": {i: (ref[i] + njson[i]) / 2 for i in J.ids},
    }
    bn, ridge_of, inner = nested()
    scores = {"B_ridge_nested": bn, **scores}
    common = sorted(set(w) & set(wj))
    say(f"items {len(J.ids)}; common ids answers.jsonl/answers_json.jsonl {len(common)}; "
        f"items with >1 hunk {sum(len(h.get(i, [])) > 1 for i in J.ids)}")
    rc = {r: sum(v == r for v in ridge_of.values()) for r in RIDGES}
    say(f"B: ridge chosen per outer fold {rc}")

    def quirkfree(s):  # LOO size + raw score, without loo_size's per-value lg of scores in [0, 1]
        return J.loo([J.size, lambda i: s[i]])

    say("")
    say(f"{'score':24s} {'AUC':>6s} {'within':>7s} {'LOOsz':>6s} {'LOOraw':>7s}   d vs ref_N [95% CI]")
    rows = {}
    for name, s in [("ref_N", ref), ("N_json (component)", njson)] + list(scores.items()):
        a, wi, ls, lr = J.auc(s), J.within(s), J.loo_size(s), quirkfree(s)
        d = J.boot_diff(s, ref)
        rows[name] = {"auc": a, "within": wi, "loo_size": ls, "loo_raw": lr, "d": d[0], "lo": d[1], "hi": d[2]}
        say(f"{name:24s} {a:6.3f} {wi:7.3f} {ls:6.3f} {lr:7.3f}   {d[0]:+.3f} [{d[1]:+.3f}, {d[2]:+.3f}]")
    say(f"\nPearson correlation of N_json and ref_N = "
        f"{_corr([ref[i] for i in J.ids], [njson[i] for i in J.ids]):.3f}")
    say(f"elapsed {time.time() - t0:.0f} s")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (HERE / "scores.json").write_text(json.dumps({"rows": rows, "ridge_chosen": ridge_of, "inner_auc": inner,
                                                  "scores": scores}, indent=1), encoding="utf-8")


def _corr(a, b):
    n = len(a); ma, mb = sum(a) / n, sum(b) / n
    c = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return c / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


if __name__ == "__main__":
    main()
