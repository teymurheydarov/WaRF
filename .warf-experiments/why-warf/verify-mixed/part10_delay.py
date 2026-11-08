"""Part 10: learned weights when labels arrive late (commit-date order). B-SZZ labels need a
later fix, so a label reaches WaRF months after the review; here each label is applied only
once `delay` days have passed since its commit's author date.

    PYTHONIOENCODING=utf-8 python -B part10_delay.py"""
from datetime import timedelta
from pathlib import Path
from vm_common import (N, P, SEATS, Y, DOM, DOMAINS, GAMMA, review, bayesian_update, ba, auc, load_dates, Tee)

log = Tee(Path(__file__).resolve().parent / "part10_delay.log")
dates, _ = load_dates()
order = sorted(range(N), key=lambda t: (dates[t], t))
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
V = [{s: (-1 if REJ[s][t] else 1) for s in SEATS} for t in range(N)]
uni = [review(V[t], {s: 0.5 for s in SEATS}, SEATS, DOM[t]) for t in range(N)]
for days in (0, 30, 180, 365):
    W = {s: {d: [1.0, 1.0] for d in DOMAINS} for s in SEATS}
    pending, out, applied = [], [None] * N, 0
    for t in order:
        due = [q for q in pending if q[0] <= dates[t]]
        pending = [q for q in pending if q[0] > dates[t]]
        for _, u, cast in sorted(due, key=lambda q: (q[0], q[1])):
            for s in cast:
                a, b = W[s][DOM[u]]
                W[s][DOM[u]] = list(bayesian_update(a, b, V[u][s] == (-1 if Y[u] else 1), GAMMA))
            applied += 1
        om = {s: W[s][DOM[t]][0] / sum(W[s][DOM[t]]) for s in SEATS}
        out[t] = review(V[t], om, SEATS, DOM[t])
        pending.append((dates[t] + timedelta(days=days), t, out[t][3]))
    chg = sum(1 for t in range(N) if out[t][0] != uni[t][0])
    log(f"  label delay {days:>3} days: labels applied before the last review {applied}; decisions differing from "
        f"uniform {chg}; BA {ba([x[0] == 'REJECT' for x in out], Y):.3f}; AUC of -Lambda {auc([-x[2] for x in out], Y):.3f}")
