"""Paired stratified bootstrap (2000, seed 4) of narrow-checks mean logit vs the verdict question, and
balanced accuracy with a leave-one-out threshold. Imports score_narrow's data (its prints rerun)."""
import random, contextlib, io
with contextlib.redirect_stdout(io.StringIO()):
    import score_narrow as s
ids, D = s.ids, s.D
A = s.S["verdict, whole change (this run)"]; B = s.S["narrow checks, whole, mean logit"]; H = s.S["narrow checks, hunks, mean logit of hunk max"]
rng = random.Random(4); P = [i for i in ids if D[i]]; N = [i for i in ids if not D[i]]
def auc(sc, smp):
    pp = [sc[i] for i in smp if D[i]]; nn = [sc[i] for i in smp if not D[i]]
    return sum((a > b) + 0.5 * (a == b) for a in pp for b in nn) / (len(pp) * len(nn))
for name, X in (("whole", B), ("hunks", H)):
    d = []
    for _ in range(2000):
        smp = [rng.choice(P) for _ in P] + [rng.choice(N) for _ in N]
        d.append(auc(X, smp) - auc(A, smp))
    d.sort(); print(f"narrow mean logit ({name}) - verdict: AUC {auc(X, ids) - auc(A, ids):+.3f} [{d[49]:+.3f}, {d[1949]:+.3f}]")
def ba_loo(sc):
    ts = sorted(set(sc.values())); hit = 0; pred = {}
    def ba(t, smp):
        pp = [i for i in smp if D[i]]; nn = [i for i in smp if not D[i]]
        return (sum(sc[i] >= t for i in pp) / len(pp) + sum(sc[i] < t for i in nn) / len(nn)) / 2
    for i in ids:
        rest = [j for j in ids if j != i]; t = max(ts, key=lambda t: ba(t, rest)); pred[i] = sc[i] >= t
    tp = sum(pred[i] for i in P); fp = sum(pred[i] for i in N)
    return (tp / len(P) + (len(N) - fp) / len(N)) / 2, tp, fp
for name, X in (("verdict", A), ("narrow whole", B), ("narrow hunks", H)):
    b, tp, fp = ba_loo(X); print(f"BA with LOO threshold, {name}: {b:.3f} ({tp}/66 caught, {fp}/66 false alarms)")
