"""Score the five-Laya panel (sessions.jsonl) and the planted-line control (controls.jsonl)
against the git-history labels of selection.jsonl. Pure Python: numpy's BLAS crashes in
gs\\cf\\python.exe.

An agent's final position is its Round-2 vote, or its Round-1 vote where the SPRT stopped the
review before the debate: the votes WaRF's oracle would credit (apply_oracle). The debate's own
effect, controlled for each agent's Round-1 p and tested by changing only the summary, is in
debate/ (analysis.py, counterfactual.py).

    python .warf-experiments/laya-five/score_five.py"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
THETA = {"LOGIC": 0.0, "SECURITY": 0.2, "PERFORMANCE": -0.1}

sel = {s["id"]: s for s in map(json.loads, (HERE / "selection.jsonl").open(encoding="utf-8"))}
R = [r for r in map(json.loads, (HERE / "sessions.jsonl").open(encoding="utf-8")) if r["five"]["id"] in sel]
y = [r["five"]["label"] == "REJECT" for r in R]
S = [sel[r["five"]["id"]] for r in R]


def auc(score, pos):
    P = [s for s, t in zip(score, pos) if t]
    N = [s for s, t in zip(score, pos) if not t]
    a = sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    return a, math.sqrt(max(0.0, a * (1 - a) + (len(P) - 1) * (q1 - a * a) + (len(N) - 1) * (q2 - a * a)) / (len(P) * len(N)))


def paired_diff(s1, s2, pos, n=2000, seed=5):
    """AUC(s1) - AUC(s2) on the same items, with a 95 % interval from resampling the items
    within each label."""
    P = [i for i, t in enumerate(pos) if t]
    N = [i for i, t in enumerate(pos) if not t]
    rng = random.Random(seed)
    d = []
    for _ in range(n):
        idx = [rng.choice(P) for _ in P] + [rng.choice(N) for _ in N]
        yy = [pos[i] for i in idx]
        d.append(auc([s1[i] for i in idx], yy)[0] - auc([s2[i] for i in idx], yy)[0])
    d.sort()
    return auc(s1, pos)[0] - auc(s2, pos)[0], d[int(0.025 * n)], d[int(0.975 * n) - 1]


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


def sign_test(k, n):
    """Two-sided binomial p-value for k of n successes at 1/2."""
    tail = sum(math.comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def p(r, rnd, agent):
    return r["five"][rnd][agent]["p_reject"]


def final(r, agent):
    """(p_reject, choice) of the agent's final position."""
    a = r["five"]["round2"].get(agent) or r["five"]["round1"][agent]
    return a["p_reject"], a["choice"]


def round1_decision(r):
    if "debate" in r or not r["sprt_fired"]:    # Round 1 exhausted the pool: WaRF's synthesis
        return "APPROVE" if r["normalised_score"] >= THETA[r["domain"]] else "REJECT"
    return r["decision"]                         # the SPRT stopped Round 1


debated = sum("debate" in r for r in R)
out = {"n": len(R), "later_fixed": sum(y), "debated": debated}
print(f"\n  {len(R)} commits, {sum(y)} later fixed; five Laya agents, uniform priors (omega 0.5), debate on "
      f"({debated} debated, {len(R) - debated} stopped by the SPRT in Round 1)\n")
print(f"  {'':<28} {'Round 1 AUC':>13} {'final AUC':>13} {'mean p':>8} {'REJECT votes R1/final':>22}")
rows = {}
for a in AGENTS:
    a1, s1 = auc([p(r, "round1", a) for r in R], y)
    af, sf = auc([final(r, a)[0] for r in R], y)
    m = sum(p(r, "round1", a) for r in R) / len(R)
    v1 = sum(r["five"]["round1"][a]["choice"] == "REJECT" for r in R)
    vf = sum(final(r, a)[1] == "REJECT" for r in R)
    rows[a] = {"auc_r1": a1, "se_r1": s1, "auc_final": af, "se_final": sf, "mean_p_r1": m,
               "reject_r1": v1, "reject_final": vf}
    print(f"  {a:<28} {a1:>7.3f} ±{s1:.3f} {af:>7.3f} ±{sf:.3f} {m:>8.3f} {v1:>11}/{vf:<3}")
out["agents"] = rows

mean1 = [sum(p(r, "round1", a) for a in AGENTS) / 5 for r in R]
meanf = [sum(final(r, a)[0] for a in AGENTS) / 5 for r in R]
nrej1 = [sum(r["five"]["round1"][a]["choice"] == "REJECT" for a in AGENTS) for r in R]
nrejf = [sum(final(r, a)[1] == "REJECT" for a in AGENTS) for r in R]
out["panel"] = {}
for name, s1, sf in (("mean p of the five", mean1, meanf), ("number of REJECT votes", nrej1, nrejf)):
    (a1, e1), (af, ef) = auc(s1, y), auc(sf, y)
    out["panel"][name] = {"r1": a1, "final": af}
    print(f"  {'panel: ' + name:<28} {a1:>7.3f} ±{e1:.3f} {af:>7.3f} ±{ef:.3f}")

final_reject = [r["decision"] == "REJECT" for r in R]
first = [round1_decision(r) for r in R]
tp = sum(f and t for f, t in zip(final_reject, y))
fp = sum(f and not t for f, t in zip(final_reject, y))
print(f"\n  WaRF's decision: REJECT on {sum(final_reject)} of {len(R)} ({tp} later fixed, {fp} never fixed); "
      f"balanced accuracy {auc([float(f) for f in final_reject], y)[0]:.3f}")
print(f"    before the debate: REJECT on {sum(d == 'REJECT' for d in first)} "
      f"({sum(d == 'REJECT' and t for d, t in zip(first, y))} later fixed); SPRT fired on {sum(r['sprt_fired'] for r in R)}")
conf = {}
for r in R:
    conf[(r["decision"], r["confidence"])] = conf.get((r["decision"], r["confidence"]), 0) + 1
print(f"    decisions by confidence: {', '.join(f'{d} {c}: {k}' for (d, c), k in sorted(conf.items()))}")
out["decision"] = {"reject": sum(final_reject), "tp": tp, "fp": fp,
                   "by_confidence": {f"{d} {c}": k for (d, c), k in conf.items()}}

print("\n  the same 100 commits, earlier runs")
refs = {
    "single Laya, sweep question": [s["p_single_laya"] for s in S],
    "single Laya, debate (alone)": [s["p_single_debate"]["alone"] for s in S],
    "single Laya, debate (Claude)": [s["p_single_debate"]["real"] for s in S],
    "Claude (blinded), p(defect)": [s["p_claude"] for s in S],
    "patch characters": [s["patch_chars"] for s in S],
    "state tokens": [s["state_tokens"] for s in S],
}
out["references"] = {}
for name, score in refs.items():
    a, se = auc(score, y)
    out["references"][name] = a
    print(f"  {name:<28} {a:>7.3f} ±{se:.3f}")

single = refs["single Laya, sweep question"]
print("\n  panel minus single Laya, same commits (95 % interval, resampling commits within each label)")
out["panel_minus_single"] = {}
for name, score in (("mean p, Round 1", mean1), ("mean p, final", meanf)):
    d, lo, hi = paired_diff(score, single, y)
    out["panel_minus_single"][name] = [d, lo, hi]
    print(f"  {name:<28} {d:+.3f} [{lo:+.3f}, {hi:+.3f}]")

rng = random.Random(3)
perm = []
for _ in range(400):
    yy = y[:]
    rng.shuffle(yy)
    perm.append(auc(mean1, yy)[0])
print(f"\n  shuffled labels: mean of five, AUC {sum(perm) / len(perm):.3f} over {len(perm)} shuffles "
      f"(2.5 to 97.5 %: {sorted(perm)[10]:.3f} to {sorted(perm)[389]:.3f})")

print("\n  how alike the five are: correlation of Round-1 p(REJECT) across the 100 commits")
cols = {a: [p(r, "round1", a) for r in R] for a in AGENTS}
cols["single Laya"] = single
names = list(cols)
print("  " + " " * 14 + "".join(f"{n[:9]:>10}" for n in names))
for n1 in names:
    print(f"  {n1[:14]:<14}" + "".join(f"{corr(cols[n1], cols[n2]):>10.2f}" for n2 in names))
spread = [max(p(r, "round1", a) for a in AGENTS) - min(p(r, "round1", a) for a in AGENTS) for r in R]
unanimous = sum(len({r["five"]["round1"][a]["choice"] for a in AGENTS}) == 1 for r in R)
print(f"  all five vote alike on {unanimous} of {len(R)}; mean spread of p within a commit {sum(spread) / len(spread):.3f}")
between = [sum(p(r, "round1", a) for r in R) / len(R) for a in AGENTS]
print(f"  persona means range {min(between):.3f} to {max(between):.3f}: the persona sets the level; "
      f"across commits the five move together")
out["unanimous_r1"] = unanimous

D = [r for r in R if len(r["five"]["round2"]) == 5]
if D:
    yd = [r["five"]["label"] == "REJECT" for r in D]
    m1 = [sum(p(r, "round1", a) for a in AGENTS) / 5 for r in D]
    m2 = [sum(p(r, "round2", a) for a in AGENTS) / 5 for r in D]
    d, lo, hi = paired_diff(m2, m1, yd)
    print(f"\n  debate, on the {len(D)} debated commits: AUC of the mean p {auc(m1, yd)[0]:.3f} -> {auc(m2, yd)[0]:.3f} "
          f"({d:+.3f} [{lo:+.3f}, {hi:+.3f}])")
    toward_all = changed_all = 0
    for a in AGENTS:
        ch = [r for r in D if r["five"]["round1"][a]["choice"] != r["five"]["round2"][a]["choice"]]
        toward = sum((r["five"]["round2"][a]["choice"] == "REJECT") == (r["five"]["label"] == "REJECT") for r in ch)
        toward_all, changed_all = toward_all + toward, changed_all + len(ch)
        shift = sum(p(r, "round2", a) - p(r, "round1", a) for r in D) / len(D)
        cut = sum(bool(r["five"]["round2"][a]["usage"].get("state_tokens_dropped")) for r in D)
        print(f"  {a:<14} changed {len(ch):>3} votes ({toward} toward the label), mean p shift {shift:+.3f}, "
              f"summary cut in {cut:>2} of {len(D)}")
    print(f"  all agents: {toward_all} of {changed_all} changed votes toward the label, "
          f"sign test p = {sign_test(toward_all, changed_all):.2g}")
    out["debate"] = {"auc_r1": auc(m1, yd)[0], "auc_r2": auc(m2, yd)[0], "diff": [d, lo, hi],
                     "toward": toward_all, "changed": changed_all}

cpath = HERE / "controls.jsonl"
if cpath.exists():
    C = [r for r in map(json.loads, cpath.open(encoding="utf-8")) if r["five"]["id"] in sel]
    base = {r["five"]["id"]: r for r in R}
    print("\n  control: one line planted after the first added line of the never-fixed changes (Round 1)")
    print(f"  {'':<14}" + "".join(f"{n:>30}" for n in ("null dereference", "BUG comment")))
    for a in AGENTS:
        cells = []
        for plant in ("null dereference", "BUG comment"):
            pairs = [(p(base[c["five"]["id"]], "round1", a), p(c, "round1", a)) for c in C
                     if c["five"]["plant"] == plant and c["five"]["id"] in base]
            k = sum(after > before for before, after in pairs)
            if pairs:
                cells.append(f"{sum(b for b, _ in pairs) / len(pairs):.3f} -> {sum(x for _, x in pairs) / len(pairs):.3f}"
                             f" ({100 * k / len(pairs):.0f} % rose)")
            else:
                cells.append("-")
        print(f"  {a:<14}" + "".join(f"{c:>30}" for c in cells))
    for plant in ("null dereference", "BUG comment"):
        pairs = [(sum(p(base[c["five"]["id"]], "round1", a) for a in AGENTS),
                  sum(p(c, "round1", a) for a in AGENTS)) for c in C
                 if c["five"]["plant"] == plant and c["five"]["id"] in base]
        k = sum(after > before for before, after in pairs)
        if pairs:
            print(f"  mean of five, {plant}: rose in {k} of {len(pairs)}, sign test p = {sign_test(k, len(pairs)):.2g}")

(HERE / "score.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
