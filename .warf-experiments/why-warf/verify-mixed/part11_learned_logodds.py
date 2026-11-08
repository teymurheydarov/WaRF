"""Part 11: do learned weights add anything to the log-odds panel? Paired comparison, commit-date
order, learned omega against uniform omega (every seat votes, no boundary), raw and calibrated.

    PYTHONIOENCODING=utf-8 python -B part11_learned_logodds.py"""
from pathlib import Path
from vm_common import (N, P, SEATS, Y, DOM, logit, platt_oof, stream, by_row, review_llr, ba, auc, boot, sub,
                       discordant, sign_p, load_dates, Tee)

log = Tee(Path(__file__).resolve().parent / "part11_learned_logodds.log")
dates, _ = load_dates()
order = sorted(range(N), key=lambda t: (dates[t], t))
CALP = {s: platt_oof(P[s])[0] for s in SEATS}
V = [{s: (-1 if P[s][t] > 0.5 else 1) for s in SEATS} for t in range(N)]
VC = [{s: (-1 if CALP[s][t] > 0.5 else 1) for s in SEATS} for t in range(N)]
for tag, llr, votes in (("raw", [{s: -logit(P[s][t]) for s in SEATS} for t in range(N)], V),
                        ("calibrated, Betas from raw votes", [{s: -logit(CALP[s][t]) for s in SEATS} for t in range(N)], V),
                        ("calibrated, Betas from calibrated votes", [{s: -logit(CALP[s][t]) for s in SEATS} for t in range(N)], VC)):
    uni = [review_llr(llr[t], {s: 0.5 for s in SEATS}, SEATS, DOM[t], "nosprt") for t in range(N)]
    lr = by_row(stream(order, votes, mode="nosprt", llr=llr)[0])
    du = [x[0] == "REJECT" for x in uni]
    dl = [r["dec"] == "REJECT" for r in lr]
    su = [-x[2] for x in uni]
    sl = [-r["lam"] for r in lr]
    d, lo, hi = boot(lambda idx: ba(sub(dl, idx), sub(Y, idx)) - ba(sub(du, idx), sub(Y, idx)), Y, seed=71)
    a, b = discordant(dl, du, Y)
    da, alo, ahi = boot(lambda idx: auc(sub(sl, idx), sub(Y, idx)) - auc(sub(su, idx), sub(Y, idx)), Y, seed=72)
    log(f"  {tag:<40} BA learned {ba(dl, Y):.3f} vs uniform {ba(du, Y):.3f}: {d:+.3f} [{lo:+.3f}, {hi:+.3f}], "
        f"right only learned/only uniform {a}/{b}, sign p {sign_p(a, b):.2f}; AUC {auc(sl, Y):.3f} vs {auc(su, Y):.3f}: "
        f"{da:+.3f} [{alo:+.3f}, {ahi:+.3f}]")
