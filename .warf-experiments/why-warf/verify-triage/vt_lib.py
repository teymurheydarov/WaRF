"""Independent checker's helpers (verify-triage). Pure Python: numpy's BLAS crashes here.

Nothing in this file calls a model or a service; it only reads stored JSONL files.

Conventions
  system   = (d, c): d[i] is the verdict on item i (+1 APPROVE, -1 REJECT), c[i] a confidence
             key; higher keys are trusted first. Keys may be tuples (compared lexicographically).
  correct  = d[i] == truth[i].
  curve    = expected cumulative number of right verdicts among the k most trusted items,
             k = 0..n, averaged exactly over all orders of tied keys.
  AURC     = mean selective error over k = 1..n.
  trust AUROC = P(key of a right verdict > key of a wrong one), ties count half.
"""
import json
import math
import random

EXP = "C:/workdir/warf/WaRF/.warf-experiments"
ROOT = "C:/workdir/warf/WaRF"

LLR_A = math.log(0.80 / 0.30)
LLR_R = math.log(0.20 / 0.70)
A_BOUND = math.log(0.90 / 0.05)
B_BOUND = math.log(0.10 / 0.95)
THETA = {"LOGIC": 0.0, "SECURITY": 0.2, "PERFORMANCE": -0.1}
BAND_RANK = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def xv(label):
    return 1 if label == "APPROVE" else -1


# ------------------------------------------------------------------ WaRF rule, written out again
def warf_round(votes, omegas, domain, early_stop):
    """My own re-implementation of WaRF's Round: (decision, band, lambda_at_end, normalised, k_used).
    The first boundary crossing decides with HIGH; without one, the omega-weighted mean vote
    against theta decides, MEDIUM if |mean - theta| >= 0.2, else LOW. With early_stop the
    returned lambda is the one at the crossing; otherwise the one after every vote."""
    lam = 0.0
    first = None
    k_used = len(votes)
    for k, (v, w) in enumerate(zip(votes, omegas), 1):
        lam += w * (LLR_A if v == 1 else LLR_R)
        if first is None:
            if lam >= A_BOUND:
                first = 1
            elif lam <= B_BOUND:
                first = -1
            if first is not None and early_stop:
                k_used = k
                break
    used_v, used_w = votes[:k_used], omegas[:k_used]
    norm = sum(w * v for v, w in zip(used_v, used_w)) / sum(used_w)
    if first is not None:
        return first, "HIGH", lam, norm, k_used
    theta = THETA[domain]
    dec = 1 if norm >= theta else -1
    band = "MEDIUM" if abs(norm - theta) >= 0.2 else "LOW"
    return dec, band, lam, norm, k_used


# ------------------------------------------------------------------ curves and scores
def curve(correct, key):
    """Expected cumulative right count among the k most trusted, k = 0..n, exact tie average."""
    n = len(correct)
    order = sorted(range(n), key=lambda i: key[i], reverse=True)
    cum = [0.0] * (n + 1)
    pos = 0
    while pos < n:
        j = pos
        while j + 1 < n and key[order[j + 1]] == key[order[pos]]:
            j += 1
        g = j - pos + 1
        r = sum(correct[order[t]] for t in range(pos, j + 1))
        for t in range(1, g + 1):
            cum[pos + t] = cum[pos] + r * t / g
        pos = j + 1
    return cum


def acc_at(cum, k):
    """Selective accuracy at coverage k (k may be fractional: the cumulative count is
    interpolated linearly between integers)."""
    if k <= 0:
        return float("nan")
    lo = int(math.floor(k))
    if lo >= len(cum) - 1:
        return cum[-1] / (len(cum) - 1)
    frac = k - lo
    c = cum[lo] + frac * (cum[lo + 1] - cum[lo])
    return c / k


def acc_at_round(cum, k):
    """Alternative: accuracy at round(k) (Python's banker's rounding avoided: half up)."""
    kk = int(math.floor(k + 0.5))
    return cum[kk] / kk if kk > 0 else float("nan")


def aurc(cum):
    n = len(cum) - 1
    return sum(1 - cum[k] / k for k in range(1, n + 1)) / n


def midranks(vals):
    n = len(vals)
    order = sorted(range(n), key=lambda i: vals[i])
    r = [0.0] * n
    pos = 0
    while pos < n:
        j = pos
        while j + 1 < n and vals[order[j + 1]] == vals[order[pos]]:
            j += 1
        mr = (pos + j) / 2 + 1
        for t in range(pos, j + 1):
            r[order[t]] = mr
        pos = j + 1
    return r


def auroc(scores, pos):
    """P(score of a positive > score of a negative), ties half (Mann-Whitney via midranks)."""
    rk = midranks(scores)
    npos = sum(1 for t in pos if t)
    nneg = len(pos) - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    s = sum(r for r, t in zip(rk, pos) if t)
    return (s - npos * (npos + 1) / 2) / (npos * nneg)


def auroc_pairs(scores, pos):
    """Brute-force version, for checking auroc()."""
    P = [s for s, t in zip(scores, pos) if t]
    N = [s for s, t in zip(scores, pos) if not t]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))


def trust_auroc(correct, key):
    return auroc(key, [bool(c) for c in correct])


# ------------------------------------------------------------------ resampling
def boot_indices(truth, B, seed):
    """B resamples of item indices, drawn with replacement within each truth label."""
    rng = random.Random(seed)
    groups = {}
    for i, t in enumerate(truth):
        groups.setdefault(t, []).append(i)
    out = []
    for _ in range(B):
        idx = []
        for g in groups.values():
            idx.extend(rng.choice(g) for _ in g)
        out.append(idx)
    return out


def pct(vals, q):
    """Percentile with linear interpolation (type 7)."""
    s = sorted(vals)
    if not s:
        return float("nan")
    h = (len(s) - 1) * q
    lo = int(math.floor(h))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (h - lo) * (s[hi] - s[lo])


def boot_p(vals):
    """Two-sided bootstrap p for 'difference = 0': 2 * min(share <= 0, share >= 0), mid-p for zeros."""
    n = len(vals)
    lt = sum(1 for v in vals if v < 0) / n
    eq = sum(1 for v in vals if v == 0) / n
    gt = 1 - lt - eq
    return min(1.0, 2 * min(lt + eq / 2, gt + eq / 2))


def ci(vals):
    vals = [v for v in vals if v == v]
    return pct(vals, 0.025), pct(vals, 0.975)


# ------------------------------------------------------------------ exact tests
def binom_pmf(k, n, p):
    return math.comb(n, k) * p ** k * (1 - p) ** (n - k)


def cp_interval(k, n, level=0.95):
    a = (1 - level) / 2

    def upper_tail(p):         # P(X >= k | p)
        return sum(binom_pmf(i, n, p) for i in range(k, n + 1))

    def lower_tail(p):         # P(X <= k | p)
        return sum(binom_pmf(i, n, p) for i in range(0, k + 1))

    if k == 0:
        lo = 0.0
    else:
        a_, b_ = 0.0, 1.0
        for _ in range(100):
            m = (a_ + b_) / 2
            if upper_tail(m) < a:
                a_ = m
            else:
                b_ = m
        lo = (a_ + b_) / 2
    if k == n:
        hi = 1.0
    else:
        a_, b_ = 0.0, 1.0
        for _ in range(100):
            m = (a_ + b_) / 2
            if lower_tail(m) > a:
                a_ = m
            else:
                b_ = m
        hi = (a_ + b_) / 2
    return lo, hi


def hyper_sf(x, N, K, n):
    """P(X >= x) for X ~ Hypergeometric(population N, K successes, n draws)."""
    tot = math.comb(N, n)
    return sum(math.comb(K, i) * math.comb(N - K, n - i) for i in range(x, min(K, n) + 1)) / tot


def fisher_two_sided(a, b, c, d):
    """Fisher's exact test for [[a, b], [c, d]], two-sided (sum of tables no more likely)."""
    r1, r2, c1 = a + b, c + d, a + c
    n = r1 + r2

    def pr(x):
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)

    p0 = pr(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    return min(1.0, sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p0 * (1 + 1e-9)))
