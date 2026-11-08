"""All four Claude arms on this answer key, on the labels as given and on corrected labels.

Arms (../planted/run_planted.py --set .warf-experiments/evidence-set), all Claude Opus 5.5:
  claude           one agent, the sweep's question
  claude-strict    one agent, told to reject only for a defect the change introduces (STRICT_PERSONA)
  claude-x5        the sweep's question asked by five identical seats, WaRF's default review (majority)
  claude-standard  WaRF's default five personas, WaRF's default review (majority)

Corrected labels: one Claude's 25 rejected clean items were classed by hand-checked Claude judges
(verify/critic/rescore.py): 16 hold a real defect in the committed code, 4 are debatable, 5 are false
alarms. "real" counts those 16 clean items as right to REJECT; "real + debatable" counts all 20. A clean
item outside the 25 that a new arm rejects was never classed, counts as a false alarm, and is listed.

Paired comparisons: exact two-sided McNemar on the items only one arm gets right, and 2000 paired
bootstrap resamples over bases (a base drawn twice counts twice) for the balanced-accuracy difference.

    python .warf-experiments/evidence-set/score_all.py     # writes score_all.log"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = {"claude": "one Claude", "claude-strict": "one Claude, strict bar",
        "claude-x5": "same question x5", "claude-standard": "WaRF five personas"}
REAL = set("06377a8 2a29aa6 2f8cd81 38858cf 3cf80c7 5853a6f 5f9ae79 6fc3f69 8058d91 890cd00 8ca586f "
           "9b1851c af41faa c826b44 da35b0c e42bec0".split())
DEBATABLE = set("15977e9 a86cf94 d9fca63 db3aca7".split())
FALSE = set("0696ac5 6c02814 a880e56 bfbe226 c0c88af".split())
out = []


def say(s=""):
    out.append(s)
    print(s)


items = {it["id"]: it for it in map(json.loads, (HERE / "items.jsonl").open(encoding="utf-8"))}
recs = {}
for arm in ARMS:
    recs[arm] = {}
    for path in sorted(HERE.glob(f"{arm}.w*.jsonl")):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if r["planted"]["id"] in recs[arm]:
                raise SystemExit(f"{arm}: {r['planted']['id']} twice")
            recs[arm][r["planted"]["id"]] = r
bases = sorted({it["base"] for it in items.values()})
bases = [b for b in bases if all(f"{b}:{k}" in recs[a] for a in ARMS for k in ("clean", "planted"))]
say(f"{len(bases)} of 50 bases reviewed by all four arms")
reject = {a: {i: r["decision"] == "REJECT" for i, r in recs[a].items()} for a in ARMS}
short = {b: b.split(":")[0] for b in bases}
LABELS = {"labels as given": set(), "real": REAL, "real + debatable": REAL | DEBATABLE}


def truth(i, defect):
    b, kind = i.rsplit(":", 1)
    return kind == "planted" or short[b] in defect


def ba(arm, bs, defect):
    P = [f"{b}:{k}" for b in bs for k in ("clean", "planted") if truth(f"{b}:{k}", defect)]
    N = [f"{b}:{k}" for b in bs for k in ("clean", "planted") if not truth(f"{b}:{k}", defect)]
    return (sum(reject[arm][i] for i in P) / len(P) + sum(not reject[arm][i] for i in N) / len(N)) / 2


def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


rng = random.Random(4)
boots = [[rng.choice(bases) for _ in bases] for _ in range(2000)]
ids = [f"{b}:{k}" for b in bases for k in ("clean", "planted")]
for name, defect in LABELS.items():
    say(f"\n== {name} ==")
    say("  arm                       BA      planted caught  clean rejected (of them real/debatable/false/unclassed)")
    for arm, label in ARMS.items():
        cr = [b for b in bases if reject[arm][f"{b}:clean"]]
        cls = [sum(short[b] in s for b in cr) for s in (REAL, DEBATABLE, FALSE)]
        say(f"  {label:<25} {ba(arm, bases, defect):.3f}   {sum(reject[arm][f'{b}:planted'] for b in bases)}/{len(bases)}"
            f"           {len(cr)} ({cls[0]}/{cls[1]}/{cls[2]}/{len(cr) - sum(cls)})")
    for a1, a2 in (("claude-standard", "claude"), ("claude-strict", "claude"), ("claude-x5", "claude"),
                   ("claude-standard", "claude-strict"), ("claude-standard", "claude-x5")):
        d = ba(a1, bases, defect) - ba(a2, bases, defect)
        xs = sorted(ba(a1, s, defect) - ba(a2, s, defect) for s in boots)
        right = {a: {i: reject[a][i] == truth(i, defect) for i in ids} for a in (a1, a2)}
        k1 = sum(right[a1][i] and not right[a2][i] for i in ids)
        k2 = sum(right[a2][i] and not right[a1][i] for i in ids)
        say(f"  {ARMS[a1]} - {ARMS[a2]}: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}]  only first {k1}, "
            f"only second {k2}, McNemar p {mcnemar(k1, k1 + k2):.3f}")

say("\n== clean items rejected by a new arm but never classed ==")
for arm in ("claude-strict", "claude-x5"):
    extra = [b for b in bases if reject[arm][f"{b}:clean"] and short[b] not in REAL | DEBATABLE | FALSE]
    say(f"  {ARMS[arm]}: {extra}")

say("\n== does the same question asked again give the same answer? ==")
agree = n = 0
same_as_one = n1 = 0
splits = {}
for i in ids:
    votes = [v["vote"] for v in recs["claude-x5"][i]["votes"]]
    key = (i.rsplit(":", 1)[1], len(votes), votes.count(-1))
    splits[key] = splits.get(key, 0) + 1
    agree += len(set(votes)) == 1
    n += 1
    same_as_one += (votes[0] == -1) == reject["claude"][i]
    n1 += 1
say(f"  x5 seats unanimous on {agree} of {n} items; first x5 seat equals one Claude's vote on {same_as_one} of {n1}")
say("  (kind, seats asked, REJECT votes): " + ", ".join(f"{k}: {v}" for k, v in sorted(splits.items())))
say("  calls: " + ", ".join(f"{ARMS[a]} {sum(len(recs[a][i]['planted'].get('calls', [0])) for i in ids)}" for a in ARMS))
(HERE / "score_all.log").write_text("\n".join(out) + "\n", encoding="utf-8")
