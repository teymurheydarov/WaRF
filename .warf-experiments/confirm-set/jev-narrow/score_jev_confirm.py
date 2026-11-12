"""Score the preregistered Jev narrow-questions test (../README.md, "Second test", 2026-11-09).

    python .warf-experiments/confirm-set/jev-narrow/score_jev_confirm.py     # writes score.log, score.json"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN = json.loads((HERE.parents[1] / "real-set" / "jev-narrow" / "frozen.json").read_text())
items = {json.loads(l)["id"]: json.loads(l) for l in (HERE.parent / "items.jsonl").open(encoding="utf-8")}
ids = list(items)
D = {i: items[i]["kind"] == "defective" for i in ids}
out = []


def say(s=""):
    out.append(s); print(s)


whole, hunk = {}, {}
for l in (HERE / "answers.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
    if r["state"] == "whole":
        if r["id"] in whole: raise SystemExit(f"{r['id']} twice")
        whole[r["id"]] = p
    else:
        hunk.setdefault(r["id"], []).append(p)
if set(whole) != set(ids):
    raise SystemExit(f"{len(set(ids) - set(whole))} whole-change answers missing")
CH = ["offbyone", "condition", "wrongvar", "missing", "memory", "interface", "compile"]


def lg(p):
    p = min(0.99, max(0.01, p)); return math.log(p / (1 - p))


def hmax(i, q):
    return max((h[q] for h in hunk.get(i, [])), default=whole[i][q])


V = {i: whole[i]["verdict"] for i in ids}
N = {i: sum(lg(hmax(i, q)) for q in CH) / len(CH) for i in ids}


def auc(s, smp=ids):
    P = [s[i] for i in smp if D[i]]; Q = [s[i] for i in smp if not D[i]]
    return sum((a > b) + 0.5 * (a == b) for a in P for b in Q) / (len(P) * len(Q)), len(P) * len(Q)


def added(c):
    return sum(1 for ln in c.splitlines() if ln.startswith("+") and not ln.startswith("+++"))


A = {i: added(items[i]["code"]) for i in ids}
qs = sorted(A.values()); cuts = [qs[len(qs) // 3], qs[2 * len(qs) // 3]]
bins = [[i for i in ids if lo < A[i] <= hi] for lo, hi in ((-1, cuts[0]), (cuts[0], cuts[1]), (cuts[1], 10 ** 9))]


def within(s):
    num = den = 0
    for b in bins:
        if any(D[i] for i in b) and any(not D[i] for i in b):
            a, n = auc(s, b); num += a * n; den += n
    return num / den


nP = sum(D.values())
say(f"{len(ids)} items ({nP} defective, {len(ids) - nP} clean); calls: {len(whole)} whole, {sum(map(len, hunk.values()))} hunks")
say(f"added-lines AUC {auc(A)[0]:.3f} (thirds at {cuts})")
say(f"  V usual question:  AUC {auc(V)[0]:.3f}  within thirds {within(V):.3f}")
say(f"  N narrow checks:   AUC {auc(N)[0]:.3f}  within thirds {within(N):.3f}")
rng = random.Random(4)
pos = [i for i in ids if D[i]]; neg = [i for i in ids if not D[i]]
diffs = []
for _ in range(2000):
    smp = [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]
    diffs.append(auc(N, smp)[0] - auc(V, smp)[0])
diffs.sort()
d = auc(N)[0] - auc(V)[0]
lo, hi = diffs[49], diffs[1949]
verdict = "N WINS" if lo > 0 else "not shown" if d > 0 else "no case"
say(f"  PRIMARY  N - V: AUC {d:+.3f} [{lo:+.3f}, {hi:+.3f}]  ->  PREREGISTERED VERDICT: {verdict}")


def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


tv, tn = FROZEN["verdict"]["threshold"], FROZEN["narrow"]["threshold"]
pv = {i: V[i] >= tv for i in ids}; pn = {i: N[i] >= tn for i in ids}


def ba(p):
    return (sum(p[i] for i in pos) / len(pos) + sum(not p[i] for i in neg) / len(neg)) / 2


k1 = sum(pn[i] == D[i] and pv[i] != D[i] for i in ids); k2 = sum(pv[i] == D[i] and pn[i] != D[i] for i in ids)
for name, p in (("V at dev threshold", pv), ("N at dev threshold", pn)):
    say(f"  {name:<20} BA {ba(p):.3f}  caught {sum(p[i] for i in pos)}/{len(pos)}  false alarms {sum(p[i] for i in neg)}/{len(neg)}")
say(f"  secondary: only N right {k1}, only V right {k2}, McNemar p {mcnemar(k1, k1 + k2):.3f}")
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score.json").write_text(json.dumps({"auc_V": auc(V)[0], "auc_N": auc(N)[0], "d": d, "ci": [lo, hi],
                                             "verdict": verdict, "ba_V": ba(pv), "ba_N": ba(pn)}, indent=1))
