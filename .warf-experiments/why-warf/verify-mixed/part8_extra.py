"""Part 8: remaining checks.
  - early stopping on the log-odds Lambda with learned omega: commit-date order (every profile
    order) and random commit orders, effect on BA;
  - --max-agents 1: does the final leader stay the seat that led early?
  - SECURITY flip bar of synthesis with three seats.

    PYTHONIOENCODING=utf-8 python -B part8_extra.py"""
import random
from itertools import permutations
from pathlib import Path

from vm_common import Y, DOM, N, P, SEATS, ba, auc, logit, stream, by_row, platt_oof, load_dates, synthesis, Tee

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part8_extra.log")
ORDERS = list(permutations(SEATS))
dates, _ = load_dates()
date_order = sorted(range(N), key=lambda t: (dates[t], t))
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
VOTES = [{s: (-1 if REJ[s][t] else 1) for s in SEATS} for t in range(N)]
CALP = {s: platt_oof(P[s])[0] for s in SEATS}
LLR = {"raw": [{s: -logit(P[s][t]) for s in SEATS} for t in range(N)],
       "calibrated": [{s: -logit(CALP[s][t]) for s in SEATS} for t in range(N)]}

log("== early stopping on the log-odds Lambda, learned omega")
for tag, llr in LLR.items():
    cells = []
    for o in ORDERS:
        e, _ = stream(date_order, VOTES, prof_order=o, mode="early", llr=llr)
        ne, _ = stream(date_order, VOTES, prof_order=o, mode="nosprt", llr=llr)
        e, ne = by_row(e), by_row(ne)
        cells.append((sum(r["conf"] == "HIGH" for r in e), sum(a["dec"] != b["dec"] for a, b in zip(e, ne)),
                      ba([r["dec"] == "REJECT" for r in e], Y)))
    log(f"  {tag:<10} commit-date order, per profile order (HIGH, decisions changed, BA): {cells}")
rng = random.Random(29)
for tag, llr in LLR.items():
    d_ba, n_chg, hi = [], [], []
    for _ in range(200):
        order = list(range(N))
        rng.shuffle(order)
        for o in ORDERS:
            e, _ = stream(order, VOTES, prof_order=o, mode="early", llr=llr)
            ne, _ = stream(order, VOTES, prof_order=o, mode="nosprt", llr=llr)
            e, ne = by_row(e), by_row(ne)
            d_ba.append(ba([r["dec"] == "REJECT" for r in e], Y) - ba([r["dec"] == "REJECT" for r in ne], Y))
            n_chg.append(sum(a["dec"] != b["dec"] for a, b in zip(e, ne)))
            hi.append(sum(r["conf"] == "HIGH" for r in e))
    d_ba.sort()
    n = len(d_ba)
    log(f"  {tag:<10} 1200 random orders: HIGH per run {min(hi)} to {max(hi)} (mean {sum(hi) / n:.1f}); runs with a changed "
        f"decision {sum(1 for x in n_chg if x)}/{n} (max {max(n_chg)} per run); BA early minus no boundary "
        f"mean {sum(d_ba) / n:+.4f} [{d_ba[int(0.025 * n)]:+.3f}, {d_ba[int(0.975 * n) - 1]:+.3f}]")

log("\n== --max-agents 1 (route 'only'): is the final leader the seat that led early?")
rng = random.Random(31)
same5 = same20 = first_right = tot = 0
for _ in range(200):
    order = list(range(N))
    rng.shuffle(order)
    for o in ORDERS:
        res, W = stream(order, VOTES, prof_order=o, route="only")
        fin = {s: W[s]["LOGIC"][0] / sum(W[s]["LOGIC"]) for s in SEATS}
        fl = sorted(o, key=lambda s: fin[s], reverse=True)[0]
        logic = [r for r in res if DOM[r["t"]] == "LOGIC"]
        same5 += logic[5]["leader"] == fl
        same20 += logic[20]["leader"] == fl
        # the first seat that was right when asked (LOGIC)
        fr = next((r["leader"] for r in logic if VOTES[r["t"]][r["leader"]] == (-1 if Y[r["t"]] else 1)), None)
        first_right += fr == fl
        tot += 1
log(f"  final LOGIC leader equals the leader at the 6th LOGIC review in {same5 / tot:.0%}, at the 21st in "
    f"{same20 / tot:.0%}; equals the first seat that was right when asked in {first_right / tot:.0%} of {tot} runs")

log("\n== synthesis with three seats: when does one seat outvote two (theta per domain)?")
for dom in ("LOGIC", "SECURITY", "PERFORMANCE"):
    # one seat with weight w votes against two seats of weight 0.5 each
    out = []
    for lone in (-1, 1):
        w = 0.0
        while w <= 1.0001:
            dec, _, _ = synthesis([lone, -lone, -lone], [w, 0.5, 0.5], dom)
            if (dec.value == "REJECT") == (lone == -1):
                break
            w += 0.0005
        out.append(f"lone {'REJECT' if lone == -1 else 'APPROVE'} wins from omega {w:.3f} (others 0.5 + 0.5)")
    log(f"  {dom:<12} " + "; ".join(out))
