"""Method choices that could drive the Jev/Laya result: tie handling, seat order, vote threshold,
Lambda at the crossing, Round 1 against the final verdict."""
import math
import random
import sys
from itertools import permutations

sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                                         # noqa: E402
import boot100 as BB                                       # noqa: E402
from systems100 import S, P5, PL, truth, sel, five, lay    # noqa: E402

ids = [s["id"] for s in sel]
AG = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")


def aurc_tiebreak(correct, key, mode):
    """AURC with ties broken in favour of right verdicts ('opt'), against ('pes'), or averaged."""
    if mode == "avg":
        return V.aurc(V.curve(correct, key))
    sgn = 1 if mode == "opt" else -1
    k2 = [(key[i], sgn * correct[i]) for i in range(len(key))]
    return V.aurc(V.curve(correct, k2))


print("1. Tie handling (AURC): averaged / optimistic / pessimistic")
for nm in ("jev_single", "jev5_R1_band", "jev5_R1_bandonly", "jevdef_R1_band", "jev5_fin_band", "laya_single", "laya5_R1_band",
           "jev5_seat_SKEPTIC", "claude"):
    s = S[nm]
    a = [aurc_tiebreak(s["correct"], s["c"], m) for m in ("avg", "opt", "pes")]
    print(f"   {nm:<20} {a[0]:.3f} / {a[1]:.3f} / {a[2]:.3f}")
print("   worst case for the claim: panel optimistic minus single pessimistic:")
for X, Y in (("jev5_R1_band", "jev_single"), ("jev5_R1_bandonly", "jev_single"), ("jevdef_R1_band", "jev_single"),
             ("jev5_fin_band", "jev_single"), ("laya5_R1_band", "laya_single"), ("jev5_R1_band", "jev5_seat_SKEPTIC")):
    d = aurc_tiebreak(S[X]["correct"], S[X]["c"], "opt") - aurc_tiebreak(S[Y]["correct"], S[Y]["c"], "pes")
    print(f"   {X:<18} - {Y:<18} {d:+.3f}")

print("\n2. Seat order (uniform weights: any order is a valid WaRF order; the five-run Round-1 votes)")
for label, M, key in (("Jev", five, "jev"), ("Laya", lay, "five")):
    ref = "jev_single" if label == "Jev" else "laya_single"
    a_ref = V.aurc(V.curve(S[ref]["correct"], S[ref]["c"]))
    res = {}
    for perm in permutations(AG):
        d, c = [], []
        for i in ids:
            r = M[i]
            votes = {v["agent"]: v["vote"] for v in r["votes"]}
            vv = [votes[a] for a in perm]
            dec, band, lam, norm, k = V.warf_round(vv, [0.5] * 5, r["domain"], early_stop=False)
            d.append(dec)
            c.append((V.BAND_RANK[band], round(abs(lam), 6)))
        cor = [1 if x == t else 0 for x, t in zip(d, truth)]
        a = V.aurc(V.curve(cor, c))
        res[perm[-1]] = res.get(perm[-1], []) + [(a, sum(cor), sum(1 for x in c if x[0] == 2), V.trust_auroc(cor, c))]
    allv = [x[0] for v in res.values() for x in v]
    print(f"   {label}: single-agent AURC {a_ref:.3f}; band AURC over all 120 seat orders {min(allv):.3f} to {max(allv):.3f}")
    for last, v in res.items():
        print(f"      last seat {last:<13} AURC {v[0][0]:.3f} right {v[0][1]} HIGH {v[0][2]} trust {v[0][3]:.3f}"
              f"  (identical over the 24 orders with this last seat: {len({round(x[0], 9) for x in v}) == 1})")

print("\n3. Vote threshold: every vote recomputed as REJECT if p > t (WaRF votes with t = 0.5, the argmax)")
for label, M, key, ref_p in (("Jev", five, "jev", S["jev_single"]["p"]), ("Laya", lay, "five", S["laya_single"]["p"])):
    for t in (0.3, 0.4, 0.5, 0.6, 0.7):
        d, c = [], []
        for i in ids:
            r = M[i]
            vv = [(-1 if r[key]["round1"][a]["p_reject"] > t else 1) for a in AG]
            dec, band, lam, norm, k = V.warf_round(vv, [0.5] * 5, r["domain"], early_stop=False)
            d.append(dec)
            c.append((V.BAND_RANK[band], round(abs(lam), 6)))
        cor = [1 if x == y else 0 for x, y in zip(d, truth)]
        sd = [(-1 if p > t else 1) for p in ref_p]
        scor = [1 if x == y else 0 for x, y in zip(sd, truth)]
        sc = [round(abs(p - t), 9) for p in ref_p]
        ap, asg = V.aurc(V.curve(cor, c)), V.aurc(V.curve(scor, sc))
        print(f"   {label} t={t}: panel acc {sum(cor) / 100:.2f} AURC {ap:.3f} trust {V.trust_auroc(cor, c):.3f} | "
              f"single acc {sum(scor) / 100:.2f} AURC {asg:.3f} trust {V.trust_auroc(scor, sc):.3f} | diff {ap - asg:+.3f}")

print("\n4. Lambda at the crossing vs after every vote; Round 1 vs final (point AURC)")
for nm in ("jev5_R1_band", "jev5_R1_band_lamcross", "jev5_fin_band", "laya5_R1_band", "laya5_R1_band_lamcross", "laya5_fin_band"):
    print(f"   {nm:<24} {V.aurc(V.curve(S[nm]['correct'], S[nm]['c'])):.3f}")

print("\n5. Excess AURC (AURC minus the oracle AURC at the same accuracy): ranking quality only")
for nm in ("jev_single", "jev_rerunA", "jev_rerunB", "jev5_R1_band", "jevdef_R1_band", "jev5_fin_band", "jev5_seat_SKEPTIC",
           "laya_single", "laya5_R1_band", "claude"):
    s = S[nm]
    a = V.aurc(V.curve(s["correct"], s["c"]))
    o = V.aurc(V.curve(s["correct"], s["correct"]))
    print(f"   {nm:<20} acc {sum(s['correct']) / 100:.2f} AURC {a:.3f} oracle {o:.3f} excess {a - o:.3f} random {1 - sum(s['correct']) / 100:.3f}")
