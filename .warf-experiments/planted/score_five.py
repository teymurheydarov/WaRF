"""Five Claudes against one: WaRF's default five personas on Claude Opus 5.5 (claude-standard) against
Claude alone (claude), on the planted set of plant.py. Right answer: REJECT for a planted item,
APPROVE for its clean original.

Reported on all 54 bases and on the cleaned set of verify/testcheck/ (hand classification, not
blinded): without the harmless, dead and non-compiling plants, and without the 8 clean originals that
hold a defect Claude named. Intervals: 2000 paired bootstrap resamples over bases (a base drawn twice
counts twice); exact two-sided McNemar on the items only one arm gets right. The clean items Claude
alone rejected are listed by their hand class, with the five-Claude verdict on each.

    python .warf-experiments/planted/score_five.py      # writes score_five.log and score_five.json"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = {"claude": "Claude alone", "claude-standard": "Five Claudes (WaRF default panel)"}
# verify/testcheck/rescore.py and its report, numbered by the planted items' order in items.jsonl
HARMLESS, NOCOMPILE, DEAD = {15, 18, 22, 31, 33}, {17, 32, 35, 47, 54}, {46, 50}
ORIG_DEFECT = {5, 7, 26, 31, 36, 39, 52, 53}
CLEAN_ALARM = {**{k: "real defect in the original" for k in ORIG_DEFECT}, 47: "minor real",
               8: "judgement call", 9: "judgement call", 18: "judgement call", 30: "judgement call",
               3: "false alarm", 35: "false alarm", 48: "false alarm", 54: "false alarm"}
out = []


def say(s=""):
    out.append(s)
    print(s)


items = [json.loads(line) for line in (HERE / "items.jsonl").open(encoding="utf-8")]
planted = [it for it in items if it["kind"] == "planted"]
num = {it["base"]: k + 1 for k, it in enumerate(planted)}
recs = {}
for arm in ARMS:
    recs[arm] = {}
    for path in sorted(HERE.glob(f"{arm}.w*.jsonl")):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if r["planted"]["id"] in recs[arm]:
                raise SystemExit(f"{arm}: {r['planted']['id']} twice")
            recs[arm][r["planted"]["id"]] = r
bases = [b for b in num if all(f"{b}:{k}" in recs[a] for a in ARMS for k in ("clean", "planted"))]
say(f"{len(bases)} of {len(num)} bases reviewed by both arms")
reject = {a: {i: r["decision"] == "REJECT" for i, r in recs[a].items()} for a in ARMS}


def ba(arm, bs):
    return (sum(reject[arm][f"{b}:planted"] for b in bs) + sum(not reject[arm][f"{b}:clean"] for b in bs)) / (2 * len(bs))


def mcnemar(k, n):
    """Exact two-sided p for k of n discordant items going one way."""
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, j) for j in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


subsets = {"all": bases,
           "cleaned (no harmless/dead/non-compiling plants, no defective originals)":
               [b for b in bases if num[b] not in HARMLESS | NOCOMPILE | DEAD | ORIG_DEFECT]}
rng = random.Random(4)
result = {}
for name, bs in subsets.items():
    boots = [[rng.choice(bs) for _ in bs] for _ in range(2000)]
    say(f"\n== {name}: {len(bs)} bases ==")
    say("  balanced accuracy [95 %]   planted caught   clean passed")
    for arm, label in ARMS.items():
        xs = sorted(ba(arm, s) for s in boots)
        caught = sum(reject[arm][f"{b}:planted"] for b in bs)
        passed = sum(not reject[arm][f"{b}:clean"] for b in bs)
        say(f"  {label:<36} {ba(arm, bs):.3f} [{xs[49]:.3f}, {xs[1949]:.3f}]   {caught}/{len(bs)}   {passed}/{len(bs)}")
        result.setdefault(name, {})[arm] = {"ba": round(ba(arm, bs), 4), "ci": [round(xs[49], 4), round(xs[1949], 4)],
                                            "caught": caught, "passed": passed, "n": len(bs)}
    d = ba("claude-standard", bs) - ba("claude", bs)
    xs = sorted(ba("claude-standard", s) - ba("claude", s) for s in boots)
    ids = [f"{b}:{k}" for b in bs for k in ("clean", "planted")]
    truth = {i: i.endswith(":planted") for i in ids}
    only5 = [i for i in ids if (reject["claude-standard"][i] == truth[i]) and (reject["claude"][i] != truth[i])]
    only1 = [i for i in ids if (reject["claude"][i] == truth[i]) and (reject["claude-standard"][i] != truth[i])]
    say(f"  five minus one: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}]; only five right {len(only5)}, "
        f"only one right {len(only1)}, McNemar p {mcnemar(len(only5), len(only5) + len(only1)):.3f}")
    say(f"    only five right: {only5}")
    say(f"    only one right:  {only1}")
    result[name]["five_minus_one"] = {"d": round(d, 4), "ci": [round(xs[49], 4), round(xs[1949], 4)],
                                      "only_five": only5, "only_one": only1}

say("\n== Claude alone's REJECTs of clean items, by hand class, and the five Claudes' verdict ==")
for b in bases:
    i = f"{b}:clean"
    if reject["claude"][i]:
        five = recs["claude-standard"][i]
        votes = "".join("R" if v["vote"] == -1 else "A" for v in five["votes"])
        say(f"  #{num[b]:<3}{CLEAN_ALARM.get(num[b], 'unclassified'):<29} five: {five['decision']:<8}"
            f"{five['confidence']:<7} votes {votes}  {b}")

say("\n== How the five seats vote ==")
splits = {}
for b in bases:
    for k in ("clean", "planted"):
        r = recs["claude-standard"][f"{b}:{k}"]
        key = (len(r["votes"]), sum(v["vote"] == -1 for v in r["votes"]))
        splits[key] = splits.get(key, 0) + 1
say("  (seats asked, REJECT votes): items  " + ", ".join(f"{k}: {v}" for k, v in sorted(splits.items())))
per_seat = {}
for b in bases:
    for k in ("clean", "planted"):
        for v in recs["claude-standard"][f"{b}:{k}"]["votes"]:
            s = per_seat.setdefault(v["agent"], {"clean": [0, 0], "planted": [0, 0]})
            s[k][0] += v["vote"] == -1
            s[k][1] += 1
say("  REJECT rate per seat, clean / planted: " + "; ".join(
    f"{a} {s['clean'][0]}/{s['clean'][1]} / {s['planted'][0]}/{s['planted'][1]}" for a, s in per_seat.items()))
agree = sum(reject["claude"][f"{b}:{k}"] == reject["claude-standard"][f"{b}:{k}"] for b in bases for k in ("clean", "planted"))
say(f"  verdict equals Claude alone on {agree} of {2 * len(bases)} items")
calls = sum(len(recs["claude-standard"][f"{b}:{k}"]["planted"]["calls"]) for b in bases for k in ("clean", "planted"))
say(f"  Claude calls: {calls}")
(HERE / "score_five.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score_five.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
