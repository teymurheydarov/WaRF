"""W2 re-derived from docs/spec/logodds-aggregation.md alone (no warf import), from the stored claude and jev
answers, with score_real.py's fold assignment (5 folds stratified by class, random.Random(7), defective class
shuffled first). Compares item by item with replay_w2.json (run replay_w2.py first). Writes w2_independent.json.

    python -B w2_independent.py
"""
import json
import math
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SET = HERE.parents[1]
THETA = {"LOGIC": 0.0, "SECURITY": 0.2, "PERFORMANCE": -0.1}
A = math.log(0.90 / 0.05)
B = math.log(0.10 / 0.95)
LN2 = math.log(2)
MIN_PLATT, MIN_RATES = 10, 5


def logit(q):
    return math.log(q / (1 - q))


def sig(x):
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def clamp(p):
    return min(0.99, max(0.01, p))


TAG = "decision model, no reasoning"
PRE = re.compile(r"p\(APPROVE\)=([0-9.]+)\s+p\(REJECT\)=([0-9.]+)")


def readout(text):
    """§7: p(REJECT) only from a tagged decision answer carrying both probabilities summing to 1 +- 0.05."""
    if TAG not in text:
        return None
    m = PRE.search(text)
    if not m:
        return None
    pa, pr = float(m.group(1)), float(m.group(2))
    if abs(pa + pr - 1) > 0.05:
        return None
    return clamp(pr)


def platt(rs, ys):
    """MAP logistic regression of y=clean on r, prior a~N(0,1), b~N(1,1); Newton with step halving."""
    t = [1.0 if y == 1 else 0.0 for y in ys]

    def lp(a, b):
        s = 0.0
        for r, ti in zip(rs, t):
            z = a + b * r
            s += ti * z - (max(z, 0) + math.log1p(math.exp(-abs(z))))
        return s - a * a / 2 - (b - 1) ** 2 / 2

    a, b = 0.0, 1.0
    cur = lp(a, b)
    for it in range(200):
        ga, gb = -a, -(b - 1)
        haa, hab, hbb = -1.0, 0.0, -1.0
        for r, ti in zip(rs, t):
            q = sig(a + b * r)
            ga += ti - q
            gb += (ti - q) * r
            w = q * (1 - q)
            haa -= w
            hab -= w * r
            hbb -= w * r * r
        det = haa * hbb - hab * hab
        da = -(hbb * ga - hab * gb) / det
        db = -(-hab * ga + haa * gb) / det
        step = 1.0
        while True:
            na, nb = a + step * da, b + step * db
            new = lp(na, nb)
            if new >= cur - 1e-15 or step < 1e-12:
                break
            step /= 2
        a, b, cur = na, nb, new
        if math.hypot(da, db) * step < 1e-13:
            return a, b, it + 1
    return a, b, None


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

# fold assignment as stated in score_real.py: per class (defective first), shuffle with one Random(7), k % 5
rng = random.Random(7)
fold = {}
for cls in (True, False):
    members = [i for i in ids if defect[i] == cls]
    rng.shuffle(members)
    for k, i in enumerate(members):
        fold[i] = k % 5


def vote_of(seat, i):
    v = recs[seat][i]["votes"][0]
    assert len(recs[seat][i]["votes"]) == 1
    return v["vote"], v.get("reasoning") or ""


# Claude: a text agent (claude_cli), so rates (or omega). Jev: decision agent, Platt on usable p.
res = {}
fits = {}
jev_no_p = [i for i in ids if readout(vote_of("jev", i)[1]) is None]
contra = [i for i in ids if (lambda p, v: p is not None and (p - 0.5) * v > 0)(readout(vote_of("jev", i)[1]), vote_of("jev", i)[0])]
for k in range(5):
    train = [i for i in ids if fold[i] != k]
    y = {i: (-1 if defect[i] else 1) for i in train}
    # Claude rates (Laplace)
    clean = [vote_of("claude", i)[0] for i in train if y[i] == 1]
    dfct = [vote_of("claude", i)[0] for i in train if y[i] == -1]
    claude_cal = len(clean) >= MIN_RATES and len(dfct) >= MIN_RATES

    def rates_ev(votes_clean, votes_def, v):
        pc = (sum(1 for x in votes_clean if x == v) + 1) / (len(votes_clean) + 2)
        pd = (sum(1 for x in votes_def if x == v) + 1) / (len(votes_def) + 2)
        return math.log(pc / pd)

    # Jev Platt
    pairs = []
    for i in train:
        p = readout(vote_of("jev", i)[1])
        if p is not None:
            pairs.append((math.log((1 - p) / p), y[i]))
    n_c = sum(1 for _, yy in pairs if yy == 1)
    n_d = sum(1 for _, yy in pairs if yy == -1)
    a = b = None
    if n_c >= MIN_PLATT and n_d >= MIN_PLATT:
        a, b, iters = platt([r for r, _ in pairs], [yy for _, yy in pairs])
        if iters is None:
            a = b = None
    pi = (n_c + 1) / (len(pairs) + 2)
    fits[k] = {"a": a, "b": b, "pi": pi, "n": len(pairs), "claude_clean_approve": sum(1 for x in clean if x == 1),
               "n_clean": len(clean), "claude_def_approve": sum(1 for x in dfct if x == 1), "n_def": len(dfct)}
    jev_clean = [vote_of("jev", i)[0] for i in train if y[i] == 1]
    jev_def = [vote_of("jev", i)[0] for i in train if y[i] == -1]

    for i in (i for i in ids if fold[i] == k):
        dom = by_id[i]["domain"]
        tau = logit((1 + THETA[dom]) / 2)
        omega = 0.5
        # seat 1: CLAUDE (both seats at omega 0.5, stable order claude, jev)
        vc, _ = vote_of("claude", i)
        ec = rates_ev(clean, dfct, vc) if claude_cal else omega * (0.981 if vc == 1 else -1.253)
        means = {"claude": ec}
        lam = ec
        decision = conf = None
        asked = ["claude"]
        if lam >= A:
            decision, conf = "APPROVE", "HIGH"
        elif lam <= B:
            decision, conf = "REJECT", "HIGH"
        if decision is None:
            vj, txt = vote_of("jev", i)
            p = readout(txt)
            if p is not None and (p - 0.5) * vj > 0:
                p = None
            if p is not None:
                r = math.log((1 - p) / p)
                if a is not None:
                    ej, tag = a + b * r - logit(pi), "platt"
                else:
                    ej, tag = max(omega * math.log(0.2 / 0.7), min(omega * math.log(0.8 / 0.3), r)), "capped"
            else:
                ej, tag = rates_ev(jev_clean, jev_def, vj), "rates"
            means["jev"] = ej
            lam = ec + ej
            asked.append("jev")
            disagree = any(m1 >= LN2 for m1 in means.values()) and any(m2 <= -LN2 for m2 in means.values())
            if not disagree and lam >= A:
                decision, conf = "APPROVE", "HIGH"
            elif not disagree and lam <= B:
                decision, conf = "REJECT", "HIGH"
            else:
                decision = "APPROVE" if lam >= tau else "REJECT"
                conf = "LOW" if (abs(lam - tau) < LN2 or disagree) else "MEDIUM"
        res[i] = {"fold": k, "decision": decision, "confidence": conf, "lambda": lam, "e_claude": ec,
                  "e_jev": means.get("jev"), "asked": asked, "tau": tau}

rep = json.loads((HERE / "replay_w2.json").read_text(encoding="utf-8"))
print("fold sizes (defective, clean):", [(sum(1 for i in ids if fold[i] == k and defect[i]),
                                         sum(1 for i in ids if fold[i] == k and not defect[i])) for k in range(5)])
print("fold assignment identical to replay:", all(rep["fold"][i] == fold[i] for i in ids))
print("leakage entries in replay (sessions/artifacts of test items in their training log):", len(rep["leakage"]))
print(f"jev answers without a usable p: {len(jev_no_p)}; with p contradicting the vote: {len(contra)}")
for k in range(5):
    f = fits[k]
    print(f"  fold {k}: Platt a={f['a']:+.4f} b={f['b']:.4f} n={f['n']} pi={f['pi']:.4f}; "
          f"Claude approves {f['claude_clean_approve']}/{f['n_clean']} clean, {f['claude_def_approve']}/{f['n_def']} defective")
dd = [i for i in ids if res[i]["decision"] != rep["items"][i]["decision"]]
dc = [i for i in ids if res[i]["confidence"] != rep["items"][i]["confidence"]]
dl = max(abs(res[i]["lambda"] - rep["items"][i]["lambda"]) for i in ids)
de = max(max(abs(res[i]["e_claude"] - rep["items"][i]["votes"][0]["evidence"]),
             abs((res[i]["e_jev"] or 0) - (rep["items"][i]["votes"][1]["evidence"] if len(rep["items"][i]["votes"]) > 1 else 0)))
         for i in ids)
da = [i for i in ids if res[i]["asked"] != rep["items"][i]["asked"]]
tags = sorted({tuple(v["calibration"] for v in rep["items"][i]["votes"]) for i in ids})
print(f"decision differences vs replay: {len(dd)} {dd}")
print(f"confidence differences: {len(dc)}; max |Lambda diff| {dl:.2e} (replay rounds evidence to 4 dp); "
      f"max |evidence diff| {de:.2e}; asked-order differences {len(da)}; replay calibration tags {tags}")
P = [i for i in ids if defect[i]]
N = [i for i in ids if not defect[i]]
print(f"independent W2: recall {sum(res[i]['decision'] == 'REJECT' for i in P)}/{len(P)}, "
      f"false alarms {sum(res[i]['decision'] == 'REJECT' for i in N)}/{len(N)}")
from collections import Counter  # noqa: E402
print("confidence:", dict(Counter(res[i]["confidence"] for i in ids)),
      "| early stop by Claude alone:", sum(len(res[i]["asked"]) == 1 for i in ids))
# how close are decisions to tau
near = sorted(ids, key=lambda i: abs(res[i]["lambda"] - res[i]["tau"]))[:5]
print("closest to tau:", [(i, round(res[i]["lambda"] - res[i]["tau"], 4)) for i in near])
# decision = sign rule only? (W2 vs claude, vs jev)
agree_c = sum((res[i]["decision"] == "REJECT") == (recs["claude"][i]["decision"] == "REJECT") for i in ids)
agree_j = sum((res[i]["decision"] == "REJECT") == (recs["jev"][i]["decision"] == "REJECT") for i in ids)
print(f"W2 agrees with Claude alone on {agree_c}/132 items, with Jev alone on {agree_j}/132")
(HERE / "w2_independent.json").write_text(json.dumps({"fold": fold, "items": res, "fits": fits}, indent=1),
                                          encoding="utf-8")
