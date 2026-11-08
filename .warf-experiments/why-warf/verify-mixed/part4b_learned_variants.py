"""Part 4b: which votes train the Betas in the learned-omega log-odds runs (commit-date order):
raw votes (p > 0.5) or calibrated votes (calibrated p > 0.5).

    PYTHONIOENCODING=utf-8 python -B part4b_learned_variants.py"""
from itertools import permutations
from pathlib import Path
from vm_common import N, P, SEATS, Y, logit, platt_oof, stream, by_row, ba, auc, load_dates, Tee

log = Tee(Path(__file__).resolve().parent / "part4_learned_variants.log")
dates, _ = load_dates()
order = sorted(range(N), key=lambda t: (dates[t], t))
CALP = {s: platt_oof(P[s])[0] for s in SEATS}
REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
RC = {s: [q > 0.5 for q in CALP[s]] for s in SEATS}
V = [{s: (-1 if REJ[s][t] else 1) for s in SEATS} for t in range(N)]
VC = [{s: (-1 if RC[s][t] else 1) for s in SEATS} for t in range(N)]
LC = [{s: -logit(CALP[s][t]) for s in SEATS} for t in range(N)]
LR = [{s: -logit(P[s][t]) for s in SEATS} for t in range(N)]
for tag, votes, llr in (("cal llr, Betas from raw votes", V, LC), ("cal llr, Betas from cal votes", VC, LC),
                        ("raw llr, Betas from raw votes", V, LR), ("raw llr, Betas from cal votes", VC, LR)):
    for mode in ("early", "nosprt"):
        for prof in permutations(SEATS):
            res, W = stream(order, votes, prof_order=prof, mode=mode, llr=llr)
            rows = by_row(res)
            dec = [r["dec"] == "REJECT" for r in rows]
            sc = [-r["lam"] for r in rows]
            log(f"{tag:<30} {mode:<7} {','.join(prof):<18} BA {ba(dec, Y):.3f} AUC {auc(sc, Y):.3f} "
                f"REJECT {sum(dec)} HIGH {sum(r['conf'] == 'HIGH' for r in rows)}")
            if mode == "nosprt":
                break
