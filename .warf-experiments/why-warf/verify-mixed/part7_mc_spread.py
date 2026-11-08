"""Part 7: Monte Carlo spread of the numbers that come from random draws or random orders, so
that small differences from the reported values can be judged; plus early stopping in random
orders (votes and log-odds, learned omega).

    PYTHONIOENCODING=utf-8 python -B part7_mc_spread.py"""
import random
from itertools import permutations
from pathlib import Path

from vm_common import Y, DOM, N, P, SEATS, auc, ba, logit, sigmoid, review, stream, by_row, platt_oof, Tee
import part5_synthetic as p5  # reuses draw()/stats(); importing it re-runs part 5 once (its log is rewritten)

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part7_mc_spread.log")
ORDERS = list(permutations(SEATS))
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
VOTES = [{s: (-1 if REJ[s][t] else 1) for s in SEATS} for t in range(N)]
LLR_RAW = [{s: -logit(P[s][t]) for s in SEATS} for t in range(N)]
CALP = {s: platt_oof(P[s])[0] for s in SEATS}
LLR_CAL = [{s: -logit(CALP[s][t]) for s in SEATS} for t in range(N)]

# routing shares and settling point, shadow route, 5 seeds x 200 orders x 6 profiles
log("== routing (raw votes, route 'shadow'): spread over 5 seeds of 200 random orders x 6 profile orders")
for seed in (17, 1, 2, 3, 4):
    rng = random.Random(seed)
    shares = {s: 0.0 for s in SEATS}
    bas = []
    for _ in range(200):
        order = list(range(N))
        rng.shuffle(order)
        for o in ORDERS:
            res, _ = stream(order, VOTES, prof_order=o, route="shadow")
            for r in res:
                shares[r["leader"]] += 1 / N
            bas.append(ba([r["dec"] == "REJECT" for r in by_row(res)], Y))
    log(f"  seed {seed}: BA mean {sum(bas) / len(bas):.3f}; shares " + ", ".join(f"{s} {shares[s] / 1200:.3f}" for s in SEATS))

# early stopping in random orders with learned omega
log("\n== early stopping with learned omega, 200 random orders x 6 profile orders")
rng = random.Random(23)
tot = {"votes": [0, 0, 0], "raw log-odds": [0, 0, 0], "calibrated log-odds": [0, 0, 0]}
for _ in range(200):
    order = list(range(N))
    rng.shuffle(order)
    for o in ORDERS:
        for tag, llr in (("votes", None), ("raw log-odds", LLR_RAW), ("calibrated log-odds", LLR_CAL)):
            e, _ = stream(order, VOTES, prof_order=o, mode="early", llr=llr)
            ne, _ = stream(order, VOTES, prof_order=o, mode="nosprt", llr=llr)
            e, ne = by_row(e), by_row(ne)
            tot[tag][0] += sum(1 for r in e if r["conf"] == "HIGH")
            tot[tag][1] += sum(1 for a, b in zip(e, ne) if a["dec"] != b["dec"])
            tot[tag][2] = max(tot[tag][2], sum(1 for r in e if r["conf"] == "HIGH"))
for tag, (h, c, mx) in tot.items():
    log(f"  {tag:<20} HIGH verdicts per run mean {h / 1200:.2f} (max {mx}); decisions differing from the "
        f"no-boundary run: {c} in 1200 runs")

# synthetic control: spread of 'cal_auc-best > 0' over seeds, and alternative definitions
log("\n== synthetic control (e): share of draws with calibrated log-odds AUC above the best member, 5 seeds x 500")
for seed in (2026, 1, 2, 3, 4):
    rng = random.Random(seed)
    vals, vals_calbest, vals_nocal = [], [], []
    for _ in range(500):
        d = p5.draw(rng)
        o, _ = p5.stats(list(range(N)), *d)
        vals.append(o["cal_auc-best"])
        p, rej, cal, rc, vp_dec, vp_sc, raw, calsum, zav = d
        best_cal = max(auc(cal[m], Y) for m in p5.MEM)       # best member judged on calibrated p
        vals_calbest.append(auc(calsum, Y) - best_cal)
        nocal = [logit(cal["JEV"][t]) + logit(cal["CLAUDE"][t]) + logit(p["SYN"][t]) for t in range(N)]
        vals_nocal.append(auc(nocal, Y) - max(auc(p[m], Y) for m in p5.MEM))
    f = lambda xs: f"mean {sum(xs) / len(xs):+.4f}, > 0 in {sum(1 for x in xs if x > 0) / len(xs):.0%}"  # noqa: E731
    log(f"  seed {seed}: {f(vals)}; best judged on calibrated p: {f(vals_calbest)}; "
        f"synthetic seat left uncalibrated: {f(vals_nocal)}")
