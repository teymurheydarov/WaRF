"""Calibration and pooling variants for PANEL3 on both projects (development, offline, no calls).

  own        WaRF logodds as cross.py: Platt per seat from the project's own training folds
  shared     the same, but each seat's Platt fit also uses all of the other project's changes (same seat role:
             the persona seat's text is identical, LOCATE and CHECKLIST ask each project's own questions)
  learned    one weight per seat and an intercept (warf.calibration.fit_logistic, WaRF's prior), trained on the
             other project plus the own training folds; bias = intercept - logit(training clean share)
Same folds as cross.py.

    python pooling.py      # writes pooling.log"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cross as C  # noqa: E402
from warf.calibration import fit_logistic, fit_platt  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


PANEL = ("BOUNDARY", "LOCATE", "CHECKLIST")


def run(name, rule, rep):
    D = C.PROJ[name]; O = C.PROJ["DuckDB" if name == "RocksDB" else "RocksDB"]
    pred = {}
    for k, test in enumerate(D["folds"][rep]):
        train = [i for f in D["folds"][rep][:k] + D["folds"][rep][k + 1:] for i in f]
        if rule == "learned":
            X = [[1.0] + [D["R"][s][i] for s in PANEL] for i in train] + [[1.0] + [O["R"][s][i] for s in PANEL] for i in O["ids"]]
            y = [D["Y"][i] for i in train] + [O["Y"][i] for i in O["ids"]]
            w = fit_logistic(X, y, 1.0)
            n_clean = sum(1 for t in y if t == 1)
            bias = w[0] - math.log((n_clean + 1) / (len(y) - n_clean + 1))
            for i in test:
                pred[i] = bias + sum(a * D["R"][s][i] for a, s in zip(w[1:], PANEL)) >= D["tau"][i]
            continue
        fits = {}
        for s in PANEL:
            rs, ys = [D["R"][s][i] for i in train], [D["Y"][i] for i in train]
            if rule == "shared":
                rs += [O["R"][s][i] for i in O["ids"]]; ys += [O["Y"][i] for i in O["ids"]]
            fits[s] = fit_platt(rs, ys)
        for i in test:
            pred[i] = sum(fits[s].evidence(D["R"][s][i]) for s in PANEL) >= D["tau"][i]
    return C.ba(D, pred)


say("PANEL3 (BOUNDARY + LOCATE + CHECKLIST), 10-fold x 5 (balanced accuracy)")
for rule in ("own", "shared", "learned"):
    r = {n: sum(run(n, rule, rep) for rep in range(5)) / 5 for n in C.PROJ}
    say(f"  {rule:<8} RocksDB {100 * r['RocksDB']:5.1f}%  DuckDB {100 * r['DuckDB']:5.1f}%")
(HERE / "pooling.log").write_text("\n".join(out) + "\n", encoding="utf-8")
