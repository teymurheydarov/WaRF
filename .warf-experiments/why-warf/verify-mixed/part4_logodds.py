"""Part 4: IDEAS.md 'Use the probability' (finding d): each seat adds omega * its log-odds of
APPROVE; the decision compares the omega-weighted mean log-odds with theta. Raw and out-of-fold
calibrated p; uniform and learned omega; WaRF's A/B boundaries on the log-odds Lambda.

    PYTHONIOENCODING=utf-8 python -B part4_logodds.py"""
import json
import math
from itertools import permutations
from pathlib import Path

from vm_common import (Y, DOM, N, P, SEATS, A, B, auc, ba, boot, sub, logit, review, review_llr, stream,
                       by_row, load_dates, platt_oof, sign_p, discordant, Tee)

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part4_logodds.log")
ORDERS = list(permutations(SEATS))
MODES = ("early", "noearly", "nosprt")
dates, _ = load_dates()
date_order = sorted(range(N), key=lambda t: (dates[t], t))
ALL = list(range(N))

CALP = {s: platt_oof(P[s])[0] for s in SEATS}
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
RC = {s: [q > 0.5 for q in CALP[s]] for s in SEATS}
VOTES = [{s: (-1 if REJ[s][t] else 1) for s in SEATS} for t in range(N)]
VOTES_C = [{s: (-1 if RC[s][t] else 1) for s in SEATS} for t in range(N)]
LLR_RAW = [{s: -logit(P[s][t]) for s in SEATS} for t in range(N)]        # log-odds of APPROVE
LLR_CAL = [{s: -logit(CALP[s][t]) for s in SEATS} for t in range(N)]

# vote panel (uniform) for comparisons
VP = [review(VOTES[t], {s: 0.5 for s in SEATS}, SEATS, DOM[t]) for t in range(N)]
vp_dec = [x[0] == "REJECT" for x in VP]
vp_score = [-x[2] for x in VP]


def uniform_llr(llr, order=SEATS, mode="nosprt"):
    return [review_llr(llr[t], {s: 0.5 for s in SEATS}, order, DOM[t], mode) for t in range(N)]


def mean_auc(idx):
    return sum(auc(sub(P[s], idx), sub(Y, idx)) for s in SEATS) / 3


def report(tag, res, member_votes):
    dec = [x[0] == "REJECT" for x in res]
    score = [-x[2] for x in res]
    tp = sum(1 for d, t in zip(dec, Y) if d and t)
    v, lo, hi = boot(lambda idx: auc(sub(score, idx), sub(Y, idx)), Y, seed=51)
    log(f"\n  [{tag}] AUC of -Lambda {v:.3f} [{lo:.3f}, {hi:.3f}]")
    for name, f in (("Claude p", lambda idx: auc(sub(P["CLAUDE"], idx), sub(Y, idx))),
                    ("Jev p", lambda idx: auc(sub(P["JEV"], idx), sub(Y, idx))),
                    ("Laya p", lambda idx: auc(sub(P["LAYA"], idx), sub(Y, idx))),
                    ("mean member", mean_auc),
                    ("vote panel -Lambda", lambda idx: auc(sub(vp_score, idx), sub(Y, idx)))):
        d, lo, hi = boot(lambda idx, f=f: auc(sub(score, idx), sub(Y, idx)) - f(idx), Y, seed=52)
        log(f"    AUC minus {name:<19} {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    v, lo, hi = boot(lambda idx: ba(sub(dec, idx), sub(Y, idx)), Y, seed=53)
    log(f"    decisions: REJECT {sum(dec)} ({tp} later fixed); BA {v:.3f} [{lo:.3f}, {hi:.3f}]")
    for name, other in (("Claude vote", member_votes["CLAUDE"]), ("Jev vote", member_votes["JEV"]),
                        ("vote panel", vp_dec)):
        d, lo, hi = boot(lambda idx, o=other: ba(sub(dec, idx), sub(Y, idx)) - ba(sub(o, idx), sub(Y, idx)), Y, seed=54)
        a, b = discordant(dec, other, Y)
        log(f"    BA minus {name:<12} ({ba(other, Y):.3f}) {d:+.3f} [{lo:+.3f}, {hi:+.3f}], {a}/{b}, sign p {sign_p(a, b):.2f}")
    d, lo, hi = boot(lambda idx: ba(sub(dec, idx), sub(Y, idx))
                     - sum(ba(sub(member_votes[s], idx), sub(Y, idx)) for s in SEATS) / 3, Y, seed=55)
    log(f"    BA minus mean member vote ({sum(ba(member_votes[s], Y) for s in SEATS) / 3:.3f}) {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    return dec, score


log("== (d) log-odds variant")
log("  mean log-odds of APPROVE per seat (raw): " + ", ".join(
    f"{s} {sum(-logit(p) for p in P[s]) / N:+.2f}" for s in SEATS))
log("  share of commits where the seat's log-odds point to APPROVE (raw): " + ", ".join(
    f"{s} {sum(p < 0.5 for p in P[s])}" for s in SEATS))
raw = uniform_llr(LLR_RAW)
cal = uniform_llr(LLR_CAL)
dec_raw, sc_raw = report("raw log-odds, uniform omega, every vote", raw, REJ)
dec_cal, sc_cal = report("calibrated log-odds (out of fold), uniform omega, every vote", cal, RC)

# boundaries: HIGH verdicts and changed decisions for every order and stopping rule
log("\n  WaRF's A/B boundaries on the log-odds Lambda (uniform omega):")
for tag, llr in (("raw", LLR_RAW), ("calibrated", LLR_CAL)):
    ref = [x[0] for x in uniform_llr(llr, SEATS, "nosprt")]
    cells = []
    for o in ORDERS:
        for m in ("early", "noearly"):
            rr = uniform_llr(llr, o, m)
            hi = [t for t in range(N) if rr[t][1] == "HIGH"]
            right = sum(1 for t in hi if (rr[t][0] == "REJECT") == Y[t])
            chg = sum(1 for t in range(N) if rr[t][0] != ref[t])
            cells.append((",".join(x[0] for x in o), m, len(hi), right, chg))
    log(f"    {tag}: (order, mode, HIGH, HIGH right, decisions changed vs all-vote synthesis) "
        + "; ".join(f"{c[0]} {c[1]} {c[2]}/{c[3]}/{c[4]}" for c in cells))

# learned omega in commit-date order (Betas updated by each seat's vote correctness)
log("\n  learned omega, commit-date order (vote correctness updates the Betas), per stopping rule:")
for tag, llr, votes, mv in (("raw", LLR_RAW, VOTES, REJ), ("calibrated", LLR_CAL, VOTES_C, RC)):
    for mode in MODES:
        res, W = stream(date_order, votes, mode=mode, llr=llr)
        rows = by_row(res)
        dec = [r["dec"] == "REJECT" for r in rows]
        score = [-r["lam"] for r in rows]
        nhigh = sum(1 for r in rows if r["conf"] == "HIGH")
        line = f"    {tag:<10} {mode:<8} BA {ba(dec, Y):.3f}, AUC {auc(score, Y):.3f}, REJECT {sum(dec)}, HIGH {nhigh}"
        if mode == "nosprt":
            for name, other in (("Claude vote", mv["CLAUDE"]),):
                d, lo, hi = boot(lambda idx, o=other: ba(sub(dec, idx), sub(Y, idx)) - ba(sub(o, idx), sub(Y, idx)), Y, seed=56)
                a, b = discordant(dec, other, Y)
                line += f"; minus {name} {d:+.3f} [{lo:+.3f}, {hi:+.3f}] {a}/{b} p {sign_p(a, b):.2f}"
            d, lo, hi = boot(lambda idx: ba(sub(dec, idx), sub(Y, idx))
                             - sum(ba(sub(mv[s], idx), sub(Y, idx)) for s in SEATS) / 3, Y, seed=57)
            line += f"; minus mean member {d:+.3f} [{lo:+.3f}, {hi:+.3f}]"
        log(line)

# equal-weight logit average of unit-SD logits (why_five.py's 0.768), recomputed
log("\n  equal-weight average of unit-SD logits (the earlier 0.768):")
Z = {}
for s in SEATS:
    l = [logit(p) for p in P[s]]
    mu = sum(l) / N
    sd = math.sqrt(sum((x - mu) ** 2 for x in l) / N)
    Z[s] = [(x - mu) / sd for x in l]
za = [sum(Z[s][t] for s in SEATS) / 3 for t in range(N)]
v, lo, hi = boot(lambda idx: auc(sub(za, idx), sub(Y, idx)), Y, seed=58)
log(f"    AUC {v:.3f} [{lo:.3f}, {hi:.3f}]")
for name, f in (("Claude p", lambda idx: auc(sub(P["CLAUDE"], idx), sub(Y, idx))), ("mean member", mean_auc)):
    d, lo, hi = boot(lambda idx, f=f: auc(sub(za, idx), sub(Y, idx)) - f(idx), Y, seed=59)
    dp, plo, phi = boot(lambda idx, f=f: auc(sub(za, idx), sub(Y, idx)) - f(idx), Y, seed=59, by="pair")
    log(f"    minus {name:<12} {d:+.3f} [{lo:+.3f}, {hi:+.3f}] (pair bootstrap [{plo:+.3f}, {phi:+.3f}])")
# other reasonable weightings
lr = {s: [logit(p) for p in P[s]] for s in SEATS}
for tag, sc in (("raw logit sum", [sum(lr[s][t] for s in SEATS) for t in ALL]),
                ("calibrated logit sum", [sum(logit(CALP[s][t]) for s in SEATS) for t in ALL]),
                ("mean of p", [sum(P[s][t] for s in SEATS) / 3 for t in ALL]),
                ("mean of ranks", None)):
    if sc is None:
        rk = {}
        for s in SEATS:
            o = sorted(ALL, key=lambda t: P[s][t])
            r = [0] * N
            for j, t in enumerate(o):
                r[t] = j
            rk[s] = r
        sc = [sum(rk[s][t] for s in SEATS) for t in ALL]
    d, lo, hi = boot(lambda idx, sc=sc: auc(sub(sc, idx), sub(Y, idx)) - auc(sub(P["CLAUDE"], idx), sub(Y, idx)), Y, seed=60)
    log(f"    {tag:<22} AUC {auc(sc, Y):.3f}; minus Claude {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
