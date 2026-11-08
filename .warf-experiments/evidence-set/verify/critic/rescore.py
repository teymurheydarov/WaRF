"""Critic re-score of the evidence set: clean items whose committed code holds a real defect
counted as REJECT-right (relabel) or dropped (drop). Classes come from the three classify checks
(verify/cr13, verify/claude-rejects, verify/judgeB), reconciled by hand; see the critic's report.
Pure Python, reads only the arm records and items.jsonl."""
import json, math, random
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
items = {it["id"]: it for it in map(json.loads, (HERE / "items.jsonl").open(encoding="utf-8"))}
rej = {}
for arm in ("claude", "claude-standard"):
    rej[arm] = {}
    for p in sorted(HERE.glob(f"{arm}.w*.jsonl")):
        for line in p.open(encoding="utf-8"):
            r = json.loads(line)
            rej[arm][r["planted"]["id"]] = r["decision"] == "REJECT"
bases = sorted({it["base"] for it in items.values()})
short = {b.split(":")[0]: b for b in bases}

REAL = "06377a8 2a29aa6 2f8cd81 38858cf 3cf80c7 5853a6f 5f9ae79 6fc3f69 8058d91 890cd00 8ca586f 9b1851c af41faa c826b44 da35b0c e42bec0".split()
DEBATABLE = "15977e9 a86cf94 d9fca63 db3aca7".split()
FALSE = "0696ac5 6c02814 a880e56 bfbe226 c0c88af".split()
cls = {**{s: "real" for s in REAL}, **{s: "debatable" for s in DEBATABLE}, **{s: "false" for s in FALSE}}

# sanity: classified set == one Claude's clean rejects; five's clean rejects inside it
one_rej = {b.split(":")[0] for b in bases if rej["claude"][f"{b}:clean"]}
five_rej = {b.split(":")[0] for b in bases if rej["claude-standard"][f"{b}:clean"]}
assert one_rej == set(cls), (one_rej ^ set(cls))
assert five_rej <= one_rej
print(f"one Claude clean rejects {len(one_rej)}, five {len(five_rej)}, five-only {len(five_rej - one_rej)}")
for c in ("real", "debatable", "false"):
    s = [k for k in cls if cls[k] == c]
    print(f"  {c:<9} {len(s):2d}: five rejected {sum(k in five_rej for k in s)}, approved {[k for k in s if k not in five_rej]}")

def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)

def score(bs, defect, mode):
    """rows: (base, kind, truth_reject). mode relabel: clean with defect -> truth REJECT; drop: removed."""
    out = {}
    for arm in rej:
        tp = p = tn = n = 0
        for b in bs:
            for kind in ("planted", "clean"):
                d = kind == "planted" or b.split(":")[0] in defect
                if kind == "clean" and d and mode == "drop":
                    continue
                r = rej[arm][f"{b}:{kind}"]
                if d: p += 1; tp += r
                else: n += 1; tn += not r
        out[arm] = ((tp / p + tn / n) / 2, tp, p, tn, n)
    return out

rng = random.Random(4)
boots = [[rng.choice(bases) for _ in bases] for _ in range(2000)]
variants = [("labels as given", set()),
            ("real (16)", set(REAL)),
            ("real + 15977e9 (17)", set(REAL) | {"15977e9"}),
            ("real + all debatable (20)", set(REAL) | set(DEBATABLE))]
for name, defect in variants:
    for mode in (("relabel", "drop") if defect else ("relabel",)):
        s = score(bases, defect, mode)
        o, f = s["claude"], s["claude-standard"]
        d = f[0] - o[0]
        xs = sorted(score(bb, defect, mode)["claude-standard"][0] - score(bb, defect, mode)["claude"][0] for bb in boots)
        only5 = only1 = 0
        for b in bases:
            for kind in ("planted", "clean"):
                t = kind == "planted" or b.split(":")[0] in defect
                if kind == "clean" and t and mode == "drop":
                    continue
                c1 = rej["claude"][f"{b}:{kind}"] == t; c5 = rej["claude-standard"][f"{b}:{kind}"] == t
                only5 += c5 and not c1; only1 += c1 and not c5
        print(f"\n{name}, {mode}: one {o[0]:.3f} (REJECT-right {o[1]}/{o[2]}, APPROVE-right {o[3]}/{o[4]}); "
              f"five {f[0]:.3f} ({f[1]}/{f[2]}, {f[3]}/{f[4]})")
        print(f"  five minus one {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}], <=0 in {sum(x <= 0 for x in xs)/len(xs):.1%}; "
              f"only five right {only5}, only one right {only1}, McNemar p {mcnemar(only5, only5 + only1):.3f}")
