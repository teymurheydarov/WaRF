"""Recompute every number in score.log without importing score_real.py (pure Python). W2's verdicts come from
w2_independent.json (spec-derived, run w2_independent.py first; identical item by item to replay_w2.json).
Prints the recomputed log and a line-by-line diff against score.log.

    python -B recompute.py
"""
import json
import random
from fractions import Fraction
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
SET = HERE.parents[1]
items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "defective" for it in items}
recs = {}
for arm in ("claude", "claude-strict", "claude-advocate", "claude-standard", "jev"):
    recs[arm] = {}
    for path in sorted(SET.glob(f"{arm}.w*.jsonl")):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            recs[arm][r["planted"]["id"]] = r
ids = [it["id"] for it in items if all(it["id"] in recs[a] for a in recs)]
w2 = json.loads((HERE / "w2_independent.json").read_text(encoding="utf-8"))["items"]
rep = json.loads((HERE / "replay_w2.json").read_text(encoding="utf-8"))["items"]
assert all(w2[i]["decision"] == rep[i]["decision"] for i in ids)

SINGLE = {"claude": "one Claude", "claude-strict": "one Claude, strict bar", "claude-advocate": "ADVOCATE alone"}
WARF = {"claude-standard": "W1 WaRF five personas", "mixed": "W2 WaRF Claude+Jev log-odds"}
NAMES = {**SINGLE, **WARF, "jev": "Jev alone (W2's seat)"}
rej = {a: {i: recs[a][i]["decision"] == "REJECT" for i in ids} for a in recs}
rej["mixed"] = {i: w2[i]["decision"] == "REJECT" for i in ids}
P_all = [i for i in ids if defect[i]]
N_all = [i for i in ids if not defect[i]]
out = []


def say(s=""):
    out.append(s)


def ba_exact(arm, sample):
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    return (Fraction(sum(rej[arm][i] for i in P), len(P)) + Fraction(sum(not rej[arm][i] for i in N), len(N))) / 2


def ba(arm, sample):
    # float version for bootstrap (same arithmetic as a plain mean of two rates)
    np_ = nr = nn = na = 0
    for i in sample:
        if defect[i]:
            np_ += 1
            nr += rej[arm][i]
        else:
            nn += 1
            na += not rej[arm][i]
    return (nr / np_ + na / nn) / 2


def mcnemar_exact(k, n):
    if n == 0:
        return Fraction(1)
    tail = sum(comb(n, j) for j in range(0, min(k, n - k) + 1))
    return min(Fraction(1), Fraction(2 * tail, 2 ** n))


say(f"{len(ids)} of {len(items)} items answered by every arm ({len(P_all)} defective, {len(N_all)} clean)")
for title, sample in (("all items", ids), ("defects both judges call visible from the diff, with all clean items",
                                           [i for i in ids if not defect[i] or by_id[i].get("visible") == "diff"])):
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    say(f"\n== {title}: {len(P)} defective, {len(N)} clean ==")
    say("  arm                              BA      recall     false alarms")
    for arm in (*SINGLE, *WARF, "jev"):
        say(f"  {NAMES[arm]:<32} {float(ba_exact(arm, sample)):.3f}   {sum(rej[arm][i] for i in P)}/{len(P)}"
            f"      {sum(rej[arm][i] for i in N)}/{len(N)}")

# stratified paired bootstrap: 2000 resamples, Random(4); each resample draws |P| defective then |N| clean ids
brng = random.Random(4)
boots = []
for _ in range(2000):
    s = [brng.choice(P_all) for _ in P_all]
    s += [brng.choice(N_all) for _ in N_all]
    boots.append(s)
say("\n== Preregistered comparisons (all items): WaRF arm minus single-call arm ==")
cmp = {}
alt = {}
for w in WARF:
    for s in SINGLE:
        d = float(ba_exact(w, ids) - ba_exact(s, ids))
        xs = sorted(ba(w, b) - ba(s, b) for b in boots)
        lo, hi = xs[49], xs[1949]                  # 2.5 % and 97.5 % order statistics (50th and 1950th of 2000)
        alt[(w, s)] = (xs[50], xs[1950], sum(x <= 0 for x in xs) / 2000)
        k1 = sum(rej[w][i] == defect[i] and rej[s][i] != defect[i] for i in ids)
        k2 = sum(rej[s][i] == defect[i] and rej[w][i] != defect[i] for i in ids)
        p = mcnemar_exact(k1, k1 + k2)
        cmp[(w, s)] = (d, lo, hi, k1, k2, p)
        say(f"  {NAMES[w]} - {NAMES[s]}: {d:+.3f} [{lo:+.3f}, {hi:+.3f}]  only WaRF {k1}, only single {k2}, "
            f"McNemar p {float(p):.3f}")

# preregistered verdict, README wording: a WaRF arm wins if it beats EACH single-call arm with McNemar p below
# its Holm threshold (two WaRF arms: 0.025 for the smaller p, 0.05 for the other) and a bootstrap lower bound > 0.
arm_p = {w: max(cmp[(w, s)][5] for s in SINGLE) for w in WARF}
order = sorted(WARF, key=lambda w: arm_p[w])
holm = {order[0]: 0.025, order[1]: 0.05}
say("\n== Preregistered verdict ==")
won = []
for w in WARF:
    beats_all = all(cmp[(w, s)][0] > 0 and cmp[(w, s)][1] > 0 for s in SINGLE)
    say(f"  {NAMES[w]}: worst p over single arms {float(arm_p[w]):.3f} (Holm threshold {holm[w]}), "
        f"bootstrap lower bound > 0 against all: {beats_all}")
    if beats_all and arm_p[w] < holm[w]:
        won.append(w)
# strict Holm step-down (the second arm is tested only if the first is rejected) gives the same here
step = []
if arm_p[order[0]] < 0.025:
    step.append(order[0])
    if arm_p[order[1]] < 0.05:
        step.append(order[1])
if won:
    verdict = "WaRF wins: " + ", ".join(NAMES[w] for w in won)
elif any(all(cmp[(w, s)][0] > 0 for s in SINGLE) for w in WARF):
    verdict = "favours WaRF, not shown"
else:
    verdict = "no case for WaRF"
say(f"  VERDICT: {verdict}")
calls = {a: sum(len(recs[a][i]["planted"].get("calls", [0])) for i in ids) for a in SINGLE}
calls["claude-standard"] = sum(len(recs["claude-standard"][i]["planted"]["calls"]) for i in ids)
say("\n  calls: " + ", ".join(f"{NAMES[a]} {c}" for a, c in calls.items()) + f"; W2 uses claude + jev ({len(ids)} each)")

mine = "\n".join(out) + "\n"
theirs = (SET / "score.log").read_text(encoding="utf-8")
print(mine)
ml, tl = mine.splitlines(), theirs.splitlines()
diffs = [(n, a, b) for n, (a, b) in enumerate(zip(ml, tl), 1) if a != b]
print(f"=== diff vs score.log: {len(ml)} vs {len(tl)} lines, {len(diffs)} differing lines")
for n, a, b in diffs:
    print(f"  line {n}:\n    mine:   {a}\n    stored: {b}")
print("\n=== extra precision")
for (w, s), (d, lo, hi, k1, k2, p) in cmp.items():
    a50, a1950, frac = alt[(w, s)]
    print(f"  {w} - {s}: d={d:+.5f} CI[{lo:+.5f},{hi:+.5f}] alt order stats [{a50:+.5f},{a1950:+.5f}] "
          f"share of resamples <= 0: {frac:.3f}; McNemar p exact {p} = {float(p):.5f}")
print(f"  Holm step-down winners: {step or 'none'}; README-rule winners: {won or 'none'}")
for w in WARF:
    print(f"  {w}: positive d against every single arm: {all(cmp[(w, s)][0] > 0 for s in SINGLE)}; "
          f"d = {[round(cmp[(w, s)][0], 4) for s in SINGLE]}")
sj = json.loads((SET / "score.json").read_text(encoding="utf-8"))
bad = []
for arm, v in sj["arms"].items():
    if round(float(ba_exact(arm, ids)), 4) != v["ba"] or sum(rej[arm][i] for i in P_all) != v["recall"] \
            or sum(rej[arm][i] for i in N_all) != v["false_alarms"]:
        bad.append(arm)
for key, v in sj["comparisons"].items():
    w, s = key.split(" - ")
    d, lo, hi, k1, k2, p = cmp[(w, s)]
    if [round(d, 4), [round(lo, 4), round(hi, 4)], k1, k2, round(float(p), 4)] != [v["d"], v["ci"], v["only_warf"], v["only_single"], v["p"]]:
        bad.append(key)
print(f"  score.json mismatches: {bad or 'none'}; verdict matches: {sj['verdict'] == verdict}")
