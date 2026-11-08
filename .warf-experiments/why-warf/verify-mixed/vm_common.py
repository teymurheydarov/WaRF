"""Shared loaders, metrics and a WaRF-faithful panel driver for the independent check of the
mixed-panel findings (Jev, Laya, Claude on the 100 size-matched gismo6 commits).

Written from scratch for the check; it does not import or read anything under why-warf/mixed/.
Stored data only, no model or service is called. Pure Python (numpy's BLAS crashes here).
"""
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

EXP = Path("C:/workdir/warf/WaRF/.warf-experiments")
sys.path.insert(0, "C:/workdir/warf/WaRF")
from warf.engine import (  # noqa: E402
    SPRTState, sprt_update, synthesis, bayesian_update, apply_decay,
    A, B, LLR_APPROVE, LLR_REJECT, THETA, DOMAINS, Decision, Confidence,
)
from warf.state import ORACLE_TIERS  # noqa: E402

GAMMA = ORACLE_TIERS["DEVELOPER"]


def jl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


SEL = jl(EXP / "laya-five" / "selection.jsonl")
IDS = [s["id"] for s in SEL]
Y = [s["label"] == "REJECT" for s in SEL]          # True = later fixed
DOM = [s["domain"] for s in SEL]
N = len(SEL)
PAIR = [i // 2 for i in range(N)]                    # rows 2k (later fixed), 2k+1 (never fixed)
assert all(Y[2 * k] and not Y[2 * k + 1] for k in range(N // 2)), "pair layout"

ONE = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_one.jsonl")}
SEATS = ("JEV", "LAYA", "CLAUDE")                    # profile order used by the reported runs
P = {
    "JEV": [ONE[i]["jev"]["round1"]["JEV"]["p_reject"] for i in IDS],
    "LAYA": [s["p_single_laya"] for s in SEL],
    "CLAUDE": [s["p_claude"] for s in SEL],
}
JEV_CHOICE = [ONE[i]["jev"]["round1"]["JEV"]["choice"] for i in IDS]


def load_dates():
    """Author date (%aI, see tools/run_laya_sweep.py cmd_plan) of each selected commit, as an
    aware datetime (the strings mix 'Z' and '+01:00', so they must not be sorted as text)."""
    want = {s["commit"] for s in SEL}
    raw = {}
    with open(EXP / "laya-sweep" / "plan.jsonl", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e["sha"] in want:
                raw[e["sha"]] = e["date"]
    out = []
    for s in SEL:
        out.append(datetime.fromisoformat(raw[s["commit"]].replace("Z", "+00:00")).astimezone(timezone.utc))
    return out, [raw[s["commit"]] for s in SEL]


# ── metrics ───────────────────────────────────────────────────────────────────

def auc(score, y):
    """Rank AUC: P(later-fixed scores above never-fixed), ties count half."""
    n = len(score)
    order = sorted(range(n), key=score.__getitem__)
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and score[order[j + 1]] == score[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = r
        i = j + 1
    n1 = sum(1 for t in y if t)
    n0 = n - n1
    return (sum(r for r, t in zip(ranks, y) if t) - n1 * (n1 + 1) / 2) / (n1 * n0)


def auc_pairs(score, y):
    """Slow pairwise AUC, used only to cross-check auc()."""
    pos = [s for s, t in zip(score, y) if t]
    neg = [s for s, t in zip(score, y) if not t]
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


def ba(rej, y):
    """Balanced accuracy of REJECT decisions (True = REJECT) against later-fixed labels."""
    n1 = sum(1 for t in y if t)
    n0 = len(y) - n1
    tp = sum(1 for r, t in zip(rej, y) if r and t)
    tn = sum(1 for r, t in zip(rej, y) if (not r) and (not t))
    return 0.5 * (tp / n1 + tn / n0)


def sign_p(a, b):
    """Exact two-sided sign test on a wins against b wins."""
    n = a + b
    if n == 0:
        return 1.0
    k = min(a, b)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def discordant(rej1, rej2, y):
    """(right only with 1, right only with 2)."""
    a = sum(1 for r1, r2, t in zip(rej1, rej2, y) if (r1 == t) and (r2 != t))
    b = sum(1 for r1, r2, t in zip(rej1, rej2, y) if (r2 == t) and (r1 != t))
    return a, b


def boot(stat, y, n=2000, seed=101, by="label"):
    """stat(idx) on all items and on n resamples: within each label (default) or of matched
    pairs (by='pair'). Returns (value, 2.5 %, 97.5 %)."""
    rng = random.Random(seed)
    if by == "label":
        pos = [i for i, t in enumerate(y) if t]
        neg = [i for i, t in enumerate(y) if not t]
        draw = lambda: [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]  # noqa: E731
    else:
        npair = len(y) // 2
        def draw():
            ks = [rng.randrange(npair) for _ in range(npair)]
            return [2 * k for k in ks] + [2 * k + 1 for k in ks]
    vals = sorted(stat(draw()) for _ in range(n))
    return stat(list(range(len(y)))), vals[int(0.025 * n)], vals[int(0.975 * n) - 1]


def sub(v, idx):
    return [v[i] for i in idx]


def logit(p):
    return math.log(p / (1 - p))


def sigmoid(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb)


def within(x, y):
    m1 = sum(v for v, t in zip(x, y) if t) / sum(y)
    m0 = sum(v for v, t in zip(x, y) if not t) / (len(y) - sum(y))
    return [v - (m1 if t else m0) for v, t in zip(x, y)]


def fit_logistic(x, y, smooth=False):
    """Maximum-likelihood a, b of P(y=1) = sigmoid(a + b x), Newton-Raphson with step halving.
    smooth=True uses Platt's (1999) target smoothing instead of 0/1 targets."""
    n1 = sum(1 for t in y if t)
    n0 = len(y) - n1
    if smooth:
        tpos, tneg = (n1 + 1) / (n1 + 2), 1 / (n0 + 2)
        tgt = [tpos if t else tneg for t in y]
    else:
        tgt = [1.0 if t else 0.0 for t in y]

    def ll(a, b):
        s = 0.0
        for xi, ti in zip(x, tgt):
            z = a + b * xi
            # log sigmoid(z) and log(1 - sigmoid(z)) computed stably
            lp = -math.log1p(math.exp(-z)) if z >= 0 else z - math.log1p(math.exp(z))
            lq = -z + lp
            s += ti * lp + (1 - ti) * lq
        return s

    a = b = 0.0
    cur = ll(a, b)
    for _ in range(200):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for xi, ti in zip(x, tgt):
            p = sigmoid(a + b * xi)
            r = ti - p
            w = p * (1 - p)
            g0 += r
            g1 += r * xi
            h00 += w
            h01 += w * xi
            h11 += w * xi * xi
        det = h00 * h11 - h01 * h01
        da = (h11 * g0 - h01 * g1) / det
        db = (-h01 * g0 + h00 * g1) / det
        step = 1.0
        while step > 1e-8:
            na, nb = a + step * da, b + step * db
            new = ll(na, nb)
            if new >= cur - 1e-12:
                break
            step /= 2
        a, b, cur = na, nb, new
        if abs(step * da) + abs(step * db) < 1e-12:
            break
    return a, b


def platt_oof(p, y=Y, smooth=False):
    """Leave-one-matched-pair-out Platt calibration of p (fit on logit p). Returns calibrated p
    and the per-fold slopes."""
    x = [logit(v) for v in p]
    out = [0.0] * len(p)
    slopes = []
    for k in range(len(p) // 2):
        tr = [i for i in range(len(p)) if PAIR[i] != k]
        a, b = fit_logistic([x[i] for i in tr], [y[i] for i in tr], smooth=smooth)
        slopes.append(b)
        for i in (2 * k, 2 * k + 1):
            out[i] = sigmoid(a + b * x[i])
    return out, slopes


# ── WaRF panel driver (mirrors orchestrator.run_review with engine's own math) ───────

def review(votes, omega, prof_order, domain, mode="early"):
    """One review. votes/omega: dict seat -> +1/-1 and effective weight; prof_order: the profile
    order (ties in omega keep it, as list.sort(reverse=True) does in run_review).
    mode: 'early' = WaRF default; 'noearly' = --no-early-stop (first crossing still decides);
    'nosprt' = synthesis on every vote, boundaries ignored.
    Returns (decision str, confidence str, Lambda, seats asked in order)."""
    seats = sorted(prof_order, key=lambda s: omega[s], reverse=True)
    st = SPRTState()
    cast = []
    early = None
    for s in seats:
        if early is not None and mode == "early":
            break
        st, crossed = sprt_update(st, votes[s], omega[s])
        cast.append(s)
        if crossed is not None and mode != "nosprt" and early is None:
            early = crossed
    if early is not None:
        return early.value, "HIGH", st.lambda_, cast
    dec, conf, _ = synthesis([votes[s] for s in cast], [omega[s] for s in cast], domain)
    return dec.value, conf.value, st.lambda_, cast


def review_llr(llr, omega, prof_order, domain, mode="early"):
    """IDEAS.md 'Use the probability': same loop, each vote adds omega * its own log-odds of
    APPROVE (instead of the fixed LLR); synthesis compares the omega-weighted mean log-odds with
    theta. Returns (decision, confidence, Lambda, cast)."""
    seats = sorted(prof_order, key=lambda s: omega[s], reverse=True)
    lam = 0.0
    cast = []
    early = None
    for s in seats:
        if early is not None and mode == "early":
            break
        lam += omega[s] * llr[s]
        cast.append(s)
        if mode != "nosprt" and early is None:
            if lam >= A:
                early = "APPROVE"
            elif lam <= B:
                early = "REJECT"
    if early is not None:
        return early, "HIGH", lam, cast
    theta = THETA[domain]
    w = sum(omega[s] for s in cast)
    norm = sum(omega[s] * llr[s] for s in cast) / w
    dec = "APPROVE" if norm >= theta else "REJECT"
    conf = "MEDIUM" if abs(norm - theta) >= 0.2 else "LOW"
    return dec, conf, lam, cast


def stream(order, votes, prof_order=SEATS, mode="early", learn=True, labels=Y,
           dates=None, decay=False, route=None, llr=None):
    """Prequential WaRF run over commits in `order` (list of row indices).
    votes[t][seat] = +1/-1. Per-domain Beta(1,1) per seat; after each review the label updates
    every seat that voted (alpha+gamma if right, beta+gamma if wrong), as apply_oracle does.
    route=None: the panel decides (review / review_llr).
    route='shadow': every seat votes and learns, the heaviest seat's vote decides.
    route='only': only the heaviest seat is asked and updated (--max-agents 1).
    decay=True: effective omega decayed by 0.95 per week since the seat's last update, with
    reviews and labels dated at the commit's author date (needs dates, order by date).
    Returns list of dicts per reviewed commit (in `order`), and the final weights."""
    W = {s: {d: [1.0, 1.0] for d in DOMAINS} for s in prof_order}
    last = {s: None for s in prof_order}
    res = []
    for t in order:
        d = DOM[t]
        om = {}
        for s in prof_order:
            a, b = W[s][d]
            if decay and last[s] is not None:
                weeks = (dates[t] - last[s]).total_seconds() / (7 * 24 * 3600)
                a, b = apply_decay(a, b, weeks)
            om[s] = a / (a + b)
        seats_sorted = sorted(prof_order, key=lambda s: om[s], reverse=True)
        leader = seats_sorted[0]
        if route is None:
            if llr is None:
                dec, conf, lam, cast = review(votes[t], om, prof_order, d, mode)
            else:
                dec, conf, lam, cast = review_llr(llr[t], om, prof_order, d, mode)
        elif route == "shadow":
            dec = "APPROVE" if votes[t][leader] == 1 else "REJECT"
            conf, lam, cast = None, None, list(prof_order)
        elif route == "only":
            dec2, conf, lam, cast = review(votes[t], om, (leader,), d, mode)
            dec = dec2
        else:
            raise ValueError(route)
        res.append({"t": t, "dec": dec, "conf": conf, "lam": lam, "cast": cast,
                    "omega": dict(om), "leader": leader})
        if learn:
            x_star = -1 if labels[t] else 1
            for s in cast:
                a, b = W[s][d]
                W[s][d] = list(bayesian_update(a, b, votes[t][s] == x_star, GAMMA))
                if dates is not None:
                    last[s] = dates[t]
    return res, W


def by_row(res):
    """Map a stream result (in review order) back to row order."""
    out = [None] * N
    for r in res:
        out[r["t"]] = r
    return out


class Tee:
    """Print to stdout and to a log file."""

    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")

    def __call__(self, *a):
        s = " ".join(str(x) for x in a)
        print(s)
        self.f.write(s + "\n")
        self.f.flush()
