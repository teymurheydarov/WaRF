"""Part 2: learned weights (finding b). Prequential runs in commit-date order and in random
orders, with and without WaRF's decay; label-shuffle and random-label controls for the AUC of
Lambda.

    PYTHONIOENCODING=utf-8 python -B part2_learned.py"""
import json
import random
from itertools import permutations
from pathlib import Path

from vm_common import (Y, DOM, N, P, SEATS, A, B, LLR_REJECT, LLR_APPROVE, auc, ba, boot, sub, review,
                       stream, by_row, load_dates, Tee)
from warf.engine import omega_ci

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part2_learned.log")
ORDERS = list(permutations(SEATS))
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
VOTES = [{s: (-1 if REJ[s][t] else 1) for s in SEATS} for t in range(N)]
dates, raw_dates = load_dates()
date_order = sorted(range(N), key=lambda t: (dates[t], t))
text_order = sorted(range(N), key=lambda t: (raw_dates[t], t))
log(f"== (b) learned weights; commits {raw_dates[date_order[0]]} to {raw_dates[date_order[-1]]}")
log(f"  date order by instant equals date order by text: {date_order == text_order}; "
    f"tied author dates: {len(dates) - len(set(dates))}")

# uniform reference
UNI = [review(VOTES[t], {s: 0.5 for s in SEATS}, SEATS, DOM[t], "early") for t in range(N)]
uni_dec = [x[0] == "REJECT" for x in UNI]
uni_score = [-x[2] for x in UNI]
v, lo, hi = boot(lambda idx: auc(sub(uni_score, idx), sub(Y, idx)), Y, seed=41)
log(f"  uniform panel: AUC of -Lambda {v:.3f} [{lo:.3f}, {hi:.3f}] (finding a's interval check)")


def learned(order, prof=SEATS, mode="early", labels=Y, decay=False):
    res, W = stream(order, VOTES, prof_order=prof, mode=mode, labels=labels,
                    dates=dates if decay else None, decay=decay)
    return by_row(res), W


log("\n  commit-date order, every profile order and stopping rule:")
for decay in (False, True):
    for mode in ("early", "noearly", "nosprt"):
        diffs = []
        for o in ORDERS:
            rows, W = learned(date_order, o, mode, decay=decay)
            dec = [r["dec"] == "REJECT" for r in rows]
            diffs.append(sum(a != b for a, b in zip(dec, uni_dec)))
        log(f"    decay {str(decay):<5} mode {mode:<8} decisions differing from uniform per profile order: {diffs}")

rows, W = learned(date_order)
dec_l = [r["dec"] == "REJECT" for r in rows]
score_l = [-r["lam"] for r in rows]
log("  final weights (no decay):")
for s in SEATS:
    for d in ("LOGIC", "SECURITY"):
        a, b = W[s][d]
        lo, hi = omega_ci(a, b)
        log(f"    {s:<7} {d:<9} alpha {a:.0f} beta {b:.0f} omega {a / (a + b):.3f} [{lo:.3f}, {hi:.3f}]")
mx = max(max(r["omega"].values()) for r in rows)
mx2 = max(sum(sorted(r["omega"].values())[-2:]) for r in rows)
mx_jc = max(r["omega"]["JEV"] + r["omega"]["CLAUDE"] for r in rows)
log(f"  largest omega used {mx:.3f}; largest sum of the two heaviest {mx2:.3f}; largest Jev+Claude {mx_jc:.3f}; "
    f"a k=2 REJECT stop needs omega sum >= {B / LLR_REJECT:.4f}, a k=3 APPROVE stop needs {A / LLR_APPROVE:.4f}")
log(f"  HIGH verdicts {sum(r['conf'] == 'HIGH' for r in rows)}; Lambda range {min(r['lam'] for r in rows):+.3f} "
    f"to {max(r['lam'] for r in rows):+.3f}")
log(f"  BA learned {ba(dec_l, Y):.3f} vs uniform {ba(uni_dec, Y):.3f}; AUC of -Lambda learned {auc(score_l, Y):.3f} "
    f"vs uniform {auc(uni_score, Y):.3f}")
d, lo, hi = boot(lambda idx: auc(sub(score_l, idx), sub(Y, idx)) - auc(sub(uni_score, idx), sub(Y, idx)), Y, seed=42)
log(f"  AUC learned minus uniform {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
OBS = d
rows_d, _ = learned(date_order, decay=True)
log(f"  with decay: AUC of -Lambda {auc([-r['lam'] for r in rows_d], Y):.3f}, BA {ba([r['dec'] == 'REJECT' for r in rows_d], Y):.3f}")

# random commit orders
log("\n  200 random commit orders x 6 profile orders:")
rng = random.Random(7)
bad, nchg, mxo, flips = [], [], 0.0, {"LOGIC": 0, "SECURITY": 0}
for _ in range(200):
    order = list(range(N))
    rng.shuffle(order)
    for o in ORDERS:
        rws, _ = learned(order, o)
        dec = [r["dec"] == "REJECT" for r in rws]
        bad.append(ba(dec, Y) - ba(uni_dec, Y))
        ch = [t for t in range(N) if dec[t] != uni_dec[t]]
        nchg.append(len(ch))
        for t in ch:
            flips[DOM[t]] += 1
        mxo = max(mxo, max(max(r["omega"].values()) for r in rws))
bad.sort()
nn = len(bad)
log(f"    BA learned minus uniform: mean {sum(bad) / nn:+.4f} [{bad[int(0.025 * nn)]:+.4f}, {bad[int(0.975 * nn) - 1]:+.4f}]; "
    f"decisions changed per run: mean {sum(nchg) / nn:.2f}, max {max(nchg)}; runs with any change "
    f"{sum(1 for x in nchg if x)}/{nn}; changed decisions by domain {flips}; largest omega in any run {mxo:.3f}")

# controls for the AUC change: labels carrying no information
log("\n  controls for the AUC change (commit-date order, profile order JEV, LAYA, CLAUDE):")


def auc_change(train_labels, score_labels):
    rws, _ = learned(date_order, labels=train_labels)
    sc = [-r["lam"] for r in rws]
    return auc(sc, score_labels) - auc(uni_score, score_labels)


rng = random.Random(8)
shuf, indep, train_only = [], [], []
for _ in range(1000):
    yy = Y[:]
    rng.shuffle(yy)
    shuf.append(auc_change(yy, yy))
    train_only.append(auc_change(yy, Y))
    yi = [rng.random() < 0.5 for _ in range(N)]
    if 0 < sum(yi) < N:
        indep.append(auc_change(yi, yi))
for name, xs in (("shuffled labels, trained and scored on them", shuf),
                 ("independent random labels, trained and scored on them", indep),
                 ("trained on shuffled labels, scored on the real ones", train_only)):
    xs.sort()
    n = len(xs)
    le = sum(1 for x in xs if x <= OBS) / n
    ge = sum(1 for x in xs if x >= OBS) / n
    log(f"    {name}: mean {sum(xs) / n:+.4f} [{xs[int(0.025 * n)]:+.4f}, {xs[int(0.975 * n) - 1]:+.4f}] over {n}; "
        f"share <= observed {OBS:+.3f}: {le:.2f}, share >= observed: {ge:.2f}")

json.dump({"obs_auc_change": OBS}, open(HERE / "part2_learned.json", "w", encoding="utf-8"), indent=1)
