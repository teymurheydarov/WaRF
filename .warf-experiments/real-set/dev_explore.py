"""DEVELOPMENT ONLY (no claim may rest on this): how far do combinations of the stored single answers
get on the 132 real-set items? Every variant tried is printed and appended to DEV.md, so the number of
looks is on record. A winner here must be frozen and confirmed on a fresh set (see DEV.md).

Rules tried, over the arms claude, claude-commit, claude-strict, claude-commit-strict, claude-advocate,
claude-standard (WaRF five personas, its verdict) and jev:
  k-of-n     REJECT if at least k of the chosen arms reject (all subsets of 2 to 4 arms, every k)
  log-odds   WaRF-style naive Bayes: each arm's vote worth its Laplace-smoothed likelihood ratio,
             learned out of fold (5 folds stratified by class, seed 7), summed, threshold 0

    python .warf-experiments/real-set/dev_explore.py"""
import glob
import itertools
import json
import math
import random
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("claude", "claude-commit", "claude-strict", "claude-commit-strict", "claude-advocate", "claude-standard", "jev")
items = {it["id"]: it for it in map(json.loads, (HERE / "items.jsonl").open(encoding="utf-8"))}
ids = list(items)
defect = {i: items[i]["kind"] == "defective" for i in ids}
rej = {}
for a in ARMS:
    rej[a] = {}
    for f in glob.glob(str(HERE / f"{a}.w*.jsonl")):
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            rej[a][r["planted"]["id"]] = r["decision"] == "REJECT"


def ba(pred):
    P = [i for i in ids if defect[i]]
    N = [i for i in ids if not defect[i]]
    return (sum(pred[i] for i in P) / len(P) + sum(not pred[i] for i in N) / len(N)) / 2


def counts(pred):
    return (sum(pred[i] for i in ids if defect[i]), sum(pred[i] for i in ids if not defect[i]))


rows = []
for a in ARMS:
    rows.append((ba(rej[a]), f"single {a}", counts(rej[a])))
for n in (2, 3, 4):
    for subset in itertools.combinations(ARMS, n):
        for k in range(1, n + 1):
            pred = {i: sum(rej[a][i] for a in subset) >= k for i in ids}
            rows.append((ba(pred), f"{k}-of-{n} {'+'.join(subset)}", counts(pred)))

rng = random.Random(7)
fold = {}
for cls in (True, False):
    m = [i for i in ids if defect[i] == cls]
    rng.shuffle(m)
    for k, i in enumerate(m):
        fold[i] = k % 5
for n in (2, 3, 4, 5, 6, 7):
    for subset in itertools.combinations(ARMS, n):
        pred = {}
        for k in range(5):
            train = [i for i in ids if fold[i] != k]
            w = {}
            for a in subset:
                nP = sum(defect[i] for i in train)
                nN = len(train) - nP
                rP = (sum(rej[a][i] for i in train if defect[i]) + 1) / (nP + 2)
                rN = (sum(rej[a][i] for i in train if not defect[i]) + 1) / (nN + 2)
                w[a] = (math.log(rP / rN), math.log((1 - rP) / (1 - rN)))
            for i in (i for i in ids if fold[i] == k):
                pred[i] = sum(w[a][0] if rej[a][i] else w[a][1] for a in subset) > 0
        rows.append((ba(pred), f"log-odds {'+'.join(subset)}", counts(pred)))

rows.sort(key=lambda r: -r[0])
base = ba(rej["claude-commit-strict"])
out = [f"## dev_explore.py, {datetime.now():%Y-%m-%d %H:%M}: {len(rows)} variants looked at",
       f"best single call: claude-commit-strict {base:.3f}; top 15:"]
for b, name, (c, fa) in rows[:15]:
    out.append(f"  {b:.3f}  caught {c}/66  false alarms {fa}/66  {name}")
print("\n".join(out))
with (HERE / "DEV.md").open("a", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n\n")
