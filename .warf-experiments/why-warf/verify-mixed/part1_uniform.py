"""Part 1: the mixed panel through WaRF as it is (uniform omega 0.5, fixed LLRs), all seat
orders and stopping rules (finding a), robustness to the vote inputs, and the calibrated-vote
diagnostic (finding a').

    PYTHONIOENCODING=utf-8 python -B part1_uniform.py"""
import json
from itertools import permutations, product
from pathlib import Path

from vm_common import (EXP, Y, DOM, N, P, SEATS, A, B, LLR_APPROVE, LLR_REJECT, auc, ba, boot, sub, sign_p,
                       discordant, review, platt_oof, jl, Tee)

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part1_uniform.log")
ORDERS = list(permutations(SEATS))
MODES = ("early", "noearly", "nosprt")


def votes_from(rej):
    return [{s: (-1 if rej[s][t] else 1) for s in rej} for t in range(N)]


def run_uniform(votes, order, mode):
    res = [review(votes[t], {s: 0.5 for s in order}, order, DOM[t], mode) for t in range(N)]
    return res


def summarize(rej_seat, tag, B_=2000):
    """Panel at uniform weights from the seats' REJECT flags; comparisons with the members."""
    votes = votes_from(rej_seat)
    runs = {(o, m): run_uniform(votes, o, m) for o in ORDERS for m in MODES}
    base = runs[(SEATS, "early")]
    same = sum(all((a[0], a[1], round(a[2], 12)) == (b[0], b[1], round(b[2], 12)) for a, b in zip(r, base))
               for r in runs.values())
    n_high = sum(1 for r in runs.values() for x in r if x[1] == "HIGH")
    asked3 = all(len(x[3]) == 3 for r in runs.values() for x in r)
    dec = [x[0] == "REJECT" for x in base]
    lam = [x[2] for x in base]
    score = [-l for l in lam]
    tp = sum(1 for d, t in zip(dec, Y) if d and t)
    log(f"\n  [{tag}] {same}/{len(runs)} runs identical to (JEV,LAYA,CLAUDE)/early; HIGH verdicts {n_high}; "
        f"3 seats asked every time: {asked3}")
    log(f"    Lambda range {min(lam):+.3f} to {max(lam):+.3f}; panel REJECT {sum(dec)} ({tp} later fixed); "
        f"BA {ba(dec, Y):.3f}; AUC of -Lambda {auc(score, Y):.3f}")
    conf = {}
    for x, t in zip(base, Y):
        c = conf.setdefault(x[1], [0, 0])
        c[0] += 1
        c[1] += (x[0] == "REJECT") == t
    log("    confidence: " + ", ".join(f"{k} {v[0]} ({v[1]} right)" for k, v in sorted(conf.items())))
    out = {"ba": ba(dec, Y), "auc": auc(score, Y), "rej": sum(dec), "tp": tp}
    # decision comparisons
    mean_ba = lambda idx: sum(ba(sub(rej_seat[s], idx), sub(Y, idx)) for s in SEATS) / 3  # noqa: E731
    v, lo, hi = boot(lambda idx: ba(sub(dec, idx), sub(Y, idx)), Y, n=B_, seed=21)
    log(f"    panel BA {v:.3f} [{lo:.3f}, {hi:.3f}]")
    for s in SEATS:
        d, lo, hi = boot(lambda idx, s=s: ba(sub(dec, idx), sub(Y, idx)) - ba(sub(rej_seat[s], idx), sub(Y, idx)),
                         Y, n=B_, seed=22)
        dp, plo, phi = boot(lambda idx, s=s: ba(sub(dec, idx), sub(Y, idx)) - ba(sub(rej_seat[s], idx), sub(Y, idx)),
                            Y, n=B_, seed=22, by="pair")
        a, b = discordant(dec, rej_seat[s], Y)
        log(f"    BA minus {s:<7} vote ({ba(rej_seat[s], Y):.3f}): {d:+.3f} [{lo:+.3f}, {hi:+.3f}] "
            f"(pair bootstrap [{plo:+.3f}, {phi:+.3f}]); right only panel/only {s}: {a}/{b}, sign p {sign_p(a, b):.3f}")
        out[f"ba_minus_{s}"] = [d, lo, hi, a, b]
    d, lo, hi = boot(lambda idx: ba(sub(dec, idx), sub(Y, idx)) - mean_ba(idx), Y, n=B_, seed=23)
    log(f"    BA minus mean member ({mean_ba(list(range(N))):.3f}): {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    # ranking comparisons
    for s in SEATS:
        d, lo, hi = boot(lambda idx, s=s: auc(sub(score, idx), sub(Y, idx)) - auc(sub(P[s], idx), sub(Y, idx)),
                         Y, n=B_, seed=24)
        log(f"    AUC(-Lambda) minus AUC({s} p) {auc(P[s], Y):.3f}: {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
        out[f"auc_minus_{s}"] = [d, lo, hi]
    d, lo, hi = boot(lambda idx: auc(sub(score, idx), sub(Y, idx))
                     - sum(auc(sub(P[s], idx), sub(Y, idx)) for s in SEATS) / 3, Y, n=B_, seed=25)
    log(f"    AUC(-Lambda) minus mean member AUC: {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
    return out, dec, score


log("== (a) mixed panel, uniform omega 0.5, fixed LLRs; 6 profile orders x 3 stopping rules")
log(f"  reachable Lambda with 3 seats at omega 0.5: {3 * 0.5 * LLR_REJECT:+.3f} to {3 * 0.5 * LLR_APPROVE:+.3f}"
    f" (B {B:+.3f}, A {A:+.3f}); per-domain thresholds as engine.THETA")
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
main, dec_main, score_main = summarize(REJ, "reported inputs: p > 0.5, Jev from sessions_one")
log(f"    panel REJECT rows equal Claude's REJECT rows: {dec_main == REJ['CLAUDE']}")

# robustness: other Jev runs, Jev at p >= 0.5, Claude at lower thresholds
log("\n== robustness of (a) to the vote inputs")
for x in "AB":
    rr = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "verify" / "refute" / f"rerun_{x}.jsonl")}
    from vm_common import IDS
    pj = [rr[i]["jev"]["round1"]["JEV"]["p_reject"] for i in IDS]
    rj = [rr[i]["jev"]["round1"]["JEV"]["choice"] == "REJECT" for i in IDS]
    alt = dict(REJ, JEV=rj)
    o, d, _ = summarize(alt, f"Jev rerun {x} (stored choice; REJECT {sum(rj)}, BA {ba(rj, Y):.3f})", B_=500)
    log(f"    panel REJECT rows equal Claude's: {d == REJ['CLAUDE']}")
alt = dict(REJ, JEV=[p >= 0.5 for p in P["JEV"]])
o, d, _ = summarize(alt, "Jev votes REJECT at p >= 0.5", B_=500)
for thr in (0.4, 0.3, 0.2):
    alt = dict(REJ, CLAUDE=[p > thr for p in P["CLAUDE"]])
    rc = alt["CLAUDE"]
    o, d, _ = summarize(alt, f"Claude votes REJECT at p > {thr} (REJECT {sum(rc)}, BA {ba(rc, Y):.3f})", B_=500)

# (a') calibrated votes
log("\n== (a') each seat votes REJECT when its out-of-fold Platt-calibrated p > 0.5")
CAL = {s: platt_oof(P[s])[0] for s in SEATS}
RC = {s: [q > 0.5 for q in CAL[s]] for s in SEATS}
votes = votes_from(RC)
runs = {(o, m): run_uniform(votes, o, m) for o in ORDERS for m in MODES}
base = runs[(SEATS, "early")]
same = sum(all((a[0], a[1]) == (b[0], b[1]) for a, b in zip(r, base)) for r in runs.values())
dec = [x[0] == "REJECT" for x in base]
score = [-x[2] for x in base]
log(f"  {same}/18 runs give the same decisions; HIGH {sum(1 for r in runs.values() for x in r if x[1] == 'HIGH')}")
v, lo, hi = boot(lambda idx: ba(sub(dec, idx), sub(Y, idx)), Y, seed=31)
log(f"  majority of calibrated votes: REJECT {sum(dec)}, BA {v:.3f} [{lo:.3f}, {hi:.3f}], AUC of -Lambda {auc(score, Y):.3f}")
for s in SEATS:
    d, lo, hi = boot(lambda idx, s=s: ba(sub(dec, idx), sub(Y, idx)) - ba(sub(RC[s], idx), sub(Y, idx)), Y, seed=32)
    a, b = discordant(dec, RC[s], Y)
    log(f"  BA minus {s} calibrated vote ({ba(RC[s], Y):.3f}): {d:+.3f} [{lo:+.3f}, {hi:+.3f}], {a}/{b}, sign p {sign_p(a, b):.2f}")
d, lo, hi = boot(lambda idx: auc(sub(score, idx), sub(Y, idx)) - auc(sub(P["CLAUDE"], idx), sub(Y, idx)), Y, seed=33)
log(f"  AUC(-Lambda) minus AUC(Claude p): {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")

json.dump({"main": main}, open(HERE / "part1_uniform.json", "w", encoding="utf-8"), indent=1)
