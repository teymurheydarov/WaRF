"""Independent recomputation of score.log and of the panel verdicts (no import of score_planted.py, no warf import).

Implements docs/spec/logodds-aggregation.md §3-§5 from scratch on the stored answers and writes
mine.jsonl (per-item verdicts) and recompute.log next to this file."""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]          # .warf-experiments/planted
SEATS = ("claude", "jev", "laya")
GROUP = {"claude": "claude_cli/claude-opus-5-5", "jev": "jev/jev-latest", "laya": "laya/multilingual"}
BOUNDARY = {"lt", "le", "gt", "ge"}
out = []


def say(s=""):
    out.append(s)
    print(s)


# ---- constants, re-derived from the spec / engine definitions ---------------------------------
P1, P0, AE, BE = 0.80, 0.30, 0.05, 0.10
A_B = math.log((1 - BE) / AE)
B_B = math.log(BE / (1 - AE))
LLR_A = math.log(P1 / P0)
LLR_R = math.log((1 - P1) / (1 - P0))
THETA = {"LOGIC": 0.0, "SECURITY": 0.2, "PERFORMANCE": -0.1}
LN2 = math.log(2)
OMEGA = 0.5                     # alpha = beta = 1, last_updated None in every profile


def logit(q):
    return math.log(q / (1 - q))


def tau(domain):
    return logit((1 + THETA[domain]) / 2)


# ---- data --------------------------------------------------------------------------------------
items = [json.loads(l) for l in (EXP / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "planted" for it in items}
recs = {s: {} for s in SEATS}
for s in SEATS:
    for p in sorted(EXP.glob(f"{s}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l)
            assert r["planted"]["id"] not in recs[s]
            recs[s][r["planted"]["id"]] = r
ids = [it["id"] for it in items if all(it["id"] in recs[s] for s in SEATS)]
bases = sorted({by_id[i]["base"] for i in ids})
assert all(f"{b}:{k}" in ids for b in bases for k in ("clean", "planted"))
say(f"{len(bases)} bases with all six answers ({len(ids)} items); answers per seat: "
    + ", ".join(f"{s} {len(recs[s])}" for s in SEATS))


def readout_p(body):
    """p(REJECT) as WaRF's readout would render and read it (two decimals, both present, sum ~1), clamped."""
    pr = body["answers"]["verdict"]["probabilities"]
    pa, pj = float(f"{float(pr.get('APPROVE') or 0):.2f}"), float(f"{float(pr.get('REJECT') or 0):.2f}")
    if abs(pa + pj - 1) > 0.05:
        return None
    return min(0.99, max(0.01, pj))


ans = {s: {} for s in SEATS}     # (vote, p or None)
for i in ids:
    rep = recs["claude"][i]["planted"]["call"]["reply"]
    w = rep.split()[0].upper().rstrip(".,:")
    v = 1 if w == "APPROVE" else -1 if w == "REJECT" else None
    assert v == recs["claude"][i]["votes"][0]["vote"], i
    ans["claude"][i] = (v, None)
    for s in ("jev", "laya"):
        body = recs[s][i]["planted"]["call"]["body"]
        v = 1 if body["answers"]["verdict"]["choice"].upper() == "APPROVE" else -1
        assert v == recs[s][i]["votes"][0]["vote"], (s, i)
        ans[s][i] = (v, readout_p(body))

# ---- folds, as score_planted defines them (seed 7, shuffled sorted bases, k % 5) --------------
rng = random.Random(7)
order = bases[:]
rng.shuffle(order)
fold = {b: k % 5 for k, b in enumerate(order)}


# ---- my own MAP Platt fit: damped Newton, convergence on the gradient ------------------------
def logpost(a, b, rs, ys):
    t = -0.5 * a * a - 0.5 * (b - 1) ** 2
    for r, y in zip(rs, ys):
        z = (a + b * r) * (1 if y == 1 else -1)
        t -= math.log1p(math.exp(-z)) if z > 0 else (-z + math.log1p(math.exp(z)))
    return t


def platt(rs, ys):
    a, b = 0.0, 1.0
    for it in range(200):
        ga, gb, haa, hab, hbb = -a, 1 - b, 1.0, 0.0, 1.0
        for r, y in zip(rs, ys):
            s = 1 / (1 + math.exp(-(a + b * r)))
            t = 1.0 if y == 1 else 0.0
            ga += t - s
            gb += (t - s) * r
            w = s * (1 - s)
            haa += w; hab += w * r; hbb += w * r * r
        if math.hypot(ga, gb) < 1e-12:
            break
        d = haa * hbb - hab * hab
        da, db = (hbb * ga - hab * gb) / d, (haa * gb - hab * ga) / d
        f0, step = logpost(a, b, rs, ys), 1.0
        while logpost(a + step * da, b + step * db, rs, ys) < f0 and step > 1e-12:
            step /= 2
        a, b = a + step * da, b + step * db
    nc = sum(y == 1 for y in ys)
    return a, b, logit((nc + 1) / (len(ys) + 2)), it


def calibrate(train_ids):
    """{seat: calibration} from the labelled single-seat answers on train_ids."""
    cal = {}
    for s in SEATS:
        votes = [(ans[s][i][0], ans[s][i][1], 1 if not defect[i] else -1) for i in train_ids]
        pairs = [(math.log((1 - p) / p), y) for _, p, y in votes if p is not None]
        if sum(y == 1 for _, y in pairs) >= 10 and sum(y == -1 for _, y in pairs) >= 10:
            a, b, pl, _ = platt([r for r, _ in pairs], [y for _, y in pairs])
            platt_fit = (a, b, pl)
        else:
            platt_fit = None
        cl = [v for v, _, y in votes if y == 1]
        de = [v for v, _, y in votes if y == -1]
        rates = (cl, de) if len(cl) >= 5 and len(de) >= 5 else None
        cal[s] = (platt_fit, rates)
    return cal


def evidence(s, vote, p, cal):
    platt_fit, rates = cal[s] if cal else (None, None)
    if p is not None and (p - 0.5) * vote > 0:
        p = None
    if p is not None:
        r = math.log((1 - p) / p)
        if platt_fit is None:
            return max(OMEGA * LLR_R, min(OMEGA * LLR_A, r)), "capped"
        a, b, pl = platt_fit
        return a + b * r - pl, "platt"
    if rates is None:
        return OMEGA * (LLR_A if vote == 1 else LLR_R), "omega"
    cl, de = rates
    pc = (sum(v == vote for v in cl) + 1) / (len(cl) + 2)
    pd = (sum(v == vote for v in de) + 1) / (len(de) + 2)
    return math.log(pc / pd), "rates"


def disagree(means):
    return any(m >= LN2 for m in means) and any(m <= -LN2 for m in means)


def review(i, cal):
    means, tags = [], []
    for s in SEATS:                                  # one seat per model: every step ends a whole model
        e, tag = evidence(s, *ans[s][i], cal)
        means.append(e); tags.append(tag)
        lam = sum(means)
        if not disagree(means):
            if lam >= A_B:
                return {"decision": "APPROVE", "confidence": "HIGH", "lambda": lam, "asked": len(means), "ev": means, "tags": tags}
            if lam <= B_B:
                return {"decision": "REJECT", "confidence": "HIGH", "lambda": lam, "asked": len(means), "ev": means, "tags": tags}
    t = tau(by_id[i]["domain"])
    dec = "APPROVE" if lam >= t else "REJECT"
    conf = "LOW" if abs(lam - t) < LN2 or disagree(means) else "MEDIUM"
    return {"decision": dec, "confidence": conf, "lambda": lam, "asked": 3, "ev": means, "tags": tags}


calibrated, cold, fits = {}, {}, {}
for k in range(5):
    train = [i for i in ids if fold[by_id[i]["base"]] != k]
    cal = calibrate(train)
    fits[k] = cal
    for i in ids:
        if fold[by_id[i]["base"]] == k:
            calibrated[i] = review(i, cal)
            cold[i] = review(i, None)

with (HERE / "mine.jsonl").open("w", encoding="utf-8") as f:
    for i in ids:
        f.write(json.dumps({"id": i, "fold": fold[by_id[i]["base"]], "cal": calibrated[i], "cold": cold[i]}) + "\n")
with (HERE / "fits.json").open("w", encoding="utf-8") as f:
    json.dump({k: {s: {"platt": c[s][0], "rates": None if c[s][1] is None else
                       [sum(v == 1 for v in c[s][1][0]), len(c[s][1][0]), sum(v == 1 for v in c[s][1][1]), len(c[s][1][1])]}
                   for s in SEATS} for k, c in fits.items()}, f, indent=1)

# ---- score.log, recomputed ---------------------------------------------------------------------
reject = {
    "Claude alone": {i: recs["claude"][i]["decision"] == "REJECT" for i in ids},
    "Mixed panel, log-odds (calibrated out of fold)": {i: calibrated[i]["decision"] == "REJECT" for i in ids},
    "Mixed panel, log-odds (cold start)": {i: cold[i]["decision"] == "REJECT" for i in ids},
    "  member: Jev alone": {i: recs["jev"][i]["decision"] == "REJECT" for i in ids},
    "  member: Laya alone": {i: recs["laya"][i]["decision"] == "REJECT" for i in ids},
}
score = {
    "Claude alone (vote)": {i: float(reject["Claude alone"][i]) for i in ids},
    "Mixed panel, -Lambda (calibrated)": {i: -calibrated[i]["lambda"] for i in ids},
    "Mixed panel, -Lambda (cold start)": {i: -cold[i]["lambda"] for i in ids},
    "  member: Jev p(REJECT)": {i: recs["jev"][i]["planted"]["call"]["body"]["answers"]["verdict"]["probabilities"]["REJECT"] for i in ids},
    "  member: Laya p(REJECT)": {i: recs["laya"][i]["planted"]["call"]["body"]["answers"]["verdict"]["probabilities"]["REJECT"] for i in ids},
}


def ba(rj, sample):
    P = [i for i in sample if defect[i]]
    N = [i for i in sample if not defect[i]]
    return (sum(rj[i] for i in P) / len(P) + sum(not rj[i] for i in N) / len(N)) / 2


def auc(sc, sample):
    P = [sc[i] for i in sample if defect[i]]
    N = [sc[i] for i in sample if not defect[i]]
    return sum((p > n) + 0.5 * (p == n) for p in P for n in N) / (len(P) * len(N))


def items_of(bs):
    return [i for i in ids if by_id[i]["base"] in bs]


subsets = {"all": bases,
           "without boundary swaps": [b for b in bases if by_id[f"{b}:planted"]["operator"] not in BOUNDARY]}
brng = random.Random(4)
for name, bs in subsets.items():
    sample = items_of(bs)
    boots = [items_of([brng.choice(bs) for _ in bs]) for _ in range(2000)]
    say(f"\n== {name}: {len(bs)} bases, {len(sample)} items ==")
    say("Verdict: balanced accuracy [95 %, bootstrap over bases], planted caught, clean passed, pairs fully right")
    for arm, rj in reject.items():
        b = ba(rj, sample)
        xs = sorted(ba(rj, s) for s in boots)
        caught = sum(rj[f"{x}:planted"] for x in bs)
        passed = sum(not rj[f"{x}:clean"] for x in bs)
        pairs = sum(rj[f"{x}:planted"] and not rj[f"{x}:clean"] for x in bs)
        say(f"  {arm:<48} {b:.3f} [{xs[49]:.3f}, {xs[1949]:.3f}]   {caught}/{len(bs)}   {passed}/{len(bs)}   {pairs}/{len(bs)}")
    say("Ranking: AUC")
    for arm, sc in score.items():
        say(f"  {arm:<48} {auc(sc, sample):.3f}")
    say("Panel minus Claude alone, balanced accuracy, paired over bases [95 %]; items only one gets right")
    for arm in ("Mixed panel, log-odds (calibrated out of fold)", "Mixed panel, log-odds (cold start)"):
        d = ba(reject[arm], sample) - ba(reject["Claude alone"], sample)
        xs = sorted(ba(reject[arm], s) - ba(reject["Claude alone"], s) for s in boots)
        right = {a: {i: reject[a][i] == defect[i] for i in sample} for a in (arm, "Claude alone")}
        only_p = sum(right[arm][i] and not right["Claude alone"][i] for i in sample)
        only_c = sum(right["Claude alone"][i] and not right[arm][i] for i in sample)
        say(f"  {arm}: {d:+.3f} [{xs[49]:+.3f}, {xs[1949]:+.3f}]   only panel {only_p}, only Claude {only_c}")

say("\n== The calibrated panel ==")
bands = {}
for i in ids:
    c = calibrated[i]["confidence"]
    n, k = bands.get(c, (0, 0))
    bands[c] = (n + 1, k + (reject["Mixed panel, log-odds (calibrated out of fold)"][i] == defect[i]))
say("  right per confidence band: " + ", ".join(f"{c} {k}/{n}" for c, (n, k) in sorted(bands.items())))
asked = [calibrated[i]["asked"] for i in ids]
say("  seats asked: " + ", ".join(f"{k} {asked.count(k)}" for k in (1, 2, 3)))
tags = {}
for i in ids:
    for s, t in zip(SEATS, calibrated[i]["tags"][:calibrated[i]["asked"]]):
        tags.setdefault(s.upper(), set()).add(t)
say("  calibration used: " + "; ".join(f"{a} {sorted(t)}" for a, t in tags.items()))
flips = sum(reject["Mixed panel, log-odds (calibrated out of fold)"][i] != reject["Claude alone"][i] for i in ids)
say(f"  verdict differs from Claude alone on {flips} of {len(ids)} items")
cost = sum(float((recs["jev"][i]["planted"]["call"]["body"].get("usage") or {}).get("cost") or 0) for i in ids)
say(f"\nJev cost ${cost:.4f}; Laya truncated: {sum(bool((recs['laya'][i]['planted']['call']['body'].get('usage') or {}).get('truncated')) for i in ids)} of {len(ids)}")
(HERE / "recompute.log").write_text("\n".join(out) + "\n", encoding="utf-8")
