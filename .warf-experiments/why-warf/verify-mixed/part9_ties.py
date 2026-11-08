"""Part 9: tie handling. The vote panel's -Lambda takes only three values, so its AUC depends on
how ties are counted; Claude's p has 41 distinct values. Strict (ties lose), half (standard),
lenient (ties win), and the comparison with Claude's p under each.

    PYTHONIOENCODING=utf-8 python -B part9_ties.py"""
from pathlib import Path

from vm_common import Y, DOM, N, P, SEATS, review, boot, sub, Tee

HERE = Path(__file__).resolve().parent
log = Tee(HERE / "part9_ties.log")


def auc_t(score, y, tie):
    pos = [s for s, t in zip(score, y) if t]
    neg = [s for s, t in zip(score, y) if not t]
    return sum((p > q) + tie * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


REJ = {s: [p > 0.5 for p in P[s]] for s in SEATS}
vp = [-review({s: (-1 if REJ[s][t] else 1) for s in SEATS}, {s: 0.5 for s in SEATS}, SEATS, DOM[t])[2] for t in range(N)]
log(f"== tie handling; distinct values: vote panel {len(set(vp))}, Claude p {len(set(P['CLAUDE']))}, "
    f"Jev p {len(set(P['JEV']))}, Laya p {len(set(P['LAYA']))}")
for tie, name in ((0.0, "strict"), (0.5, "half"), (1.0, "lenient")):
    a = {s: auc_t(P[s], Y, tie) for s in SEATS}
    v = auc_t(vp, Y, tie)
    d, lo, hi = boot(lambda idx: auc_t(sub(vp, idx), sub(Y, idx), tie) - auc_t(sub(P["CLAUDE"], idx), sub(Y, idx), tie),
                     Y, n=1000, seed=61)
    log(f"  {name:<8} vote panel {v:.3f}; Claude {a['CLAUDE']:.3f}, Jev {a['JEV']:.3f}, Laya {a['LAYA']:.3f}; "
        f"vote panel minus Claude {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
# best case for the vote panel: its ties lenient, Claude's strict
d, lo, hi = boot(lambda idx: auc_t(sub(vp, idx), sub(Y, idx), 1.0) - auc_t(sub(P["CLAUDE"], idx), sub(Y, idx), 0.0),
                 Y, n=1000, seed=62)
log(f"  vote panel lenient minus Claude strict (most favourable to the panel): {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")
