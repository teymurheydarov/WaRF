"""Free check: does Jev add to change size on fresh items? A logistic model log(added+1) [+ Jev score]
fitted on the 132 dev items, applied unchanged to the 220 confirm items."""
import contextlib, io, json, math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    import score_narrow as dev
    sys.path.insert(0, str(HERE.parents[1] / "confirm-set" / "jev-narrow"))
    import score_jev_confirm as cf
def auc(s, ids, D):
    P = [s[i] for i in ids if D[i]]; Q = [s[i] for i in ids if not D[i]]
    return sum((a > b) + 0.5 * (a == b) for a in P for b in Q) / (len(P) * len(Q))
lg = dev.lg
devV = dev.S["verdict, whole change (this run)"]; devN = dev.S["narrow checks, hunks, mean logit of hunk max"]
for name, ds, cs, tr in (("size only", None, None, None), ("size + V", devV, cf.V, lg), ("size + N", devN, cf.N, lambda x: x)):
    fx = lambda A, s, i: [1.0, math.log(A[i] + 1)] + ([tr(s[i])] if s else [])
    w = dev.fit([fx(dev.A, ds, i) for i in dev.ids], [int(dev.D[i]) for i in dev.ids])
    sc = {i: sum(a * b for a, b in zip(w, fx(cf.A, cs, i))) for i in cf.ids}
    print(f"{name:<10} fresh-set AUC {auc(sc, cf.ids, cf.D):.3f}   weights {[round(x, 2) for x in w]}")
