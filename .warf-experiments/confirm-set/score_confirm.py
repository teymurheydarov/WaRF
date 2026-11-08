"""Score the preregistered confirmation test (README.md).

P (the effort panel) rejects an item if Opus at low, default or max effort rejects it. It was asked in
sequence: low on every item, default on every item (it is also the S-default arm), max only where both
approved. On items where low or default rejected, max was not asked and P rejects without it.
P wins if it beats both S-low and S-default in balanced accuracy, with exact McNemar p < 0.05 and a
bootstrap lower bound above 0 (stratified by class, 2000, seed 4). "Not shown" if both differences are
positive but either test fails; "no case" otherwise.

    python .warf-experiments/confirm-set/score_confirm.py     # writes score.log and score.json"""
import glob
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = "claude-commit-strict-tools"
out = []


def say(s=""):
    out.append(s)
    print(s)


items = {it["id"]: it for it in map(json.loads, (HERE / "items.jsonl").open(encoding="utf-8"))}
ids = list(items)
defect = {i: items[i]["kind"] == "defective" for i in ids}


def load(tag):
    recs = {}
    for f in glob.glob(str(HERE / f"{tag}.w*.jsonl")):
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            if r["planted"]["id"] in recs:
                raise SystemExit(f"{tag}: {r['planted']['id']} twice")
            recs[r["planted"]["id"]] = r["decision"] == "REJECT"
    return recs


low, default, mx = load(f"{A}@low"), load(A), load(f"{A}@max")
need_max = [i for i in ids if not low.get(i, True) and not default.get(i, True)]
missing = ([i for i in ids if i not in low or i not in default] + [i for i in need_max if i not in mx])
if missing:
    raise SystemExit(f"{len(missing)} answers missing, e.g. {missing[:3]}; finish the runs first")
if set(mx) - set(need_max):
    raise SystemExit("max was asked on items low or default had rejected")
P = {i: low[i] or default[i] or mx.get(i, False) for i in ids}
arms = {"P effort panel (low/default/max, any rejects)": P, "S-low": low, "S-default": default}


def ba(p, sample=ids):
    pos = [i for i in sample if defect[i]]
    neg = [i for i in sample if not defect[i]]
    return (sum(p[i] for i in pos) / len(pos) + sum(not p[i] for i in neg) / len(neg)) / 2


def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


nP, nN = sum(defect.values()), len(ids) - sum(defect.values())
say(f"{len(ids)} items ({nP} defective, {nN} clean); max asked on {len(need_max)} items both low and default approved")
say("  arm                                              BA      caught       false alarms")
for name, p in arms.items():
    say(f"  {name:<48} {ba(p):.3f}   {sum(p[i] for i in ids if defect[i])}/{nP}      {sum(p[i] for i in ids if not defect[i])}/{nN}")
rng = random.Random(4)
pos = [i for i in ids if defect[i]]
neg = [i for i in ids if not defect[i]]
boots = [[rng.choice(pos) for _ in pos] + [rng.choice(neg) for _ in neg] for _ in range(2000)]
result = {"n": len(ids), "max_asked": len(need_max), "arms": {k: round(ba(v), 4) for k, v in arms.items()}, "vs": {}}
wins, positive = [], []
for name, s in (("S-low", low), ("S-default", default)):
    d = ba(P) - ba(s)
    xs = sorted(ba(P, b) - ba(s, b) for b in boots)
    k1 = sum((P[i] == defect[i]) and (s[i] != defect[i]) for i in ids)
    k2 = sum((s[i] == defect[i]) and (P[i] != defect[i]) for i in ids)
    p = mcnemar(k1, k1 + k2)
    say(f"  P - {name}: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}]  only P {k1}, only {name} {k2}, McNemar p {p:.3f}")
    result["vs"][name] = {"d": round(d, 4), "ci": [round(xs[49], 4), round(xs[1949], 4)], "only_p": k1, "only_s": k2, "p": round(p, 4)}
    wins.append(p < 0.05 and xs[49] > 0)
    positive.append(d > 0)
verdict = "P WINS" if all(wins) else "not shown" if all(positive) else "no case"
say(f"  PREREGISTERED VERDICT: {verdict}")
result["verdict"] = verdict
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
