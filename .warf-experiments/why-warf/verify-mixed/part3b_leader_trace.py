"""Part 3b: leader sequence of the 'shadow' route in commit-date order, profile order LAYA, JEV,
CLAUDE (upper case = LOGIC review, lower case = SECURITY review), and the SECURITY omegas.

    PYTHONIOENCODING=utf-8 python -B part3b_leader_trace.py"""
from pathlib import Path
from vm_common import N, P, SEATS, DOM, stream, load_dates, Tee

log = Tee(Path(__file__).resolve().parent / "part3_leader_trace.log")
dates, _ = load_dates()
order = sorted(range(N), key=lambda t: (dates[t], t))
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
votes = [{s: (-1 if REJ[s][t] else 1) for s in SEATS} for t in range(N)]
res, W = stream(order, votes, prof_order=("LAYA", "JEV", "CLAUDE"), route="shadow")
log("".join(r["leader"][0] if DOM[r["t"]] == "LOGIC" else r["leader"][0].lower() for r in res))
log("SECURITY positions", [j + 1 for j, r in enumerate(res) if DOM[r["t"]] == "SECURITY"])
for j, r in enumerate(res):
    if DOM[r["t"]] == "SECURITY":
        log(j + 1, {k: round(v, 3) for k, v in r["omega"].items()}, r["leader"])
