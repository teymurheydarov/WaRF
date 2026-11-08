"""Part 6: my own controls for the checking pipeline.

Positive controls
  P1  three independent synthetic seats (AUC about 0.70 each, Bayes threshold): the vote panel
      and the log-odds panel must beat their best member if the pipeline can show a gain.
  P2  learned weights must change decisions when the data warrant it: an oracle seat (right 90 %)
      and an anti-seat (wrong 90 %) beside Jev; and two near-oracles must make the SPRT fire.
  P3  the synthetic control of finding (e) with each seat's vote at its calibrated threshold:
      does a majority of well-thresholded votes beat its best member?
Negative controls
  N1  labels shuffled 200 times: AUCs centre on 0.5, the log-odds panel's gain over Claude and
      over the mean member centres on 0, and the bootstrap interval covers 0 at about 95 %.
  N2  a pure-noise seat in place of Laya: the log-odds panel must not gain from it.

    PYTHONIOENCODING=utf-8 python -B part6_controls.py"""
import math
import random
from pathlib import Path

from vm_common import (Y, DOM, N, P, SEATS, auc, ba, boot, sub, logit, sigmoid, review, review_llr, stream,
                       by_row, load_dates, platt_oof, THETA, Tee)

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part6_controls.log")
dates, _ = load_dates()
date_order = sorted(range(N), key=lambda t: (dates[t], t))
ALL = list(range(N))


def syn_seat(rng, d=0.742, y=Y):
    s = [(d / 2 if t else -d / 2) + rng.gauss(0, 1) for t in y]
    return [sigmoid(d * x) for x in s], [x > 0 for x in s]


def panels(p, rej, mem, y=Y):
    vp = [review({m: (-1 if rej[m][t] else 1) for m in mem}, {m: 0.5 for m in mem}, mem, DOM[t]) for t in range(N)]
    vp_dec = [x[0] == "REJECT" for x in vp]
    vp_sc = [-x[2] for x in vp]
    lo = [review_llr({m: -logit(p[m][t]) for m in mem}, {m: 0.5 for m in mem}, mem, DOM[t], "nosprt") for t in range(N)]
    lo_dec = [x[0] == "REJECT" for x in lo]
    lo_sc = [-x[2] for x in lo]
    return vp_dec, vp_sc, lo_dec, lo_sc


# ── P1 ───────────────────────────────────────────────────────────────────────
rng = random.Random(11)
acc = {"vp_ba-bestvote": [], "vp_auc-bestauc": [], "lo_auc-bestauc": [], "lo_ba-bestvote": []}
for _ in range(300):
    mem = ("S1", "S2", "S3")
    p, rej = {}, {}
    for m in mem:
        p[m], rej[m] = syn_seat(rng)
    vp_dec, vp_sc, lo_dec, lo_sc = panels(p, rej, mem)
    bv = max(ba(rej[m], Y) for m in mem)
    bauc = max(auc(p[m], Y) for m in mem)
    acc["vp_ba-bestvote"].append(ba(vp_dec, Y) - bv)
    acc["vp_auc-bestauc"].append(auc(vp_sc, Y) - bauc)
    acc["lo_auc-bestauc"].append(auc(lo_sc, Y) - bauc)
    acc["lo_ba-bestvote"].append(ba(lo_dec, Y) - bv)
log("== P1 three independent synthetic seats (AUC about 0.70 each), 300 draws: mean [2.5 %, 97.5 %], share > 0")
for k, xs in acc.items():
    xs.sort()
    log(f"  {k:<16} {sum(xs) / len(xs):+.3f} [{xs[7]:+.3f}, {xs[292]:+.3f}]  > 0 in {sum(1 for x in xs if x > 0) / len(xs):.0%}")

# ── P2 ───────────────────────────────────────────────────────────────────────
rng = random.Random(12)
orc = [(t if rng.random() < 0.9 else (not t)) for t in Y]       # REJECT flag, right 90 %
anti = [((not t) if rng.random() < 0.9 else t) for t in Y]      # wrong 90 %
votes = [{"JEV": (-1 if P["JEV"][t] > 0.5 else 1), "ORACLE": (-1 if orc[t] else 1), "ANTI": (-1 if anti[t] else 1)}
         for t in range(N)]
prof = ("JEV", "ORACLE", "ANTI")
uni = [review(votes[t], {s: 0.5 for s in prof}, prof, DOM[t])[0] for t in range(N)]
res, W = stream(date_order, votes, prof_order=prof)
rows = by_row(res)
chg = sum(1 for t in range(N) if rows[t]["dec"] != uni[t])
log("\n== P2 learned weights when the data warrant it (commit-date order)")
log(f"  Jev + oracle (90 % right) + anti-seat (90 % wrong): decisions changed by learning {chg}/100; "
    f"BA uniform {ba([d == 'REJECT' for d in uni], Y):.3f} -> learned {ba([r['dec'] == 'REJECT' for r in rows], Y):.3f}; "
    f"final LOGIC omega " + ", ".join(f"{s} {W[s]['LOGIC'][0] / sum(W[s]['LOGIC']):.2f}" for s in prof))
orc2 = [(t if rng.random() < 0.95 else (not t)) for t in Y]
votes2 = [{"JEV": (-1 if P["JEV"][t] > 0.5 else 1), "ORACLE": (-1 if orc[t] else 1), "ORACLE2": (-1 if orc2[t] else 1)}
          for t in range(N)]
prof2 = ("JEV", "ORACLE", "ORACLE2")
res2, W2 = stream(date_order, votes2, prof_order=prof2)
nh = sum(1 for r in res2 if r["conf"] == "HIGH")
n2 = sum(1 for r in res2 if len(r["cast"]) < 3)
log(f"  Jev + two near-oracles (90 %, 95 %): HIGH verdicts {nh}, reviews stopped before the third seat {n2}, "
    f"first HIGH at review {next((j + 1 for j, r in enumerate(res2) if r['conf'] == 'HIGH'), None)}")

# ── P3 ───────────────────────────────────────────────────────────────────────
CALJ, _ = platt_oof(P["JEV"])
CALC, _ = platt_oof(P["CLAUDE"])
rng = random.Random(13)
acc = {"calvote-majority_ba - best calvote": [], "calvote-majority_ba - best raw vote": [],
       "calvote-count AUC - best AUC": []}
for _ in range(200):
    ps, _rej = syn_seat(rng)
    cal = {"JEV": CALJ, "SYN": platt_oof(ps)[0], "CLAUDE": CALC}
    rc = {m: [x > 0.5 for x in cal[m]] for m in cal}
    raw_rej = {"JEV": [x > 0.5 for x in P["JEV"]], "SYN": _rej, "CLAUDE": [x > 0.5 for x in P["CLAUDE"]]}
    mem = ("JEV", "SYN", "CLAUDE")
    vp = [review({m: (-1 if rc[m][t] else 1) for m in mem}, {m: 0.5 for m in mem}, mem, DOM[t]) for t in range(N)]
    dec = [x[0] == "REJECT" for x in vp]
    sc = [-x[2] for x in vp]
    acc["calvote-majority_ba - best calvote"].append(ba(dec, Y) - max(ba(rc[m], Y) for m in mem))
    acc["calvote-majority_ba - best raw vote"].append(ba(dec, Y) - max(ba(raw_rej[m], Y) for m in mem))
    acc["calvote-count AUC - best AUC"].append(auc(sc, Y) - max(auc(P["JEV"], Y), auc(ps, Y), auc(P["CLAUDE"], Y)))
log("\n== P3 synthetic control of finding (e) with every seat voting at its calibrated threshold, 200 draws")
for k, xs in acc.items():
    xs.sort()
    log(f"  {k:<38} {sum(xs) / len(xs):+.3f} [{xs[5]:+.3f}, {xs[194]:+.3f}]  > 0 in {sum(1 for x in xs if x > 0) / len(xs):.0%}")

# ── N1 ───────────────────────────────────────────────────────────────────────
rng = random.Random(14)
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
_, vp_sc, lo_dec, lo_sc = panels(P, REJ, SEATS)
m_auc = {"vote panel": [], "log-odds panel": [], "Claude p": []}
gain_c, gain_m, cover_c, cover_m = [], [], 0, 0
NS = 200
for k in range(NS):
    yy = Y[:]
    # shuffle within matched pairs' label slots: permute labels across rows
    rng.shuffle(yy)
    m_auc["vote panel"].append(auc(vp_sc, yy))
    m_auc["log-odds panel"].append(auc(lo_sc, yy))
    m_auc["Claude p"].append(auc(P["CLAUDE"], yy))
    g1 = boot(lambda idx: auc(sub(lo_sc, idx), sub(yy, idx)) - auc(sub(P["CLAUDE"], idx), sub(yy, idx)), yy, n=200, seed=k)
    g2 = boot(lambda idx: auc(sub(lo_sc, idx), sub(yy, idx)) - sum(auc(sub(P[s], idx), sub(yy, idx)) for s in SEATS) / 3,
              yy, n=200, seed=k)
    gain_c.append(g1[0])
    gain_m.append(g2[0])
    cover_c += g1[1] <= 0 <= g1[2]
    cover_m += g2[1] <= 0 <= g2[2]
log(f"\n== N1 labels shuffled {NS} times")
log("  mean AUC: " + ", ".join(f"{k} {sum(v) / NS:.3f}" for k, v in m_auc.items()))
log(f"  log-odds panel minus Claude: mean {sum(gain_c) / NS:+.4f}, 95 % bootstrap interval covers 0 in {cover_c / NS:.0%}")
log(f"  log-odds panel minus mean member: mean {sum(gain_m) / NS:+.4f}, covers 0 in {cover_m / NS:.0%}")

# ── N2 ───────────────────────────────────────────────────────────────────────
rng = random.Random(15)
d_mean, d_claude = [], []
for _ in range(300):
    noise = [min(max(rng.random(), 0.01), 0.99) for _ in range(N)]
    p = {"JEV": P["JEV"], "NOISE": noise, "CLAUDE": P["CLAUDE"]}
    mem = ("JEV", "NOISE", "CLAUDE")
    rej = {m: [x > 0.5 for x in p[m]] for m in mem}
    _, _, _, sc = panels(p, rej, mem)
    sc2 = [-logit(P["JEV"][t]) - logit(P["CLAUDE"][t]) for t in range(N)]
    d_mean.append(auc(sc, Y) - auc([-x for x in sc2], Y))
    d_claude.append(auc(sc, Y) - auc(P["CLAUDE"], Y))
d_mean.sort()
d_claude.sort()
log("\n== N2 a pure-noise seat (p uniform on [0.01, 0.99]) in place of Laya, 300 draws")
log(f"  log-odds panel with noise minus the same panel without it (Jev + Claude): mean {sum(d_mean) / 300:+.3f} "
    f"[{d_mean[7]:+.3f}, {d_mean[292]:+.3f}]")
log(f"  log-odds panel with noise minus Claude: mean {sum(d_claude) / 300:+.3f} [{d_claude[7]:+.3f}, {d_claude[292]:+.3f}]")
