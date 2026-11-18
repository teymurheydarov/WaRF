"""How accurate is a WaRF panel with few labels from its own project? Development on RocksDB and DuckDB only
(stored answers, no calls); PPSSPP is kept for the test (README.md).

For n labelled changes per class from the target project (drawn from the training folds; n = 0 means none):
  warf       WaRF today: a seat's Platt fit when it has >= 10 labels of each class, else its raw log-odds
             capped at the vote-mode step of a fresh profile (omega 0.5)
  transfer   each seat's Platt fit from the OTHER project (all its 800 changes), the target's labels ignored
  prior s    a MAP Platt fit on the target's n labels with the prior centred on the other project's fit,
             a ~ N(a0, s), b ~ N(b0, s); at n = 0 this is `transfer`
Rule `logodds` as ../cross-project/cross.py (verdict seats of one model averaged, question seats their own
group, groups summed, threshold tau of the item's domain). Seats keep their role across projects: the persona
seats have the same text everywhere, LOCATE and CHECKLIST carry each project's own text.

    python curve.py      # writes curve.log"""
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cross-project"))
import cross  # noqa: E402  (loads RocksDB and DuckDB)
from cross import GROUP, PROJ  # noqa: E402
from warf.calibration import PlattFit, _logit, _sigmoid  # noqa: E402
from warf.engine import LLR_APPROVE, LLR_REJECT  # noqa: E402

out = []
NS = [0, 5, 10, 20, 40, 80, 160, 360]
REPS = 5
PANELS = {"PANEL3": ("BOUNDARY", "LOCATE", "CHECKLIST"),
          "LO-ctx": ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")}


def say(s=""):
    out.append(s); print(s, flush=True)


def fit(rs, ys, a0=0.0, b0=1.0, sd=1.0, max_iter=60):
    """WaRF's fit_platt with the prior a ~ N(a0, sd), b ~ N(b0, sd) (WaRF: a0 0, b0 1, sd 1)."""
    lam = 1.0 / (sd * sd)

    def logpost(a, b):
        t = -0.5 * lam * ((a - a0) ** 2 + (b - b0) ** 2)
        for r, y in zip(rs, ys):
            s = (a + b * r) * (1 if y == 1 else -1)
            t += -math.log1p(math.exp(-s)) if s >= 0 else s - math.log1p(math.exp(s))
        return t

    a, b = a0, b0
    cur = logpost(a, b)
    for _ in range(max_iter):
        ga, gb, haa, hab, hbb = -lam * (a - a0), -lam * (b - b0), lam, 0.0, lam
        for r, y in zip(rs, ys):
            p = _sigmoid(a + b * r); t = 1.0 if y == 1 else 0.0; w = p * (1 - p)
            ga += t - p; gb += (t - p) * r; haa += w; hab += w * r; hbb += w * r * r
        det = haa * hbb - hab * hab
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        step = 1.0
        while step > 1e-6:
            c = logpost(a + step * da, b + step * db)
            if c >= cur:
                break
            step /= 2
        a, b, cur = a + step * da, b + step * db, c
        if abs(step * da) < 1e-9 and abs(step * db) < 1e-9:
            break
    n_clean = sum(1 for y in ys if y == 1)
    return PlattFit(a, b, _logit((n_clean + 1) / (len(ys) + 2)))


def capped(r, omega=0.5):
    return max(omega * LLR_REJECT, min(omega * LLR_APPROVE, r))


def source_fits(src):
    D = PROJ[src]
    return {s: fit([D["R"][s][i] for i in D["ids"]], [D["Y"][i] for i in D["ids"]]) for s in cross.SEATS}


def curve(target, panel, method, src_fit, sd=None):
    D = PROJ[target]
    res = {}
    for n in NS:
        bas = []
        for rep in range(REPS):
            pred = {}
            for k, test in enumerate(D["folds"][rep]):
                train = [i for f in D["folds"][rep][:k] + D["folds"][rep][k + 1:] for i in f]
                rng = random.Random(1000 * rep + 10 * k + n)
                P = [i for i in train if D["Y"][i] == -1]; N = [i for i in train if D["Y"][i] == 1]
                lab = rng.sample(P, min(n, len(P))) + rng.sample(N, min(n, len(N)))
                ev = {}
                for s in panel:
                    rs, ys = [D["R"][s][i] for i in lab], [D["Y"][i] for i in lab]
                    if method == "warf":
                        f = fit(rs, ys) if n >= 10 else None
                        ev[s] = (lambda r, f=f: f.evidence(r)) if f else capped
                    elif method == "transfer" or n == 0:
                        f0 = src_fit[s]
                        ev[s] = lambda r, f0=f0: f0.a + f0.b * r   # source sets are balanced: no base-rate term
                    else:
                        f = fit(rs, ys, src_fit[s].a, src_fit[s].b, sd)
                        ev[s] = f.evidence
                for i in test:
                    g = {}
                    for s in panel:
                        g.setdefault(GROUP.get(s, s), []).append(ev[s](D["R"][s][i]))
                    pred[i] = sum(sum(v) / len(v) for v in g.values()) >= D["tau"][i]
            bas.append(cross.ba(D, pred))
        res[n] = sum(bas) / len(bas)
    return res


if __name__ == "__main__":
    other = {"RocksDB": "DuckDB", "DuckDB": "RocksDB"}
    fits = {t: source_fits(other[t]) for t in PROJ}
    methods = [("warf", None), ("transfer", None), ("prior 0.25", 0.25), ("prior 0.5", 0.5), ("prior 1", 1.0)]
    say("Balanced accuracy (mean of 5 repetitions) by labelled changes per class from the target project")
    for target in PROJ:
        for pname, panel in PANELS.items():
            say(f"\n{target}, {pname} (source of the prior: {other[target]})")
            say(f"  {'method':<11}" + "".join(f"{n:>7}" for n in NS))
            for m, sd in methods:
                r = curve(target, panel, m.split()[0], fits[target], sd)
                say(f"  {m:<11}" + "".join(f"{100 * r[n]:7.1f}" for n in NS))
    (HERE / "curve.log").write_text("\n".join(out) + "\n", encoding="utf-8")
