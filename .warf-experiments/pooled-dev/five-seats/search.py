"""Best WaRF panels of at most five seats, from stored Jev answers (development, offline, no calls).

Seats are views of views.py that WaRF can express with one project context for every seat:
the five persona seats, V.prof_ctx (WaRF's default question with the context), the locate seats (LB, LR, LE),
the checklist seats (CK.mean, CK.or; stand-ins asked without the context), DG.mean, C.prof_ctx.
Two rules, stratified 10-fold cross-validation within RocksDB (repetition 0 for the search; the top panels
again over 5 repetitions):
  logodds  each seat Platt-calibrated on the training folds (warf.calibration.fit_platt, its prior and base
           rate), verdict seats of one model averaged (jev-1.14: SKEPTIC, ADVOCATE, AUDITOR, V.prof_ctx;
           jev-1.13: TEST-FOCUSED, BOUNDARY), every other seat its own group, groups summed, REJECT below
           tau of the item's domain (WaRF's early stop is not replayed here)
  learned  L2 logistic over the seats' log-odds (warf.calibration.fit_logistic, WaRF's prior), bias minus
           the training base rate, REJECT below tau

    python search.py      # writes search.log"""
import itertools
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[2]))
import views as W  # noqa: E402
from warf.calibration import approve_logodds, fit_logistic, fit_platt  # noqa: E402
from warf.engine import logodds_tau  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


POOL = ["P:SKEPTIC", "P:ADVOCATE", "P:AUDITOR", "P:TEST-FOCUSED", "P:BOUNDARY", "V.prof_ctx",
        "LB", "LR", "LE", "CK.mean", "CK.or", "DG.mean", "C.prof_ctx"]
GROUP = {"P:SKEPTIC": "1.14", "P:ADVOCATE": "1.14", "P:AUDITOR": "1.14", "V.prof_ctx": "1.14",
         "P:TEST-FOCUSED": "1.13", "P:BOUNDARY": "1.13"}
ids, items = W.ids, W.items
Y = {i: (1 if items[i]["kind"] == "clean" else -1) for i in ids}
R = {s: {i: approve_logodds(min(0.99, max(0.01, W.V[s][i]))) for i in ids} for s in POOL}
TAU = {i: logodds_tau(items[i]["domain"]) for i in ids}


def folds(rep):
    rng = random.Random(300 + rep)
    P = [i for i in ids if Y[i] == -1]; N = [i for i in ids if Y[i] == 1]; rng.shuffle(P); rng.shuffle(N)
    return [P[k::10] + N[k::10] for k in range(10)]


FOLDS = [folds(rep) for rep in range(5)]
PLATT = {}      # (rep, k, seat) -> fit


def platt(rep, k, s, train):
    key = (rep, k, s)
    if key not in PLATT:
        PLATT[key] = fit_platt([R[s][i] for i in train], [Y[i] for i in train])
    return PLATT[key]


def ba(pred):
    P = [i for i in ids if Y[i] == -1]; N = [i for i in ids if Y[i] == 1]
    return (sum(not pred[i] for i in P) / len(P) + sum(pred[i] for i in N) / len(N)) / 2   # pred: APPROVE


def run(panel, rule, rep):
    pred = {}
    for k, test in enumerate(FOLDS[rep]):
        train = [i for f in FOLDS[rep][:k] + FOLDS[rep][k + 1:] for i in f]
        if rule == "learned":
            w = fit_logistic([[1.0] + [R[s][i] for s in panel] for i in train], [Y[i] for i in train], 1.0)
            n_clean = sum(1 for i in train if Y[i] == 1)
            bias = w[0] - math.log((n_clean + 1) / (len(train) - n_clean + 1))
            for i in test:
                pred[i] = bias + sum(a * R[s][i] for a, s in zip(w[1:], panel)) >= TAU[i]
        else:
            fits = {s: platt(rep, k, s, train) for s in panel}
            for i in test:
                g = {}
                for s in panel:
                    g.setdefault(GROUP.get(s, s), []).append(fits[s].evidence(R[s][i]))
                pred[i] = sum(sum(v) / len(v) for v in g.values()) >= TAU[i]
    return ba(pred)


if __name__ == "__main__":
    say("Panels of at most five seats, 10-fold CV within RocksDB (balanced accuracy)")
    res = []
    for n in range(1, 6):
        for panel in itertools.combinations(POOL, n):
            if sum(s.startswith("CK") for s in panel) > 1:          # one checklist seat per panel
                continue
            res.append((panel, run(panel, "logodds", 0), run(panel, "learned", 0)))
    for rule, col in (("logodds", 1), ("learned", 2)):
        say(f"\nTop panels, rule {rule} (repetition 0, then mean over 5 repetitions in both rules)")
        for panel, *_ in sorted(res, key=lambda r: -r[col])[:8]:
            m_lo = sum(run(panel, "logodds", rep) for rep in range(5)) / 5
            m_le = sum(run(panel, "learned", rep) for rep in range(5)) / 5
            say(f"  {' + '.join(panel):<62} logodds {100 * m_lo:5.1f}%  learned {100 * m_le:5.1f}%")
    best1 = {n: max((r for r in res if len(r[0]) == n), key=lambda r: max(r[1], r[2])) for n in range(1, 6)}
    say("\nBest panel per size (repetition 0)")
    for n, (panel, lo, le) in best1.items():
        say(f"  {n} seat(s): {' + '.join(panel):<62} logodds {100 * lo:5.1f}%  learned {100 * le:5.1f}%")
    ref = ("P:SKEPTIC", "P:ADVOCATE", "P:AUDITOR", "P:TEST-FOCUSED", "P:BOUNDARY")
    say(f"\nReference, the five persona seats (LO with context): logodds "
        f"{100 * sum(run(ref, 'logodds', r) for r in range(5)) / 5:.1f}%  learned "
        f"{100 * sum(run(ref, 'learned', r) for r in range(5)) / 5:.1f}%")
    (HERE / "search.log").write_text("\n".join(out) + "\n", encoding="utf-8")
