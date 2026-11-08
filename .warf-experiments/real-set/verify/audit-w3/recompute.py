"""Independent recompute of score_commit.log (no import of score_commit.py or warf): single-arm metrics,
W3 derived from docs/spec/logodds-aggregation.md, McNemar, bootstrap, verdict. Writes w3_pure.json here."""
import json, math, random, re
from pathlib import Path
HERE = Path(__file__).resolve().parent
SET = HERE.parents[1]
ARMS = ["claude", "claude-strict", "claude-advocate", "claude-commit", "claude-commit-strict"]
items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "defective" for it in items}
recs = {}
for a in ARMS:
    recs[a] = {}
    for p in sorted(SET.glob(f"{a}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l)
            assert r["planted"]["id"] not in recs[a], (a, r["planted"]["id"])
            recs[a][r["planted"]["id"]] = r
ids = [it["id"] for it in items if all(it["id"] in recs[a] for a in ARMS)]
print(len(ids), "items answered by every arm")

def myvote(text):
    w = text.split()[0].upper().rstrip(".,:")
    if w == "APPROVE": return 1
    if w == "REJECT": return -1
    return 1 if re.search(r"\bAPPROVE\b", text, re.I) else -1
mism = 0
for a in ARMS:
    for i in ids:
        r = recs[a][i]
        v = r["votes"][0]["vote"]
        if myvote(r["planted"]["call"]["reply"]) != v or (v == -1) != (r["decision"] == "REJECT"): mism += 1
print("reply/vote/decision mismatches:", mism)
vote = {a: {i: recs[a][i]["votes"][0]["vote"] for i in ids} for a in ARMS}
reject = {a: {i: vote[a][i] == -1 for i in ids} for a in ARMS}

# ---- W3 from the spec ----
A = math.log(0.9 / 0.05); B = math.log(0.1 / 0.95); LN2 = math.log(2)
THETA = None
src = (SET.parents[1] / "warf" / "engine.py").read_text(encoding="utf-8")
m = re.search(r"THETA\s*=\s*\{([^}]*)\}", src); THETA = eval("{" + m.group(1) + "}")
tau = {d: math.log(((1 + t) / 2) / (1 - (1 + t) / 2)) for d, t in THETA.items()}
print("tau", {d: round(t, 3) for d, t in tau.items()}, "A", round(A, 3), "B", round(B, 3))
rng = random.Random(7); fold = {}
for cls in (True, False):
    mem = [i for i in ids if defect[i] == cls]; rng.shuffle(mem)
    for k, i in enumerate(mem): fold[i] = k % 5
SEATS = ["claude-strict", "claude-commit-strict"]
w3 = {}; leak = 0
for k in range(5):
    train = [i for i in ids if fold[i] != k]
    test = [i for i in ids if fold[i] == k]
    leak += len(set(train) & set(test))
    ev = {}
    for s in SEATS:
        cl = [vote[s][i] for i in train if not defect[i]]; de = [vote[s][i] for i in train if defect[i]]
        assert len(cl) >= 5 and len(de) >= 5
        ev[s] = {v: math.log(((cl.count(v) + 1) / (len(cl) + 2)) / ((de.count(v) + 1) / (len(de) + 2))) for v in (1, -1)}
    for i in test:
        e1 = ev[SEATS[0]][vote[SEATS[0]][i]]
        if e1 >= A or e1 <= B:
            w3[i] = {"decision": "APPROVE" if e1 >= A else "REJECT", "seats": 1, "lam": e1, "e": [e1], "how": "stop1"}
            continue
        e2 = ev[SEATS[1]][vote[SEATS[1]][i]]
        lam = e1 + e2
        dis = (e1 >= LN2 or e2 >= LN2) and (e1 <= -LN2 or e2 <= -LN2)
        if not dis and lam >= A: d, how = "APPROVE", "stop2"
        elif not dis and lam <= B: d, how = "REJECT", "stop2"
        else:
            t = tau[by_id[i]["domain"]]; d = "APPROVE" if lam >= t else "REJECT"
            how = "exhausted" + ("-disagree" if dis else "")
        w3[i] = {"decision": d, "seats": 2, "lam": lam, "e": [e1, e2], "how": how}
    print(f"fold {k}: train {len(train)} test {len(test)}  e(strict) A {ev[SEATS[0]][1]:+.3f} R {ev[SEATS[0]][-1]:+.3f}"
          f"  e(commit) A {ev[SEATS[1]][1]:+.3f} R {ev[SEATS[1]][-1]:+.3f}")
print("fold overlap (train & test):", leak)
reject["w3"] = {i: w3[i]["decision"] == "REJECT" for i in ids}
from collections import Counter
print("W3 seats:", Counter(w3[i]["seats"] for i in ids), "how:", Counter(w3[i]["how"] for i in ids))
print("W3 vs AND/OR of seats:", sum(reject["w3"][i] == (reject[SEATS[0]][i] and reject[SEATS[1]][i]) for i in ids), "AND,",
      sum(reject["w3"][i] == (reject[SEATS[0]][i] or reject[SEATS[1]][i]) for i in ids), "OR of 132")
dom = Counter(by_id[i]["domain"] for i in ids); print("domains", dom)

NAMES = {"claude": "one Claude", "claude-strict": "one Claude, strict", "claude-advocate": "ADVOCATE alone",
         "claude-commit": "one Claude, whole commit", "claude-commit-strict": "one Claude, whole commit, strict", "w3": "W3"}
def ba(a, s):
    P = [i for i in s if defect[i]]; N = [i for i in s if not defect[i]]
    return (sum(reject[a][i] for i in P) / len(P) + sum(not reject[a][i] for i in N) / len(N)) / 2
def mcn(k, n):
    if n == 0: return 1.0
    return min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)
for title, s in (("all", ids), ("visible diff", [i for i in ids if not defect[i] or by_id[i].get("visible") == "diff"]),
                 ("needs other file", [i for i in ids if not defect[i] or by_id[i].get("visible") == "needs_other_file"])):
    P = [i for i in s if defect[i]]; N = [i for i in s if not defect[i]]
    print(f"== {title}: {len(P)} def {len(N)} clean")
    for a in ARMS + ["w3"]:
        print(f"  {NAMES[a]:<34} {ba(a, s):.3f}  {sum(reject[a][i] for i in P)}/{len(P)}  {sum(reject[a][i] for i in N)}/{len(N)}")
br = random.Random(4); Pi = [i for i in ids if defect[i]]; Ni = [i for i in ids if not defect[i]]
boots = [[br.choice(Pi) for _ in Pi] + [br.choice(Ni) for _ in Ni] for _ in range(2000)]
rows = {}
for s in ARMS:
    d = ba("w3", ids) - ba(s, ids)
    xs = sorted(ba("w3", b) - ba(s, b) for b in boots)
    k1 = sum(reject["w3"][i] == defect[i] and reject[s][i] != defect[i] for i in ids)
    k2 = sum(reject[s][i] == defect[i] and reject["w3"][i] != defect[i] for i in ids)
    p = mcn(k1, k1 + k2); rows[s] = (d, xs[49], xs[1949], p, xs[50], xs[1950])
    print(f"  W3 - {NAMES[s]}: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}] (alt idx 50/1950: [{xs[50]:+.3f}, {xs[1950]:+.3f}])"
          f" only W3 {k1}, only single {k2}, p {p:.3f}")
won = all(r[1] > 0 and r[3] < 0.05 for r in rows.values())
fav = all(r[0] > 0 for r in rows.values())
print("VERDICT:", "W3 wins" if won else "favours W3, not shown" if fav else "no case for W3")
json.dump({i: w3[i] for i in ids}, (HERE / "w3_pure.json").open("w"), indent=0)
json.dump(fold, (HERE / "folds.json").open("w"))
