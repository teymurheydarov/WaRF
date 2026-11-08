"""What drives W3: discordant items, OR/AND rules of the two strict seats, rerun proxies, power.
Reads replay_w3.json (from replay_w3.py) and the arm records; writes nothing but stdout.

    python -B analyse.py
"""
import glob
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SET = HERE.parents[1]
EXP = SET.parent
items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "defective" for it in items}
rep = json.loads((HERE / "replay_w3.json").read_text(encoding="utf-8"))


def load(d, arm):
    out = {}
    for p in sorted(Path(d).glob(f"{arm}.w*.jsonl")):
        for line in p.open(encoding="utf-8"):
            r = json.loads(line)
            out[r["planted"]["id"]] = r
    return out


ARMS = ("claude", "claude-strict", "claude-advocate", "claude-commit", "claude-commit-strict")
recs = {a: load(SET, a) for a in ARMS}
ids = [it["id"] for it in items]
rej = {a: {i: recs[a][i]["decision"] == "REJECT" for i in ids} for a in ARMS}
rej["W3"] = {i: rep["items"][i]["decision"] == "REJECT" for i in ids}
S, C = rej["claude-strict"], rej["claude-commit-strict"]
rej["OR"] = {i: S[i] or C[i] for i in ids}
rej["AND"] = {i: S[i] and C[i] for i in ids}
P = [i for i in ids if defect[i]]
N = [i for i in ids if not defect[i]]


def metrics(r, sample=ids):
    p = [i for i in sample if defect[i]]
    n = [i for i in sample if not defect[i]]
    tp = sum(r[i] for i in p); fp = sum(r[i] for i in n); fn = len(p) - tp; tn = len(n) - fp
    ba = (tp / len(p) + tn / len(n)) / 2
    acc = (tp + tn) / len(sample)
    prec = tp / (tp + fp) if tp + fp else float("nan")
    f1 = 2 * tp / (2 * tp + fp + fn)
    den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = (tp * tn - fp * fn) / den if den else float("nan")
    return dict(ba=ba, acc=acc, recall=f"{tp}/{len(p)}", fa=f"{fp}/{len(n)}", prec=prec, f1=f1, mcc=mcc)


def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


def cmp(a, b, sample=ids):
    k1 = sum((rej[a][i] == defect[i]) and (rej[b][i] != defect[i]) for i in sample)
    k2 = sum((rej[b][i] == defect[i]) and (rej[a][i] != defect[i]) for i in sample)
    return k1, k2, mcnemar(k1, k1 + k2)


# ---- evidence table ----
print("== W3 evidence per (seat vote) pattern ==")
pat = {}
for i in ids:
    it = rep["items"][i]
    v = tuple((x["agent"], x["vote"]) for x in it["votes"])
    key = (S[i], C[i], len(it["votes"]), it["decision"])
    pat.setdefault(key, []).append(i)
for key, members in sorted(pat.items(), key=lambda kv: -len(kv[1])):
    ev = [tuple(round(x["evidence"], 2) for x in rep["items"][i]["votes"]) for i in members]
    lam = sorted({round(rep["items"][i]["lambda"], 2) for i in members})
    print(f"  strict={'R' if key[0] else 'A'} commit={'R' if key[1] else 'A'} seats={key[2]} W3={key[3]}: "
          f"n={len(members)} (defective {sum(defect[i] for i in members)}), evidence {sorted(set(ev))}, Lambda {lam}")
print("  calibration tags:", sorted({x['calibration'] for i in ids for x in rep['items'][i]['votes']}))
print("  domains:", {d: sum(1 for i in ids if by_id[i]['domain'] == d) for d in ('LOGIC', 'SECURITY', 'PERFORMANCE')})

print("\n== W3 vs OR / AND ==")
for rule in ("OR", "AND"):
    diff = [i for i in ids if rej["W3"][i] != rej[rule][i]]
    print(f"  W3 != {rule}: {len(diff)} items {diff}")

print("\n== metrics, all 132 ==")
print(f"  {'arm':<22}{'BA':>7}{'acc':>7}{'recall':>9}{'FA':>8}{'prec':>7}{'F1':>7}{'MCC':>7}   vs W3 (only W3 / only arm / McNemar p)")
for a in ("W3", "OR", "AND", "claude-strict", "claude-commit-strict", "claude-advocate", "claude", "claude-commit"):
    m = metrics(rej[a])
    c = cmp("W3", a) if a != "W3" else ("", "", "")
    print(f"  {a:<22}{m['ba']:7.3f}{m['acc']:7.3f}{m['recall']:>9}{m['fa']:>8}{m['prec']:7.3f}{m['f1']:7.3f}{m['mcc']:7.3f}   {c}")
for title, sub in (("visible from diff", "diff"), ("needs other file", "needs_other_file")):
    sample = [i for i in ids if not defect[i] or by_id[i].get("visible") == sub]
    print(f"  -- {title}: " + ", ".join(f"{a} {metrics(rej[a], sample)['ba']:.3f} ({metrics(rej[a], sample)['recall']})"
                                        for a in ("W3", "OR", "AND", "claude-strict", "claude-commit-strict")))

print("\n== seat agreement ==")
both = {(S[i], C[i], defect[i]) for i in ids}
for s in (True, False):
    for c in (True, False):
        m = [i for i in ids if S[i] == s and C[i] == c]
        print(f"  strict {'R' if s else 'A'} commit {'R' if c else 'A'}: {len(m)} (defective {sum(defect[i] for i in m)}, clean {len(m) - sum(defect[i] for i in m)})")

print("\n== discordant items ==")
for other in ("claude-commit-strict", "claude-strict"):
    diff = [i for i in ids if rej["W3"][i] != rej[other][i]]
    print(f"  W3 vs {other}: {len(diff)}")
    for i in diff:
        it = rep["items"][i]
        print(f"    {i}  truth={'REJECT' if defect[i] else 'APPROVE'} visible={by_id[i].get('visible')} "
              f"strict={'R' if S[i] else 'A'} commit-strict={'R' if C[i] else 'A'} W3={it['decision']} "
              f"Lambda={it['lambda']:+.3f} ev={[(x['agent'], round(x['evidence'], 3)) for x in it['votes']]} "
              f"domain={it['domain']} conf={it['confidence']}")

# ---- rerun proxies ----
print("\n== rerun proxies (same prompt, same input) ==")
std = load(SET, "claude-standard")
adv = recs["claude-advocate"]
agree = n = 0
for i in ids:
    seat = [v for v in std[i]["votes"] if v["agent"] == "ADVOCATE"]
    if seat:
        n += 1
        agree += (seat[0]["vote"] == -1) == rej["claude-advocate"][i]
print(f"  real-set ADVOCATE arm vs ADVOCATE seat of claude-standard: agree {agree}/{n}")
ev = EXP / "evidence-set"
eitems = [json.loads(l) for l in (ev / "items.jsonl").open(encoding="utf-8")]
edef = {it["id"]: it["kind"] != "clean" for it in eitems}
x5 = load(ev, "claude-x5")
ecl = load(ev, "claude")
pairs = []
for i, r in x5.items():
    vs = {v["agent"]: v["vote"] for v in r["votes"]}
    pairs.append(vs)
nseat = sum(len(v) for v in pairs)
print(f"  evidence-set claude-x5: {len(pairs)} items, {nseat} seat votes")
dis = tot = 0
for vs in pairs:
    keys = sorted(vs)
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            tot += 1
            dis += vs[keys[a]] != vs[keys[b]]
print(f"  pairwise seat disagreement within an item (plain persona): {dis}/{tot} = {dis / tot:.3f}" if tot else "")
dis = tot = 0
for i, r in x5.items():
    if i in ecl:
        for v in r["votes"]:
            tot += 1
            dis += (v["vote"] == -1) != (ecl[i]["decision"] == "REJECT")
print(f"  x5 seat vs evidence-set claude arm: disagree {dis}/{tot} = {dis / tot:.3f}" if tot else "")

# BA spread of a 'rerun' of claude-strict: flip each item's answer with prob q (from the proxy discordance)
print("\n== power ==")
# observed discordance between W3 and each strict arm
for other in ("claude-strict", "claude-commit-strict"):
    k1, k2, p = cmp("W3", other)
    d = (k1 - k2) / 132
    pd = (k1 + k2) / 132
    print(f"  W3 vs {other}: only W3 {k1}, only arm {k2}, discordance {pd:.3f}, accuracy gain {d:+.4f}")


def power_mcnemar(n, p10, p01, alpha=0.05, sims=4000, seed=1):
    rng = random.Random(seed)
    hit = 0
    for _ in range(sims):
        k1 = k2 = 0
        for _ in range(n):
            u = rng.random()
            if u < p10:
                k1 += 1
            elif u < p10 + p01:
                k2 += 1
        if k1 > k2 and mcnemar(k1, k1 + k2) < alpha:
            hit += 1
    return hit / sims


def n_needed(p10, p01, target=0.8):
    # analytic (Connor 1987) normal approximation for paired proportions, two-sided 0.05
    za, zb = 1.959964, 0.841621
    pd, d = p10 + p01, p10 - p01
    return math.ceil((za * math.sqrt(pd) + zb * math.sqrt(pd - d * d)) ** 2 / (d * d))


# BA gain with balanced classes equals the accuracy gain (equal class sizes), so d_BA = (k1-k2)/n.
for label, k1, k2 in (("vs claude-strict (4/1)", 4, 1), ("vs claude-commit-strict (4/2)", 4, 2)):
    p10, p01 = k1 / 132, k2 / 132
    n = n_needed(p10, p01)
    sim = {m: power_mcnemar(m, p10, p01) for m in (132, n // 2, n, 2 * n)}
    print(f"  {label}: d={(k1 - k2) / 132:+.4f}, analytic n for 80% power = {n} items; "
          f"simulated exact-McNemar power {', '.join(f'n={m}: {v:.2f}' for m, v in sim.items())}")
# rule of thumb: what d would be detectable at n=132 with the observed discordance
for pd in (5 / 132, 6 / 132):
    for n in (132, 264, 500, 1000, 2000):
        # smallest d with analytic power >= 0.8
        za, zb = 1.959964, 0.841621
        d = (za * math.sqrt(pd) + zb * math.sqrt(pd)) / math.sqrt(n)
        print(f"  discordance {pd:.3f}, n={n}: minimum detectable gain about {d:.3f}")
