"""Part 0: validate the panel driver on WaRF's stored reviews, then recompute the seat-level
numbers of finding 1 (votes, AUC, calibrated votes, clone rule, correlations).

    PYTHONIOENCODING=utf-8 python -B part0_seats.py"""
import json
import math
from pathlib import Path

from vm_common import (EXP, SEL, IDS, Y, DOM, N, P, SEATS, JEV_CHOICE, auc, auc_pairs, ba, boot, sub,
                       logit, corr, within, platt_oof, fit_logistic, review, sign_p, discordant, jl, Tee)

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part0_seats.log")
AG5 = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
v = lambda c: -1 if c == "REJECT" else 1  # noqa: E731

# ── 0. driver against stored reviews ─────────────────────────────────────────
log("== 0. panel driver replays stored WaRF reviews")
for fn, prof, mode in (("sessions_one.jsonl", ("JEV",), "early"),
                       ("sessions_standard.jsonl", AG5, "early")):
    rs = jl(EXP / "jev-five" / fn)
    ok = {"decision": 0, "confidence": 0, "lambda": 0, "asked": 0}
    for r in rs:
        rd = r["jev"]["round1"]
        # votes only for the agents that were asked; a needed but missing vote would KeyError
        votes = {a: v(rd[a]["choice"]) for a in rd}
        om = {a: 0.5 for a in prof}
        # an agent that was not asked has no stored vote: if the driver asks it, that is a KeyError
        try:
            dec, conf, lam, cast = review(votes, om, prof, r["domain"], mode)
        except KeyError:
            continue
        ok["decision"] += dec == r["decision"]
        ok["confidence"] += conf == r["confidence"]
        ok["lambda"] += abs(round(lam, 4) - r["sprt_lambda"]) < 1e-9
        ok["asked"] += cast == [x["agent"] for x in r["votes"]]
    log(f"  {fn:<26} {len(rs)} reviews; match: " + ", ".join(f"{k} {n}/{len(rs)}" for k, n in ok.items()))

# five Jev with debate, no early stop: is the top-level verdict Round 1 or the final one?
rs = jl(EXP / "jev-five" / "sessions_five.jsonl")
m_final = m_r1 = m_lam1 = m_lam2 = 0
n_deb = 0
for r in rs:
    r1 = {a: v(r["jev"]["round1"][a]["choice"]) for a in AG5}
    om = {a: 0.5 for a in AG5}
    d1, c1, l1, _ = review(r1, om, AG5, r["domain"], "noearly")
    m_lam1 += abs(round(l1, 4) - r["sprt_lambda"]) < 1e-9
    m_r1 += (d1, c1) == (r["decision"], r["confidence"])
    if c1 == "HIGH":
        fd, fc = d1, c1
    else:
        n_deb += 1
        r2 = {x["agent"]: x["vote"] for x in r["debate"]["votes"]}
        assert all(r2[a] == v(r["jev"]["round2"][a]["choice"]) for a in AG5)
        fd, fc, l2, _ = review(r2, om, AG5, r["domain"], "noearly")
        m_lam2 += abs(round(l2, 4) - r["debate"]["sprt_lambda"]) < 1e-9
    m_final += (fd, fc) == (r["decision"], r["confidence"])
log(f"  sessions_five.jsonl        100 reviews; Round-1 Lambda matches {m_lam1}/100; top-level verdict equals "
    f"the recomputed final verdict {m_final}/100, the Round-1 verdict {m_r1}/100; "
    f"{n_deb} debated, Round-2 Lambda matches {m_lam2}/{n_deb}")

# AUC implementations agree
for s in SEATS:
    assert abs(auc(P[s], Y) - auc_pairs(P[s], Y)) < 1e-12
tie = [round(p, 1) for p in P["JEV"]]
assert abs(auc(tie, Y) - auc_pairs(tie, Y)) < 1e-12
log("  rank AUC equals pairwise AUC on the three seats and on a heavily tied score")

# ── 1. seats ──────────────────────────────────────────────────────────────────
log("\n== 1. seats (p > 0.5 votes; AUC of p; 2000 bootstrap resamples within labels)")
assert all((c == "REJECT") == (p > 0.5) for c, p in zip(JEV_CHOICE, P["JEV"]))
log("  Jev's stored choice equals p > 0.5 on all 100 commits: True")
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
REJ_GE = {s: [p >= 0.5 for p in P[s]] for s in SEATS}
out = {}
for s in SEATS:
    r = REJ[s]
    tp = sum(1 for a, t in zip(r, Y) if a and t)
    a_, lo, hi = boot(lambda idx, s=s: auc(sub(P[s], idx), sub(Y, idx)), Y, seed=11)
    ap_, plo, phi = boot(lambda idx, s=s: auc(sub(P[s], idx), sub(Y, idx)), Y, seed=11, by="pair")
    out[s] = {"rej": sum(r), "tp": tp, "ba": ba(r, Y), "auc": [a_, lo, hi]}
    log(f"  {s:<7} REJECT {sum(r):>2} ({tp} later fixed, {sum(r) - tp} never fixed), vote BA {ba(r, Y):.3f}; "
        f"p >= 0.5: REJECT {sum(REJ_GE[s])}, BA {ba(REJ_GE[s], Y):.3f}; "
        f"AUC of p {a_:.3f} [{lo:.3f}, {hi:.3f}] (pair bootstrap [{plo:.3f}, {phi:.3f}])")

# calibration, leave-one-matched-pair-out Platt on logit p
log("\n  out-of-fold Platt calibration (leave one matched pair out), vote = calibrated p > 0.5")
CAL = {}
for s in SEATS:
    cp, slopes = platt_oof(P[s])
    cps, _ = platt_oof(P[s], smooth=True)
    CAL[s] = cp
    a_full, b_full = fit_logistic([logit(p) for p in P[s]], Y)
    rc = [q > 0.5 for q in cp]
    rcs = [q > 0.5 for q in cps]
    log(f"  {s:<7} full-data fit a {a_full:+.3f} slope {b_full:.3f} (folds {min(slopes):.3f} to {max(slopes):.3f}); "
        f"calibrated REJECT {sum(rc)} ({sum(1 for a, t in zip(rc, Y) if a and t)} later fixed), BA {ba(rc, Y):.3f}; "
        f"with Platt target smoothing: REJECT {sum(rcs)}, BA {ba(rcs, Y):.3f}; "
        f"AUC of calibrated p {auc(cp, Y):.3f}")

# disagreement (clone rule) and correlations
log("\n  clone rule (SPECIFICATION 3.1.2: min pairwise disagreement >= 0.15), raw p > 0.5 votes / calibrated votes")
L = {s: [logit(p) for p in P[s]] for s in SEATS}
CR = {s: [q > 0.5 for q in CAL[s]] for s in SEATS}
for i, s1 in enumerate(SEATS):
    for s2 in SEATS[i + 1:]:
        dis = sum(a != b for a, b in zip(REJ[s1], REJ[s2])) / N
        disc = sum(a != b for a, b in zip(CR[s1], CR[s2])) / N
        log(f"  {s1}-{s2:<7} disagree {dis:.2f} (calibrated {disc:.2f}); logit corr {corr(L[s1], L[s2]):+.2f}, "
            f"within label {corr(within(L[s1], Y), within(L[s2], Y)):+.2f}; "
            f"p corr {corr(P[s1], P[s2]):+.2f}")

# vote-level paired comparisons between seats
a, b = discordant(REJ["JEV"], REJ["CLAUDE"], Y)
log(f"\n  votes right only Jev / only Claude: {a}/{b}, sign p {sign_p(a, b):.2f}")
claude_rej = [i for i in range(N) if REJ["CLAUDE"][i]]
log(f"  Claude's REJECT rows: {claude_rej}; Jev REJECT on all of them: {all(REJ['JEV'][i] for i in claude_rej)}; "
    f"labels {[Y[i] for i in claude_rej]}")

json.dump({"seats": out, "cal": CAL}, open(HERE / "part0_seats.json", "w", encoding="utf-8"), indent=1)
