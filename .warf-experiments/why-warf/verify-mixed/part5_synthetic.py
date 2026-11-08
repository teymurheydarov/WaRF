"""Part 5: the positive control of finding (e), rebuilt independently. An independent synthetic
seat replaces Laya: s = +/-0.371 + N(0,1) (+ for later fixed), p = sigmoid(0.742 s) (its exact
posterior), it votes REJECT when s > 0. 500 draws; power from 200-resample bootstraps on the
first 100 draws.

    PYTHONIOENCODING=utf-8 python -B part5_synthetic.py"""
import math
import random
from pathlib import Path

from vm_common import (Y, DOM, N, P, auc, ba, boot, sub, logit, sigmoid, review, platt_oof, within, corr,
                       THETA, Tee)

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part5_synthetic.log")
MEM = ("JEV", "SYN", "CLAUDE")
CALJ, _ = platt_oof(P["JEV"])
CALC, _ = platt_oof(P["CLAUDE"])


def zscore(v):
    mu = sum(v) / len(v)
    sd = math.sqrt(sum((x - mu) ** 2 for x in v) / len(v))
    return [(x - mu) / sd for x in v]


def logodds_decision(lsum_reject):
    """Uniform omega, every seat votes: APPROVE iff mean log-odds of APPROVE >= theta."""
    return [(-l / 3) < THETA[DOM[t]] for t, l in enumerate(lsum_reject)]


def draw(rng):
    s = [(0.371 if t else -0.371) + rng.gauss(0, 1) for t in Y]
    ps = [sigmoid(0.742 * x) for x in s]
    p = {"JEV": P["JEV"], "SYN": ps, "CLAUDE": P["CLAUDE"]}
    rej = {"JEV": [x > 0.5 for x in P["JEV"]], "SYN": [x > 0 for x in s], "CLAUDE": [x > 0.5 for x in P["CLAUDE"]]}
    cal = {"JEV": CALJ, "SYN": platt_oof(ps)[0], "CLAUDE": CALC}
    rc = {m: [x > 0.5 for x in cal[m]] for m in MEM}
    # WaRF vote panel at uniform omega (no boundary is reachable with three seats)
    vp = [review({m: (-1 if rej[m][t] else 1) for m in MEM}, {m: 0.5 for m in MEM}, MEM, DOM[t]) for t in range(N)]
    assert all(x[1] != "HIGH" for x in vp)
    vp_dec = [x[0] == "REJECT" for x in vp]
    vp_sc = [-x[2] for x in vp]
    raw = [sum(logit(p[m][t]) for m in MEM) for t in range(N)]
    calsum = [sum(logit(cal[m][t]) for m in MEM) for t in range(N)]
    z = {m: zscore([logit(x) for x in p[m]]) for m in MEM}
    zav = [sum(z[m][t] for m in MEM) / 3 for t in range(N)]
    return p, rej, cal, rc, vp_dec, vp_sc, raw, calsum, zav


def stats(idx, p, rej, cal, rc, vp_dec, vp_sc, raw, calsum, zav, best_auc=None, best_vote=None, best_cvote=None):
    yy = sub(Y, idx)
    A_ = {m: auc(sub(p[m], idx), yy) for m in MEM}
    Bv = {m: ba(sub(rej[m], idx), yy) for m in MEM}
    Bc = {m: ba(sub(rc[m], idx), yy) for m in MEM}
    ba_ = max(A_, key=A_.get) if best_auc is None else best_auc
    bv = max(Bv, key=Bv.get) if best_vote is None else best_vote
    bc = max(Bc, key=Bc.get) if best_cvote is None else best_cvote
    vpd = sub(vp_dec, idx)
    cal_dec = sub(logodds_decision(calsum), idx)
    o = {
        "syn_auc": A_["SYN"],
        "vp_ba": ba(vpd, yy),
        "vp_ba-best": ba(vpd, yy) - Bv[bv],
        "vp_auc-best": auc(sub(vp_sc, idx), yy) - A_[ba_],
        "vp_ba-claude": ba(vpd, yy) - Bv["CLAUDE"],
        "vp_ba-mean": ba(vpd, yy) - sum(Bv.values()) / 3,
        "raw_auc": auc(sub(raw, idx), yy),
        "raw_auc-best": auc(sub(raw, idx), yy) - A_[ba_],
        "raw_auc-mean": auc(sub(raw, idx), yy) - sum(A_.values()) / 3,
        "raw_auc-claude": auc(sub(raw, idx), yy) - A_["CLAUDE"],
        "cal_auc": auc(sub(calsum, idx), yy),
        "cal_auc-best": auc(sub(calsum, idx), yy) - A_[ba_],
        "cal_auc-claude": auc(sub(calsum, idx), yy) - A_["CLAUDE"],
        "cal_ba": ba(cal_dec, yy),
        "cal_ba-bestcalvote": ba(cal_dec, yy) - Bc[bc],
        "zavg_auc-best": auc(sub(zav, idx), yy) - A_[ba_],
    }
    return o, (ba_, bv, bc)


rng = random.Random(2026)
draws, rows, wl = [], [], {"JEV": [], "CLAUDE": []}
for k in range(500):
    d = draw(rng)
    o, best = stats(list(range(N)), *d)
    rows.append(o)
    draws.append((d, best))
    lsyn = within([logit(x) for x in d[0]["SYN"]], Y)
    for m in ("JEV", "CLAUDE"):
        wl[m].append(corr(lsyn, within([logit(x) for x in P[m]], Y)))

log("== (e) synthetic independent seat in place of Laya, 500 draws (mean [2.5 %, 97.5 %] over draws, share > 0)")
log(f"  within-label logit correlation of the synthetic seat: Jev {sum(wl['JEV']) / 500:+.3f}, "
    f"Claude {sum(wl['CLAUDE']) / 500:+.3f}")
for key in rows[0]:
    xs = sorted(r[key] for r in rows)
    n = len(xs)
    log(f"  {key:<20} {sum(xs) / n:+.3f} [{xs[int(0.025 * n)]:+.3f}, {xs[int(0.975 * n) - 1]:+.3f}]  "
        f"> 0 in {sum(1 for x in xs if x > 0) / n:.0%}")
log(f"  best member by AUC: " + ", ".join(f"{m} {sum(1 for _, b in draws if b[0] == m) / 500:.0%}" for m in MEM)
    + "; best vote: " + ", ".join(f"{m} {sum(1 for _, b in draws if b[1] == m) / 500:.0%}" for m in MEM))

# power on n = 100: bootstrap within labels, 200 resamples, first 100 draws; 'detected' = 2.5 % point > 0
keys = ("cal_auc-best", "cal_auc-claude", "vp_ba-best", "raw_auc-claude", "raw_auc-mean", "vp_ba-mean",
        "zavg_auc-best", "cal_ba-bestcalvote")
det = {k: 0 for k in keys}
det_re = {k: 0 for k in keys}
pos = [i for i, t in enumerate(Y) if t]
neg = [i for i, t in enumerate(Y) if not t]
brng = random.Random(99)
for d, best in draws[:100]:
    vals = {k: [] for k in keys}
    vals_re = {k: [] for k in keys}
    for _ in range(200):
        idx = [brng.choice(pos) for _ in pos] + [brng.choice(neg) for _ in neg]
        o, _ = stats(idx, *d, best_auc=best[0], best_vote=best[1], best_cvote=best[2])
        o2, _ = stats(idx, *d)
        for k in keys:
            vals[k].append(o[k])
            vals_re[k].append(o2[k])
    for k in keys:
        v = sorted(vals[k])
        det[k] += v[5] > 0          # 2.5 % point of 200
        v2 = sorted(vals_re[k])
        det_re[k] += v2[5] > 0
log("\n  power on n = 100 (share of the first 100 draws whose 95 % bootstrap interval lies above 0;"
    " best member fixed per draw / re-chosen in every resample):")
for k in keys:
    log(f"    {k:<20} {det[k]}% / {det_re[k]}%")
