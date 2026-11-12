"""Score the preregistered third test (../README.md, 2026-11-11): two Jev versions as WaRF seats.

    python score_mix_confirm.py     # writes score_mix.log, score_mix.json"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
JN = HERE.parents[1] / "real-set" / "jev-narrow"
FROZEN = json.loads((JN / "frozen.json").read_text())
FMIX = json.loads((JN / "versions" / "frozen_mix.json").read_text())
items = {json.loads(l)["id"]: json.loads(l) for l in (HERE.parent / "items.jsonl").open(encoding="utf-8")}
ids = list(items)
D = {i: items[i]["kind"] == "defective" for i in ids}
CH = ["offbyone", "condition", "wrongvar", "missing", "memory", "interface", "compile"]
out = []


def say(s=""):
    out.append(s); print(s)


def load(name):
    whole, hunk, models = {}, {}, set()
    for l in (HERE / name).open(encoding="utf-8"):
        r = json.loads(l); models.add(r["model"])
        p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
        if r["state"] == "whole":
            if r["id"] in whole: raise SystemExit(f"{name}: {r['id']} twice")
            whole[r["id"]] = p
        else:
            hunk.setdefault(r["id"], []).append(p)
    if set(whole) != set(ids): raise SystemExit(f"{name}: whole answers missing")
    return whole, hunk, models


def lg(p):
    p = min(0.99, max(0.01, p)); return math.log(p / (1 - p))


def Nof(w, h):
    return {i: sum(lg(max((x[q] for x in h.get(i, [])), default=w[i][q])) for q in CH) / len(CH) for i in ids}


w14, h14, m14 = load("answers.jsonl"); w13, h13, m13 = load("answers_jev-1.13.jsonl")
N14, N13 = Nof(w14, h14), Nof(w13, h13)
M = {i: (N13[i] + N14[i]) / 2 for i in ids}
V = {i: w14[i]["verdict"] for i in ids}
pos = [i for i in ids if D[i]]; neg = [i for i in ids if not D[i]]


def auc(s, smp=ids):
    P = [s[i] for i in smp if D[i]]; Q = [s[i] for i in smp if not D[i]]
    return sum((a > b) + 0.5 * (a == b) for a in P for b in Q) / (len(P) * len(Q))


def ba(p):
    return (sum(p[i] for i in pos) / len(pos) + sum(not p[i] for i in neg) / len(neg)) / 2


def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


def rank(d):
    return {k: r for r, k in enumerate(sorted(d, key=d.get))}


ra, rb = rank(N13), rank(N14); n = len(ids)
say(f"models: {sorted(m13)} and {sorted(m14)}; 220 items ({len(pos)} defective)")
say(f"Spearman N(1.13) vs N(1.14): {1 - 6 * sum((ra[i] - rb[i]) ** 2 for i in ids) / (n * (n * n - 1)):.3f}")
pm = {i: M[i] >= FMIX["mix"]["threshold"] for i in ids}
pn = {i: N14[i] >= FROZEN["narrow"]["threshold"] for i in ids}
pv = {i: V[i] >= FROZEN["verdict"]["threshold"] for i in ids}
for name, p in (("M two-version WaRF Jev", pm), ("N WaRF Jev (1.14)", pn), ("V one Jev", pv)):
    say(f"  {name:<24} BA {ba(p):.3f}  caught {sum(p[i] for i in pos)}/110  false alarms {sum(p[i] for i in neg)}/110")
res = {}
for rival, pr in (("N", pn), ("V", pv)):
    k1 = sum(pm[i] == D[i] and pr[i] != D[i] for i in ids); k2 = sum(pr[i] == D[i] and pm[i] != D[i] for i in ids)
    p = mcnemar(k1, k1 + k2); d = ba(pm) - ba(pr)
    verdict = "M WINS" if d > 0 and p < 0.05 else "not shown" if d > 0 else "no case"
    tag = "PRIMARY" if rival == "N" else "secondary"
    say(f"  {tag} M - {rival}: BA {d:+.3f}; only M right {k1}, only {rival} right {k2}, McNemar p {p:.3f} -> {verdict}")
    res[rival] = {"d_ba": d, "only_M": k1, "only_rival": k2, "p": p, "verdict": verdict}
rng = random.Random(4); diffs = []
for _ in range(2000):
    smp = [rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg]
    diffs.append(auc(M, smp) - auc(N14, smp))
diffs.sort()
say(f"  secondary AUC: M {auc(M):.3f}, N {auc(N14):.3f}, N(1.13) {auc(N13):.3f}; M - N {auc(M) - auc(N14):+.3f} [{diffs[49]:+.3f}, {diffs[1949]:+.3f}]")
(HERE / "score_mix.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score_mix.json").write_text(json.dumps(res, indent=1))
