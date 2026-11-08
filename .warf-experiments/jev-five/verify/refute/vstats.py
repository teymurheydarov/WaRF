"""Pure-Python statistics for the Jev refutation (numpy's BLAS crashes gs\\cf\\python.exe)."""
import math
import random


def auc(score, pos):
    P = [s for s, t in zip(score, pos) if t]
    N = [s for s, t in zip(score, pos) if not t]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))


def hanley_se(a, n1, n0):
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    return math.sqrt(max(0.0, a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n0 - 1) * (q2 - a * a)) / (n1 * n0))


def _psi(p, q):
    return 1.0 if p > q else 0.5 if p == q else 0.0


def delong(scores, pos):
    """AUCs of several scores on the same items and their DeLong covariance matrix."""
    P = [i for i, t in enumerate(pos) if t]
    N = [i for i, t in enumerate(pos) if not t]
    m, n = len(P), len(N)
    k = len(scores)
    A, V10, V01 = [], [], []
    for s in scores:
        v10 = [sum(_psi(s[i], s[j]) for j in N) / n for i in P]
        v01 = [sum(_psi(s[i], s[j]) for i in P) / m for j in N]
        A.append(sum(v10) / m)
        V10.append(v10)
        V01.append(v01)
    S = [[0.0] * k for _ in range(k)]
    for r in range(k):
        for c in range(k):
            s10 = sum((V10[r][i] - A[r]) * (V10[c][i] - A[c]) for i in range(m)) / (m - 1)
            s01 = sum((V01[r][j] - A[r]) * (V01[c][j] - A[c]) for j in range(n)) / (n - 1)
            S[r][c] = s10 / m + s01 / n
    return A, S


def delong_single(score, pos):
    A, S = delong([score], pos)
    return A[0], math.sqrt(S[0][0])


def delong_paired(s1, s2, pos):
    A, S = delong([s1, s2], pos)
    d = A[0] - A[1]
    var = S[0][0] + S[1][1] - 2 * S[0][1]
    se = math.sqrt(max(var, 1e-300))
    z = d / se
    return d, se, z, 2 * norm_sf(abs(z)), S


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def norm_ppf(p):
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 1 - norm_sf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def mean(a):
    return sum(a) / len(a)


def corr(a, b):
    ma, mb = mean(a), mean(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


def ranks(a):
    order = sorted(range(len(a)), key=lambda i: a[i])
    r = [0.0] * len(a)
    i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b):
    return corr(ranks(a), ranks(b))


def solve(M, b):
    """Gauss-Jordan with partial pivoting; M is a list of rows."""
    n = len(M)
    A = [row[:] + [b[i]] for i, row in enumerate(M)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(A[r][c]))
        if abs(A[p][c]) < 1e-14:
            raise ZeroDivisionError("singular")
        A[c], A[p] = A[p], A[c]
        piv = A[c][c]
        A[c] = [x / piv for x in A[c]]
        for r in range(n):
            if r != c and A[r][c]:
                f = A[r][c]
                A[r] = [x - f * y for x, y in zip(A[r], A[c])]
    return [A[i][n] for i in range(n)]


def inverse(M):
    n = len(M)
    cols = [solve(M, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def ols(X, y):
    """X rows without intercept; returns (coef with intercept first, residuals, fitted)."""
    Z = [[1.0] + list(r) for r in X]
    p = len(Z[0])
    XtX = [[sum(z[i] * z[j] for z in Z) for j in range(p)] for i in range(p)]
    Xty = [sum(z[i] * t for z, t in zip(Z, y)) for i in range(p)]
    beta = solve(XtX, Xty)
    fit = [sum(b * v for b, v in zip(beta, z)) for z in Z]
    return beta, [t - f for t, f in zip(y, fit)], fit


def standardize_cols(X):
    p = len(X[0])
    out = [list(r) for r in X]
    for j in range(p):
        col = [r[j] for r in X]
        m = mean(col)
        s = math.sqrt(sum((v - m) ** 2 for v in col) / (len(col) - 1)) or 1.0
        for r in out:
            r[j] = (r[j] - m) / s
    return out


def logit_fit(X, y, ridge=0.0, iters=100):
    """Logistic regression by Newton-Raphson; X rows without intercept; L2 penalty `ridge`
    on the slopes only. Returns (beta, loglik (unpenalised), covariance (inverse penalised Hessian))."""
    Z = [[1.0] + list(r) for r in X]
    p = len(Z[0])
    beta = [0.0] * p
    for _ in range(iters):
        eta = [sum(b * v for b, v in zip(beta, z)) for z in Z]
        mu = [1 / (1 + math.exp(-max(-35, min(35, e)))) for e in eta]
        g = [sum((t - m) * z[i] for z, t, m in zip(Z, y, mu)) - (ridge * beta[i] if i else 0.0) for i in range(p)]
        H = [[sum(m * (1 - m) * z[i] * z[j] for z, m in zip(Z, mu)) + (ridge if (i == j and i) else 0.0)
              for j in range(p)] for i in range(p)]
        step = solve(H, g)
        beta = [b + s for b, s in zip(beta, step)]
        if max(abs(s) for s in step) < 1e-10:
            break
    eta = [sum(b * v for b, v in zip(beta, z)) for z in Z]
    ll = sum(t * e - math.log1p(math.exp(e)) if e < 30 else t * e - e for t, e in zip(y, eta))
    mu = [1 / (1 + math.exp(-max(-35, min(35, e)))) for e in eta]
    H = [[sum(m * (1 - m) * z[i] * z[j] for z, m in zip(Z, mu)) + (ridge if (i == j and i) else 0.0)
          for j in range(p)] for i in range(p)]
    return beta, ll, inverse(H)


def logit_predict(beta, X):
    return [sum(b * v for b, v in zip(beta, [1.0] + list(r))) for r in X]


def chi2_sf_1(x):
    return math.erfc(math.sqrt(max(x, 0) / 2))


def binom_two_sided(k, n):
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)
