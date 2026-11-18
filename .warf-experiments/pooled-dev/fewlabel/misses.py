"""Where PANEL3 misses (stored answers, no calls): catch rate of the test defects by the judges' visibility label,
and false alarms, on DuckDB and PPSSPP (10-fold calibration within the set, repetition 0, the rule of
../cross-project/cross.py).

    python misses.py      # writes misses.log"""
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cross-project"))
import cross  # noqa: E402

EXP = HERE.parent.parent
out = []


def say(s=""):
    out.append(s); print(s, flush=True)


def predict(D, panel, rep=0):
    pred = {}
    for k, test in enumerate(D["folds"][rep]):
        train = [i for f in D["folds"][rep][:k] + D["folds"][rep][k + 1:] for i in f]
        fits = {s: cross.fit_platt([D["R"][s][i] for i in train], [D["Y"][i] for i in train]) for s in panel}
        for i in test:
            g = {}
            for s in panel:
                g.setdefault(cross.GROUP.get(s, s), []).append(fits[s].evidence(D["R"][s][i]))
            pred[i] = sum(sum(v) / len(v) for v in g.values()) >= D["tau"][i]
    return pred


sets = {"DuckDB": cross.PROJ["DuckDB"],
        "PPSSPP": cross.load(EXP / "pp-set" / "items.jsonl", [EXP / "pp-set" / "sessions.jsonl"])}
P3 = ("BOUNDARY", "LOCATE", "CHECKLIST")
for name, D in sets.items():
    pred = predict(D, P3)
    items = D["items"]
    vis = Counter(items[i].get("visible") for i in D["ids"] if D["Y"][i] == -1)
    say(f"\n{name}: PANEL3, balanced accuracy {100 * cross.ba(D, pred):.1f}%")
    for v, n in vis.most_common():
        caught = sum(1 for i in D["ids"] if D["Y"][i] == -1 and items[i].get("visible") == v and not pred[i])
        say(f"  defects {v:<17} {n:4d}  caught {caught:4d}  ({100 * caught / n:.0f}%)")
    N = [i for i in D["ids"] if D["Y"][i] == 1]
    say(f"  clean changes          {len(N):4d}  false alarms {sum(1 for i in N if not pred[i])}"
        f"  ({100 * sum(1 for i in N if not pred[i]) / len(N):.0f}%)")
(HERE / "misses.log").write_text("\n".join(out) + "\n", encoding="utf-8")
