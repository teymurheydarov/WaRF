"""Panels of at most five seats, scored on BOTH labelled projects from stored WaRF answers (development: both sets
have been seen; no calls).

  RocksDB (800, ../../rdb-set/items.jsonl): persona seats from ../history/sessions_LO_ctx.jsonl, DEFAULT, LOCATE
          and CHECKLIST from ../five-seats/sessions_live.jsonl (all with RocksDB's context)
  DuckDB  (800, ../../ddb-set/items.jsonl): all eight seats from ../../ddb-set/sessions.jsonl (DuckDB's context)
Rule `logodds` as ../five-seats/search.py (WaRF's Platt fit per seat, verdict seats of one model averaged, each
question seat its own group, groups summed, threshold tau of the item's domain; the early stop is not replayed),
stratified 10-fold, the folds of ../warf-panel/replay_learned.py.

    python cross.py      # writes cross.log; import cross for its data and run()"""
import itertools
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
from warf.calibration import approve_logodds, fit_platt  # noqa: E402
from warf.engine import logodds_tau  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


SEATS = ["SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY", "DEFAULT", "LOCATE", "CHECKLIST"]
GROUP = {"SKEPTIC": "1.14", "ADVOCATE": "1.14", "AUDITOR": "1.14", "DEFAULT": "1.14",
         "TEST-FOCUSED": "1.13", "BOUNDARY": "1.13"}


def load(items_path, session_paths):
    items = {json.loads(l)["id"]: json.loads(l) for l in Path(items_path).open(encoding="utf-8")}
    p = {}
    for f in session_paths:
        for l in Path(f).open(encoding="utf-8"):
            r = json.loads(l)
            for v in r["votes"]:
                if v["agent"] in SEATS:
                    p[(r["artifact"], v["agent"])] = v["p_reject"]
    ids = list(items)
    missing = [(i, s) for i in ids for s in SEATS if (i, s) not in p]
    if missing:
        raise SystemExit(f"{len(missing)} answers missing, e.g. {missing[:2]}")
    Y = {i: (1 if items[i]["kind"] == "clean" else -1) for i in ids}
    R = {s: {i: approve_logodds(min(0.99, max(0.01, p[(i, s)]))) for i in ids} for s in SEATS}
    tau = {i: logodds_tau(items[i]["domain"]) for i in ids}
    folds = []
    for rep in range(5):
        rng = random.Random(300 + rep)
        P = [i for i in ids if Y[i] == -1]; N = [i for i in ids if Y[i] == 1]; rng.shuffle(P); rng.shuffle(N)
        folds.append([P[k::10] + N[k::10] for k in range(10)])
    return {"items": items, "ids": ids, "Y": Y, "R": R, "tau": tau, "folds": folds, "platt": {}}


PROJ = {"RocksDB": load(EXP / "rdb-set" / "items.jsonl", [HERE.parent / "history" / "sessions_LO_ctx.jsonl",
                                                         HERE.parent / "five-seats" / "sessions_live.jsonl"]),
        "DuckDB": load(EXP / "ddb-set" / "items.jsonl", [EXP / "ddb-set" / "sessions.jsonl"])}


def ba(D, pred):
    P = [i for i in D["ids"] if D["Y"][i] == -1]; N = [i for i in D["ids"] if D["Y"][i] == 1]
    return (sum(not pred[i] for i in P) / len(P) + sum(pred[i] for i in N) / len(N)) / 2


def run(D, panel, rep=0, group=GROUP):
    """Balanced accuracy of `panel` under the logodds rule, repetition `rep`; pred[i] True = APPROVE."""
    pred = {}
    for k, test in enumerate(D["folds"][rep]):
        train = [i for f in D["folds"][rep][:k] + D["folds"][rep][k + 1:] for i in f]
        fits = {}
        for s in panel:
            key = (rep, k, s)
            if key not in D["platt"]:
                D["platt"][key] = fit_platt([D["R"][s][i] for i in train], [D["Y"][i] for i in train])
            fits[s] = D["platt"][key]
        for i in test:
            g = {}
            for s in panel:
                g.setdefault(group.get(s, s), []).append(fits[s].evidence(D["R"][s][i]))
            pred[i] = sum(sum(v) / len(v) for v in g.values()) >= D["tau"][i]
    return ba(D, pred)


def both(panel, reps=1, group=GROUP):
    return {name: sum(run(D, panel, r, group) for r in range(reps)) / reps for name, D in PROJ.items()}


if __name__ == "__main__":
    LO = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
    P3 = ("BOUNDARY", "LOCATE", "CHECKLIST")
    ref = {name: both(p, 5) for name, p in (("LO-ctx", LO), ("PANEL3", P3))}
    say("Reference (mean of 5 repetitions): " + "; ".join(f"{n} RocksDB {100 * r['RocksDB']:.1f}%, DuckDB "
                                                          f"{100 * r['DuckDB']:.1f}%" for n, r in ref.items()))
    res = []
    for n in range(1, 6):
        for panel in itertools.combinations(SEATS, n):
            r = both(panel)
            res.append((min(r.values()), r, panel))
    res.sort(key=lambda t: -t[0])
    say("\nPanels of at most 5 seats ranked by the worse project (repetition 0), top 12, then 5 repetitions")
    for _, r0, panel in res[:12]:
        r = both(panel, 5)
        say(f"  {' + '.join(panel):<62} RocksDB {100 * r['RocksDB']:5.1f}%  DuckDB {100 * r['DuckDB']:5.1f}%")
    (HERE / "cross.log").write_text("\n".join(out) + "\n", encoding="utf-8")
