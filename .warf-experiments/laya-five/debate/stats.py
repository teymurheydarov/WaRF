"""Small pure-Python statistics kit (numpy's BLAS crashes gs\\cf\\python.exe)."""
import math
import random


def solve(A, b):
    """Gaussian elimination with partial pivoting; None when singular."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        inv = 1.0 / M[c][c]
        for r in range(c + 1, n):
            f = M[r][c] * inv
            if f:
                Mr, Mc = M[r], M[c]
                for k in range(c, n + 1):
                    Mr[k] -= f * Mc[k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = M[r][n] - sum(M[r][k] * x[k] for k in range(r + 1, n))
        x[r] = s / M[r][r]
    return x


def ols(X, y, w=None):
    """Coefficients of y on the columns of X (rows include the intercept), with optional
    integer weights w (bootstrap counts)."""
    k = len(X[0])
    XtX = [[0.0] * k for _ in range(k)]
    Xty = [0.0] * k
    for i, (row, yy) in enumerate(zip(X, y)):
        wi = 1 if w is None else w[i]
        if not wi:
            continue
        for a in range(k):
            ra = row[a] * wi
            Xty[a] += ra * yy
            XA = XtX[a]
            for b in range(a, k):
                XA[b] += ra * row[b]
    for a in range(k):
        for b in range(a):
            XtX[a][b] = XtX[b][a]
    return solve(XtX, Xty)


def counts(rng, n, units=None):
    """Bootstrap weights: multinomial counts over n rows, or over clusters `units`
    (a list of row-index lists) when given."""
    w = [0] * n
    if units is None:
        for _ in range(n):
            w[rng.randrange(n)] += 1
    else:
        for _ in range(len(units)):
            for i in units[rng.randrange(len(units))]:
                w[i] += 1
    return w


def pct(v, q):
    v = sorted(v)
    if not v:
        return float("nan")
    pos = q * (len(v) - 1)
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def auc_w(score, pos, w=None):
    """P(score of a positive > score of a negative), ties 1/2, with integer weights."""
    if w is None:
        w = [1] * len(score)
    items = sorted((s, p, wi) for s, p, wi in zip(score, pos, w) if wi)
    n1 = sum(wi for s, p, wi in items if p)
    n0 = sum(wi for s, p, wi in items if not p)
    if not n1 or not n0:
        return float("nan")
    # walk groups of equal score: positives beat the negatives below, tie with those equal
    below_neg, total = 0, 0.0
    i = 0
    while i < len(items):
        j = i
        g1 = g0 = 0
        while j < len(items) and items[j][0] == items[i][0]:
            if items[j][1]:
                g1 += items[j][2]
            else:
                g0 += items[j][2]
            j += 1
        total += g1 * (below_neg + 0.5 * g0)
        below_neg += g0
        i = j
    return total / (n1 * n0)


def hanley_mcneil(a, n1, n0):
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    return math.sqrt(max(0.0, a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n0 - 1) * (q2 - a * a)) / (n1 * n0))


def delong_paired(s1, s2, pos):
    """DeLong (1988) test for two correlated AUCs on the same cases: (auc1, auc2, diff, se, z, p)."""
    P = [i for i, t in enumerate(pos) if t]
    N = [i for i, t in enumerate(pos) if not t]
    m, n = len(P), len(N)

    def psi(x, y):
        return 1.0 if x > y else (0.5 if x == y else 0.0)

    V10 = [[sum(psi(s[i], s[j]) for j in N) / n for i in P] for s in (s1, s2)]
    V01 = [[sum(psi(s[i], s[j]) for i in P) / m for j in N] for s in (s1, s2)]
    A = [sum(v) / m for v in V10]

    def cov(u, v):
        mu, mv = sum(u) / len(u), sum(v) / len(v)
        return sum((a - mu) * (b - mv) for a, b in zip(u, v)) / (len(u) - 1)

    S10 = [[cov(V10[r], V10[c]) for c in range(2)] for r in range(2)]
    S01 = [[cov(V01[r], V01[c]) for c in range(2)] for r in range(2)]
    var = (S10[0][0] + S10[1][1] - 2 * S10[0][1]) / m + (S01[0][0] + S01[1][1] - 2 * S01[0][1]) / n
    se = math.sqrt(max(var, 0.0))
    d = A[1] - A[0]
    z = d / se if se else float("nan")
    p = math.erfc(abs(z) / math.sqrt(2)) if se else float("nan")
    return A[0], A[1], d, se, z, p


def sign_test(k, n):
    """Two-sided exact binomial p-value for k successes of n at 1/2."""
    if n == 0:
        return float("nan")
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def logit(p, eps=1e-6):
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def mean(v):
    return sum(v) / len(v)


def corr(a, b):
    ma, mb = mean(a), mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


if __name__ == "__main__":
    # self-test: the kit must recover planted values and fail if broken
    rng = random.Random(1)
    X, y = [], []
    for _ in range(500):
        a, b = rng.random(), rng.randrange(4)
        X.append([1.0, a, float(b)])
        y.append(0.3 + 0.7 * a + 0.05 * b + rng.gauss(0, 0.01))
    beta = ols(X, y)
    assert abs(beta[0] - 0.3) < 0.01 and abs(beta[1] - 0.7) < 0.01 and abs(beta[2] - 0.05) < 0.003, beta
    w = counts(rng, len(y))
    assert sum(w) == len(y)
    sc = [0.1, 0.4, 0.35, 0.8, 0.8]
    lab = [0, 0, 1, 1, 0]
    # positives 0.35, 0.8 vs negatives 0.1, 0.4, 0.8: (1+0+0) + (1+1+0.5) = 3.5 of 6
    assert abs(auc_w(sc, lab) - 3.5 / 6) < 1e-12, auc_w(sc, lab)
    assert abs(auc_w(sc, lab, [2, 1, 1, 1, 1]) - (2 + 0 + 0 + 2 + 1 + 0.5) / 8) < 1e-12
    assert abs(sign_test(0, 10) - 2 / 1024) < 1e-12 and sign_test(5, 10) == 1.0
    a1, a2, d, se, z, p = delong_paired([0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1], [0, 0, 1, 1])
    assert a1 == 1.0 and a2 == 0.0 and d == -1.0
    print("stats self-test ok", [round(b, 4) for b in beta])
