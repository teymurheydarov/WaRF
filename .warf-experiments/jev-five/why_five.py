"""Why the five-agent panels add nothing. How alike the five agents are, what averaging can gain
at that likeness, and what averaging genuinely different reviewers gains on the same 100 commits.
Reads only stored scores; no model is asked. Pure Python: numpy's BLAS crashes in gs\\cf\\python.exe.

    python .warf-experiments/jev-five/why_five.py"""
import json
import math
import random
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
LAYA = HERE.parent / "laya-five"
AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
N01 = NormalDist()


def jl(path):
    return [json.loads(line) for line in path.open(encoding="utf-8")]


sel = jl(LAYA / "selection.jsonl")
ids = [s["id"] for s in sel]
y = [s["label"] == "REJECT" for s in sel]
one = {r["jev"]["id"]: r for r in jl(HERE / "sessions_one.jsonl")}
five = {r["jev"]["id"]: r for r in jl(HERE / "sessions_five.jsonl")}
lfive = {r["five"]["id"]: r for r in jl(LAYA / "sessions.jsonl")}
reruns = [{r["jev"]["id"]: r for r in jl(HERE / "verify" / "refute" / f"rerun_{x}.jsonl")} for x in "AB"]


def logit(p):
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


def auc(score, pos):
    """Chance that a later-fixed change scores above a never-fixed one, ties counted half."""
    order = sorted(range(len(score)), key=lambda i: score[i])
    rank = [0.0] * len(score)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and score[order[j + 1]] == score[order[i]]:
            j += 1
        for k in range(i, j + 1):
            rank[order[k]] = (i + j) / 2 + 1
        i = j + 1
    n1 = sum(pos)
    return (sum(r for r, t in zip(rank, pos) if t) - n1 * (n1 + 1) / 2) / (n1 * (len(pos) - n1))


def boot(stat, n=2000, seed=5):
    """stat(idx) on the commits and on resamples within each label: value and 95 % interval."""
    P = [i for i, t in enumerate(y) if t]
    N = [i for i, t in enumerate(y) if not t]
    rng = random.Random(seed)
    d = sorted(stat([rng.choice(P) for _ in P] + [rng.choice(N) for _ in N]) for _ in range(n))
    return stat(list(range(len(y)))), d[int(0.025 * n)], d[int(0.975 * n) - 1]


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb)


def within(x):
    """x minus its label's mean: what is left once the label is known."""
    m1 = sum(v for v, t in zip(x, y) if t) / sum(y)
    m0 = sum(v for v, t in zip(x, y) if not t) / (len(y) - sum(y))
    return [v - (m1 if t else m0) for v, t in zip(x, y)]


def zavg(members):
    """Equal-weight mean of the members' logits, each scaled to unit SD over all commits (no labels)."""
    zs = []
    for m in members:
        mu = sum(m) / len(m)
        sd = math.sqrt(sum((v - mu) ** 2 for v in m) / len(m))
        zs.append([(v - mu) / sd for v in m])
    return [sum(col) / len(col) for col in zip(*zs)]


def pj(rs, i, rnd, agent):
    return rs[i]["jev"][rnd][agent]["p_reject"]


S = {
    "Jev, one question": [pj(one, i, "round1", "JEV") for i in ids],
    "Jev, rerun A": [pj(reruns[0], i, "round1", "JEV") for i in ids],
    "Jev, rerun B": [pj(reruns[1], i, "round1", "JEV") for i in ids],
    "Laya, one question": [s["p_single_laya"] for s in sel],
    "Claude, blinded": [s["p_claude"] for s in sel],
}
for a in AGENTS:
    S[f"Jev {a}"] = [pj(five, i, "round1", a) for i in ids]
    S[f"Laya {a}"] = [lfive[i]["five"]["round1"][a]["p_reject"] for i in ids]
L = {k: [logit(p) for p in v] for k, v in S.items()}

GROUPS = (
    ("five Jev personas (Round 1)", [f"Jev {a}" for a in AGENTS]),
    ("five Laya personas (Round 1)", [f"Laya {a}" for a in AGENTS]),
    ("Jev asked three times", ["Jev, one question", "Jev, rerun A", "Jev, rerun B"]),
    ("Laya + Jev", ["Laya, one question", "Jev, one question"]),
    ("Jev + Claude", ["Jev, one question", "Claude, blinded"]),
    ("Laya + Jev + Claude", ["Laya, one question", "Jev, one question", "Claude, blinded"]),
)

print(f"\n  {len(ids)} commits, {sum(y)} later fixed (the five-Laya selection); stored scores only")
print("\n  1. How alike the members are: correlation of their logit p(REJECT) across commits,")
print("     overall and within each label (the part that is not signal)")
out = {}
for name, members in GROUPS:
    if not name.startswith("five"):
        continue
    print(f"\n  {name}")
    print("  " + " " * 14 + "".join(f"{m.split()[-1][:12]:>13}" for m in members))
    for m1 in members:
        print(f"  {m1.split()[-1][:14]:<14}" + "".join(
            f"{corr(L[m1], L[m2]):>13.2f}" if m1 != m2 else f"{'':>13}" for m2 in members))
    rej = [sum(p > 0.5 for p in S[m]) for m in members]
    print(f"  REJECT votes per persona: {', '.join(f'{m.split()[-1]} {k}' for m, k in zip(members, rej))}")

print("\n  2. What averaging gains, against what the binormal model predicts from the members alone.")
print("     n_eff = n / (1 + (n - 1) * mean within-label correlation): the number of independent")
print("     reviewers the members are worth. Prediction: AUC of the mean of the members' d' times")
print("     sqrt(n_eff); 'if independent' sets n_eff = n.")
print(f"\n  {'':<30} {'members AUC':>18} {'r within':>9} {'n_eff':>6} {'predicted':>10} {'if indep.':>10} {'observed':>9}")
for name, members in GROUPS:
    n = len(members)
    aucs = [auc(S[m], y) for m in members]
    W = [within(L[m]) for m in members]
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    rho = sum(corr(W[i], W[j]) for i, j in pairs) / len(pairs)
    n_eff = n / (1 + (n - 1) * rho)
    d = sum(math.sqrt(2) * N01.inv_cdf(a) for a in aucs) / n
    pred = N01.cdf(d * math.sqrt(n_eff) / math.sqrt(2))
    indep = N01.cdf(d * math.sqrt(n) / math.sqrt(2))
    combo = zavg([L[m] for m in members])
    obs = auc(combo, y)
    print(f"  {name:<30} {min(aucs):.3f} to {max(aucs):.3f} {rho:>9.2f} {n_eff:>6.2f} {pred:>10.3f} {indep:>10.3f} {obs:>9.3f}")
    best = max(members, key=lambda m: auc(S[m], y))

    def over_mean(idx, members=members, combo=combo):
        yy = [y[i] for i in idx]
        return auc([combo[i] for i in idx], yy) - sum(auc([L[m][i] for i in idx], yy) for m in members) / len(members)

    def over_best(idx, best=best, combo=combo):
        yy = [y[i] for i in idx]
        return auc([combo[i] for i in idx], yy) - auc([L[best][i] for i in idx], yy)

    g1, g2 = boot(over_mean), boot(over_best)
    print(f"  {'':<30} average beats its mean member by {g1[0]:+.3f} [{g1[1]:+.3f}, {g1[2]:+.3f}], "
          f"its best ({best}) by {g2[0]:+.3f} [{g2[1]:+.3f}, {g2[2]:+.3f}]")
    out[name] = {"members_auc": aucs, "rho_within": rho, "n_eff": n_eff, "predicted": pred,
                 "if_independent": indep, "observed": obs, "over_mean_member": g1, "over_best_member": [best, *g2]}

print("\n  3. WaRF's SPRT adds the five votes as five independent pieces of evidence.")
print("     Later-fixed share by the number of Jev REJECT votes in Round 1 (half of all commits are later fixed):")
by_k = {}
for i, t in zip(ids, y):
    k = sum(five[i]["jev"]["round1"][a]["choice"] == "REJECT" for a in AGENTS)
    by_k.setdefault(k, []).append(t)
for k in sorted(by_k):
    print(f"     {k} of 5 REJECT: {len(by_k[k]):>3} commits, {sum(by_k[k]):>2} later fixed ({sum(by_k[k]) / len(by_k[k]):.2f})")
for name, rs in (("one Jev agent", one), ("five-Jev panel", five)):
    cells = {}
    for i, t in zip(ids, y):
        cells.setdefault((rs[i]["decision"], rs[i]["confidence"]), []).append(t)
    print(f"     {name}: " + "; ".join(f"{d} {c} {len(v)} ({sum(v)} later fixed)" for (d, c), v in sorted(cells.items())))
out["reject_votes"] = {k: [len(v), sum(v)] for k, v in by_k.items()}
(HERE / "why_five.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
