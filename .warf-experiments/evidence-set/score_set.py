"""Score reviewers on this answer key (items.jsonl: 50 bases, each clean = APPROVE and planted = REJECT).

Arms, from ../planted/run_planted.py --set .warf-experiments/evidence-set:
  claude            one Claude Opus 5.5 agent, the sweep's question
  claude-standard   WaRF's default five personas on Claude Opus 5.5, default review (majority at
                    uniform weights, early stop after four REJECTs)

Reported: balanced accuracy, planted caught, clean passed, with 2000 paired bootstrap resamples over
bases (a base drawn twice counts twice); the difference five minus one with exact two-sided McNemar on
the items only one arm gets right; planted catches per plant kind; the five seats' vote splits.

    python .warf-experiments/evidence-set/score_set.py      # writes score.log and score.json"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = {"claude": "One Claude", "claude-standard": "Five Claudes (WaRF default panel)"}
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
            i = r["planted"]["id"]
            if i in recs[arm]:
                raise SystemExit(f"{arm}: {i} twice")
            if items[i]["kind"] != r["planted"]["kind"]:
                raise SystemExit(f"{arm}: {i} kind mismatch")
            recs[arm][i] = r
bases = sorted({it["base"] for it in items.values()})
bases = [b for b in bases if all(f"{b}:{k}" in recs[a] for a in ARMS for k in ("clean", "planted"))]
say(f"{len(bases)} of 50 bases reviewed by both arms")
reject = {a: {i: r["decision"] == "REJECT" for i, r in recs[a].items()} for a in ARMS}


def ba(arm, bs):
    return (sum(reject[arm][f"{b}:planted"] for b in bs) + sum(not reject[arm][f"{b}:clean"] for b in bs)) / (2 * len(bs))


def mcnemar(k, n):
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


rng = random.Random(4)
boots = [[rng.choice(bases) for _ in bases] for _ in range(2000)]
result = {"n_bases": len(bases), "arms": {}}
say("\n  balanced accuracy [95 %]   planted caught   clean passed")
for arm, label in ARMS.items():
    xs = sorted(ba(arm, s) for s in boots)
    caught = sum(reject[arm][f"{b}:planted"] for b in bases)
    passed = sum(not reject[arm][f"{b}:clean"] for b in bases)
    say(f"  {label:<34} {ba(arm, bases):.3f} [{xs[49]:.3f}, {xs[1949]:.3f}]   {caught}/{len(bases)}   {passed}/{len(bases)}")
    result["arms"][arm] = {"ba": round(ba(arm, bases), 4), "ci": [round(xs[49], 4), round(xs[1949], 4)],
                           "caught": caught, "passed": passed}
ids = [f"{b}:{k}" for b in bases for k in ("clean", "planted")]
truth = {i: i.endswith(":planted") for i in ids}
only5 = [i for i in ids if reject["claude-standard"][i] == truth[i] and reject["claude"][i] != truth[i]]
only1 = [i for i in ids if reject["claude"][i] == truth[i] and reject["claude-standard"][i] != truth[i]]
d = ba("claude-standard", bases) - ba("claude", bases)
xs = sorted(ba("claude-standard", s) - ba("claude", s) for s in boots)
le0 = sum(x <= 0 for x in xs) / len(xs)
say(f"\n  five minus one: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}], <= 0 in {le0:.1%} of resamples; "
    f"only five right {len(only5)}, only one right {len(only1)}, McNemar p {mcnemar(len(only5), len(only5) + len(only1)):.3f}")
say(f"    only five right: {only5}")
say(f"    only one right:  {only1}")
result["five_minus_one"] = {"d": round(d, 4), "ci": [round(xs[49], 4), round(xs[1949], 4)],
                            "only_five": only5, "only_one": only1}

say("\n  planted caught per plant kind (one / five)")
kinds = sorted({items[f"{b}:planted"]["operator"] for b in bases})
for k in kinds:
    bs = [b for b in bases if items[f"{b}:planted"]["operator"] == k]
    say(f"    {k:<12} {sum(reject['claude'][f'{b}:planted'] for b in bs)}/{len(bs)}"
        f"   {sum(reject['claude-standard'][f'{b}:planted'] for b in bs)}/{len(bs)}")
say("  missed plants:")
for b in bases:
    i = f"{b}:planted"
    if not (reject["claude"][i] and reject["claude-standard"][i]):
        votes = "".join("R" if v["vote"] == -1 else "A" for v in recs["claude-standard"][i]["votes"])
        say(f"    {b:<34} {items[i]['operator']:<12} one {recs['claude'][i]['decision']:<8} five {votes}")
say("  clean items rejected:")
for b in bases:
    i = f"{b}:clean"
    if reject["claude"][i] or reject["claude-standard"][i]:
        votes = "".join("R" if v["vote"] == -1 else "A" for v in recs["claude-standard"][i]["votes"])
        say(f"    {b:<34} one {recs['claude'][i]['decision']:<8} five {votes}")

splits = {}
for i in ids:
    r = recs["claude-standard"][i]
    key = (items[i]["kind"], len(r["votes"]), sum(v["vote"] == -1 for v in r["votes"]))
    splits[key] = splits.get(key, 0) + 1
say("\n  five Claudes, (kind, seats asked, REJECT votes): items")
say("    " + ", ".join(f"{k}: {v}" for k, v in sorted(splits.items())))
calls = sum(len(recs["claude-standard"][i]["planted"]["calls"]) for i in ids)
say(f"  Claude calls: one {len(ids)}, five {calls}")
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
