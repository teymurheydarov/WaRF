"""Learned weighting of all stored Jev views per RocksDB change (development, offline, no calls).

WaRF's pooling gives every evidence group the same weight (the group mean, summed). Here the weights are
learned on the project's own labels: an L2-regularised logistic regression on the views' log-odds, judged by
stratified 10-fold cross-validation repeated 5 times within RocksDB (weights from the training folds only).
REJECT when the fitted log-odds of "defective" is above 0 (the set is balanced).

    python stack.py      # writes stack.log"""
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP / "kpx-set")); sys.path.insert(0, str(EXP.parent))
from freeze import fit_logistic  # noqa: E402
from warf.calibration import p_reject_from_text  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


items = {json.loads(l)["id"]: json.loads(l) for l in (EXP / "rdb-set" / "items.jsonl").open(encoding="utf-8")}
ids = list(items); Y = {i: (1 if items[i]["kind"] == "defective" else -1) for i in ids}   # fit_logistic: +1 class


def lg(p):
    p = min(0.99, max(0.01, p)); return math.log(p / (1 - p))


def seats(path):
    s = {}
    for l in Path(path).open(encoding="utf-8"):
        r = json.loads(l)
        s[r["jev"]["id"]] = [(v["model"], p_reject_from_text(v["reasoning"])) for v in r["votes"]]
    return s


LO, LOC = seats(EXP / "rdb-set" / "sessions_LO.jsonl"), seats(HERE / "sessions_LO_ctx.jsonl")
ST = {}
for f in (HERE.parent / "context" / "answers.jsonl", HERE / "answers.jsonl"):
    for l in f.open(encoding="utf-8"):
        r = json.loads(l)
        ST.setdefault(r["state"], {})[r["id"]] = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0)
                                                  for q, v in r["answers"].items()}
CHK, whole, hunk = ["inttype", "format", "warning", "assert", "lifetime", "concurrency", "edge"], {}, {}
for l in (HERE / "answers_checks.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
    (whole.__setitem__(r["id"], p) if r["state"] == "whole" else hunk.setdefault(r["id"], []).append(p))
TOP = {i: {q: max([whole[i][q]] + [h[q] for h in hunk.get(i, [])]) for q in CHK} for i in ids}


def grp(S, i, m):
    v = [lg(p) for mm, p in S[i] if mm == m]; return sum(v) / len(v)


F = {
    "LO (2 group means)": lambda i: [grp(LO, i, "jev-1.14"), grp(LO, i, "jev-1.13")],
    "LO with context (2)": lambda i: [grp(LOC, i, "jev-1.14"), grp(LOC, i, "jev-1.13")],
    "checks (7)": lambda i: [lg(TOP[i][q]) for q in CHK],
    "LO with context + checks": lambda i: [grp(LOC, i, "jev-1.14"), grp(LOC, i, "jev-1.13")] + [lg(TOP[i][q]) for q in CHK],
    "all views": lambda i: ([grp(LO, i, "jev-1.14"), grp(LO, i, "jev-1.13"), grp(LOC, i, "jev-1.14"), grp(LOC, i, "jev-1.13")]
                            + [lg(TOP[i][q]) for q in CHK] + [lg(whole[i]["verdict"])]
                            + [lg(ST[s][i][q]) for s in ("plain", "ctx", "commit", "both", "prof", "prof_ctx") for q in ("verdict", "compile")]),
}


def ba(pred):
    P = [i for i in ids if Y[i] == 1]; N = [i for i in ids if Y[i] == -1]
    return (sum(pred[i] for i in P) / len(P) + sum(not pred[i] for i in N) / len(N)) / 2


def cv(f, sd):
    """Balanced accuracy of the L2 logistic on views f, 10-fold x 5 within RocksDB: mean, min, max."""
    res = []
    for rep in range(5):
        rng = random.Random(300 + rep)
        P = [i for i in ids if Y[i] == 1]; N = [i for i in ids if Y[i] == -1]; rng.shuffle(P); rng.shuffle(N)
        folds = [P[k::10] + N[k::10] for k in range(10)]
        pred = {}
        for k in range(10):
            tr = [i for g in folds[:k] + folds[k + 1:] for i in g]
            w = fit_logistic([[1.0] + f(i) for i in tr], [Y[i] for i in tr], prior_sd=sd)
            pred.update({i: sum(a * b for a, b in zip(w, [1.0] + f(i))) > 0 for i in folds[k]})
        res.append(ba(pred))
    return sum(res) / 5, min(res), max(res)


if __name__ == "__main__":
    say("Learned weights, 10-fold x 5 within RocksDB (800 changes, balanced accuracy)")
    for name, f in F.items():
        for sd in (1.0, 0.3):
            m, a, b = cv(f, sd)
            say(f"  {name:<28} prior sd {sd}: {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
    (HERE / "stack.log").write_text("\n".join(out) + "\n", encoding="utf-8")
