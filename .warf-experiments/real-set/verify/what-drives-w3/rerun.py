"""Rerun-noise proxies: the same persona and input asked twice. No strict persona was ever asked twice on these
items, so this measures ADVOCATE (real-set) and the plain question (evidence-set claude-x5) instead.

    python -B rerun.py
"""
import itertools
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SET = HERE.parents[1]
EXP = SET.parent


def load(d, arm):
    out = {}
    for p in sorted(Path(d).glob(f"{arm}.w*.jsonl")):
        for line in p.open(encoding="utf-8"):
            r = json.loads(line)
            out[r["planted"]["id"]] = r
    return out


def ba(rej, truth, ids):
    P = [i for i in ids if truth[i]]
    N = [i for i in ids if not truth[i]]
    return (sum(rej[i] for i in P) / len(P) + sum(not rej[i] for i in N) / len(N)) / 2


items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
truth = {it["id"]: it["kind"] == "defective" for it in items}
ids = list(truth)
adv = load(SET, "claude-advocate")
std = load(SET, "claude-standard")
a1 = {i: adv[i]["decision"] == "REJECT" for i in ids}
a2 = {i: [v for v in std[i]["votes"] if v["agent"] == "ADVOCATE"][0]["vote"] == -1 for i in ids}
same_prompt = all(std[i]["votes"][0]["persona"] == adv[i]["votes"][0]["persona"] for i in ids
                  if std[i]["votes"][0]["agent"] == "ADVOCATE")
dis = [i for i in ids if a1[i] != a2[i]]
print(f"real-set ADVOCATE arm vs ADVOCATE seat of W1: persona hash equal {same_prompt}; discordant {len(dis)}/132 "
      f"(defective {sum(truth[i] for i in dis)}, clean {len(dis) - sum(truth[i] for i in dis)})")
print(f"  BA arm {ba(a1, truth, ids):.3f}, BA seat {ba(a2, truth, ids):.3f}, diff {ba(a2, truth, ids) - ba(a1, truth, ids):+.3f}")
k1 = sum(a2[i] == truth[i] and a1[i] != truth[i] for i in ids)
k2 = sum(a1[i] == truth[i] and a2[i] != truth[i] for i in ids)
print(f"  only seat right {k1}, only arm right {k2}")

# evidence-set: five identical seats of the plain question; early stopping means not every seat answers
ev = EXP / "evidence-set"
eitems = [json.loads(l) for l in (ev / "items.jsonl").open(encoding="utf-8")]
etruth = {it["id"]: it["kind"] != "clean" for it in eitems}
x5 = load(ev, "claude-x5")
cl = load(ev, "claude")
seatvotes = {i: {v["agent"]: v["vote"] == -1 for v in r["votes"]} for i, r in x5.items()}
full = [i for i in seatvotes if len(seatvotes[i]) == 5]
print(f"\nevidence-set claude-x5: {len(seatvotes)} items, all five seats answered on {len(full)}")
seats = [f"CLAUDE-{k}" for k in range(1, 6)]
diffs = []
for s, t in itertools.combinations(seats, 2):
    common = [i for i in seatvotes if s in seatvotes[i] and t in seatvotes[i]]
    if sum(etruth[i] for i in common) and sum(not etruth[i] for i in common):
        d = ba({i: seatvotes[i][t] for i in common}, etruth, common) - ba({i: seatvotes[i][s] for i in common}, etruth, common)
        nd = sum(seatvotes[i][s] != seatvotes[i][t] for i in common)
        diffs.append((s, t, len(common), nd, d))
for s, t, n, nd, d in diffs:
    print(f"  {s} vs {t}: {n} common items, discordant {nd} ({nd / n:.3f}), BA diff {d:+.3f}")
for s in seats:
    common = [i for i in seatvotes if s in seatvotes[i] and i in cl]
    nd = sum(seatvotes[i][s] != (cl[i]["decision"] == "REJECT") for i in common)
    d = ba({i: seatvotes[i][s] for i in common}, etruth, common) - ba({i: cl[i]["decision"] == "REJECT" for i in common}, etruth, common)
    print(f"  {s} vs claude arm: {len(common)} items, discordant {nd} ({nd / len(common):.3f}), BA diff {d:+.3f}")

# what a rerun with per-item flip rate q does to claude-strict's BA on the 132 items (simulation)
S = {i: r["decision"] == "REJECT" for i, r in load(SET, "claude-strict").items()}
rng = random.Random(3)
for q in (0.03, 0.06, 0.08):
    sims = []
    for _ in range(4000):
        r = {i: (not S[i]) if rng.random() < q else S[i] for i in ids}
        sims.append(ba(r, truth, ids) - ba(S, truth, ids))
    sims.sort()
    print(f"\nsimulated rerun of claude-strict, each answer flipped with prob {q}: BA change "
          f"median {sims[2000]:+.3f}, 95% range [{sims[100]:+.3f}, {sims[3899]:+.3f}]")
