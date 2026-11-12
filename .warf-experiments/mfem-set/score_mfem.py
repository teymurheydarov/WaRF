"""Score the preregistered MFEM test (README.md).

    python score_mfem.py      # writes score.log, score.json"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN = json.loads((HERE.parent / "real-set" / "jev-narrow" / "frozen.json").read_text())
items = {json.loads(l)["id"]: json.loads(l) for l in (HERE / "items.jsonl").open(encoding="utf-8")}
ids = list(items)
D = {i: items[i]["kind"] == "defective" for i in ids}
pos = [i for i in ids if D[i]]; neg = [i for i in ids if not D[i]]
SEPARATOR = "\n\n" + "─" * 60 + "\n"          # warf.context_extractor._SEPARATOR: diff above, function bodies below
CH = ["offbyone", "condition", "wrongvar", "missing", "memory", "interface", "compile"]
out = []


def say(s=""):
    out.append(s); print(s)


def lg(p):
    p = min(0.99, max(0.01, p)); return math.log(p / (1 - p))


whole, hunk, models = {}, {}, set()
for l in (HERE / "answers_narrow.jsonl").open(encoding="utf-8"):
    r = json.loads(l); models.add(r["model"])
    p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
    if r["state"] == "whole":
        if r["id"] in whole: raise SystemExit(f"{r['id']} twice")
        whole[r["id"]] = p
    else:
        hunk.setdefault(r["id"], []).append(p)
if set(whole) != set(ids): raise SystemExit(f"{len(set(ids) - set(whole))} whole-change answers missing")
lo = {}
for l in (HERE / "sessions_LO.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    if r["jev"]["id"] in lo: raise SystemExit(f"LO {r['jev']['id']} twice")
    lo[r["jev"]["id"]] = r
if set(lo) != set(ids): raise SystemExit(f"{len(set(ids) - set(lo))} LO reviews missing")

V = {i: whole[i]["verdict"] for i in ids}
N = {i: sum(lg(max((h[q] for h in hunk.get(i, [])), default=whole[i][q])) for q in CH) / len(CH) for i in ids}
pv = {i: V[i] >= FROZEN["verdict"]["threshold"] for i in ids}
pn = {i: N[i] >= FROZEN["narrow"]["threshold"] for i in ids}
pl = {i: lo[i]["decision"] == "REJECT" for i in ids}
mp = {i: sum(v["p_reject"] for v in lo[i]["jev"]["round1"].values()) / len(lo[i]["jev"]["round1"]) for i in ids}


def added(c):
    return sum(1 for ln in c.split(SEPARATOR, 1)[0].splitlines()
               if ln.startswith("+") and not ln.startswith("+++"))


A = {i: added(items[i]["code"]) for i in ids}


def ba(p, P=pos, Q=neg):
    return (sum(p[i] for i in P) / len(P) + sum(not p[i] for i in Q) / len(Q)) / 2


def auc(s):
    return sum((s[a] > s[b]) + 0.5 * (s[a] == s[b]) for a in pos for b in neg) / (len(pos) * len(neg))


def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


def vs(pa, pr):
    k1 = sum(pa[i] == D[i] and pr[i] != D[i] for i in ids); k2 = sum(pr[i] == D[i] and pa[i] != D[i] for i in ids)
    return ba(pa) - ba(pr), k1, k2, mcnemar(k1, k1 + k2)


lo_models = sorted({m for r in lo.values() for m in r["jev"]["models"]})
cost = sum(r["jev"]["cost"] for r in lo.values()) + sum(
    float((json.loads(l).get("usage") or {}).get("cost") or 0) for l in (HERE / "answers_narrow.jsonl").open(encoding="utf-8"))
say(f"{len(ids)} MFEM items ({len(pos)} defective, {len(neg)} clean); narrow run {sorted(models)}; LO {lo_models}; Jev cost ${cost:.3f}")
for name, p in (("V, one Jev", pv), ("N, WaRF Jev narrow checks", pn), ("LO, WaRF log-odds panel", pl)):
    say(f"  {name:<28} right {100 * ba(p):5.1f}%  caught {sum(p[i] for i in pos)}/{len(pos)}  false alarms {sum(p[i] for i in neg)}/{len(neg)}")
d, k1, k2, p = vs(pl, pv)
verdict = "LO WINS" if d > 0 and p < 0.05 else "not shown" if d > 0 else "no case"
say(f"\nPRIMARY  LO - V: {100 * d:+.1f} points; only LO right {k1}, only V right {k2}; exact McNemar p {p:.4f} -> {verdict}")
res = {"primary": {"d": d, "only_LO": k1, "only_V": k2, "p": p, "verdict": verdict},
       "ba": {"V": ba(pv), "N": ba(pn), "LO": ba(pl)}}
for name, a, b in (("LO - N", pl, pn), ("N - V", pn, pv)):
    d2, j1, j2, p2 = vs(a, b)
    say(f"secondary {name}: {100 * d2:+.1f} points; {j1} vs {j2}; McNemar p {p2:.4f}")
    res[name] = {"d": d2, "a": j1, "b": j2, "p": p2}
say(f"secondary AUC: added lines {auc(A):.3f}, V {auc(V):.3f}, N {auc(N):.3f}, LO mean seat p {auc(mp):.3f}")
vis = [i for i in pos if items[i].get("visible") == "diff"]
say(f"secondary, the {len(vis)} defects visible from the diff (with all clean items):")
for name, pp in (("V", pv), ("N", pn), ("LO", pl)):
    say(f"  {name:<3} right {100 * ba(pp, vis, neg):5.1f}%  caught {sum(pp[i] for i in vis)}/{len(vis)}")
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score.json").write_text(json.dumps(res, indent=1))
