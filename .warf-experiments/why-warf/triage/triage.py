"""Triage: does WaRF's panel tell you WHICH verdicts to trust better than a single agent's own
confidence does?

WaRF's documents place the panel's value in its confidence, not its accuracy (the talk:
"Ensemble value is in High-confidence early stops"; warf/policy.md: act on REJECT [HIGH], send
MEDIUM and LOW to a human). Each system below gives every review a decision d and a confidence c.
Reviews are ranked by c, most confident first; tied confidences are averaged over all their
orders (exact expectation, never file order). Reported per system:
  - selective accuracy: accuracy among the most confident 10, 25, 50, 75 and 100 % of reviews
    (a fractional review count includes the boundary review fractionally);
  - AURC: mean selective error over the coverages k = 1..n, with a 95 % bootstrap interval
    (resampling reviews within each label, 2,000 draws);
  - "random": the AURC of the same verdicts ranked at random (= the overall error rate) and a
    permutation p for "c ranks right verdicts above wrong ones better than chance";
  - "oracle": the AURC if c were 1 for every right verdict and 0 for every wrong one (the floor);
  - trust AUROC: the chance that a right verdict carries a higher c than a wrong one (ties
    half), a trust measure that does not depend on the accuracy itself.
Paired differences use the same bootstrap draws for both systems. Controls: shuffled labels must
give a flat curve, the oracle confidence a steep one, and the tie handling is checked against
random tie orders.

Stored data only: no model or service is asked. Reads
  ../../laya-five/selection.jsonl, ../../laya-five/sessions.jsonl
  ../../jev-five/sessions_one.jsonl, sessions_five.jsonl, sessions_standard.jsonl
  ../../jev-five/verify/refute/rerun_A.jsonl, rerun_B.jsonl
  ../../sessions.jsonl            the 12-file persona experiment (via tools/compare_pools.py)
  ../../../.warf/sessions.jsonl   WaRF's labelled corpus (read only)
Writes triage.log and triage.json next to this file, nothing else.
Pure Python: numpy's BLAS crashes in gs\\cf\\python.exe.

    set PYTHONIOENCODING=utf-8
    python -B .warf-experiments/why-warf/triage/triage.py
"""
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent                       # .warf-experiments
ROOT = EXP.parent                              # the WaRF clone
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from warf.engine import A, B, SPRTState, sprt_update, synthesis   # noqa: E402
from _groundtruth import corpus_truth, truth_for                   # noqa: E402
from compare_pools import agreement, load_pool, uniform_replay     # noqa: E402

NB, NP, NS = 2000, 2000, 1000                  # bootstrap draws, permutations, label shuffles
COV = (0.10, 0.25, 0.50, 0.75, 1.00)
BAND = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
NAN = float("nan")
LOG, RES = [], {}


def say(s=""):
    LOG.append(s)
    print(s)


def jl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


# --------------------------------------------------------------------------------------------
# Selective accuracy
# --------------------------------------------------------------------------------------------
def tie_blocks(c):
    """Review indices, most confident first, grouped into blocks of equal confidence."""
    order = sorted(range(len(c)), key=lambda i: c[i], reverse=True)
    blocks, i = [], 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and c[order[j + 1]] == c[order[i]]:
            j += 1
        blocks.append(order[i:j + 1])
        i = j + 1
    return blocks


def cum_correct(c, ok):
    """C[k] = expected number of right verdicts among the k most confident, k = 0..n,
    averaged over every order of tied confidences (exact)."""
    C = [0.0]
    for blk in tie_blocks(c):
        rate = sum(ok[i] for i in blk) / len(blk)
        for _ in blk:
            C.append(C[-1] + rate)
    return C


def acc_k(C, k):
    """Accuracy among the k most confident reviews; fractional k includes the next review
    fractionally (C is linear within a tie block, so this is exact for ties too)."""
    n = len(C) - 1
    if k <= 0:
        return NAN
    if k >= n:
        return C[n] / n
    lo = int(math.floor(k + 1e-9))
    frac = max(0.0, k - lo)
    return (C[lo] + frac * (C[lo + 1] - C[lo])) / k


def aurc(C):
    n = len(C) - 1
    return sum(1 - C[k] / k for k in range(1, n + 1)) / n


def trust_auc(c, ok):
    """P(c of a right verdict > c of a wrong verdict), ties half."""
    n = len(c)
    n1 = sum(ok)
    n0 = n - n1
    if n1 == 0 or n0 == 0:
        return NAN
    order = sorted(range(n), key=lambda i: c[i])
    rank = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and c[order[j + 1]] == c[order[i]]:
            j += 1
        for t in range(i, j + 1):
            rank[order[t]] = (i + j) / 2 + 1
        i = j + 1
    return (sum(rank[i] for i in range(n) if ok[i]) - n1 * (n1 + 1) / 2) / (n1 * n0)


class System:
    def __init__(self, name, d, c, y, high=None, group=""):
        assert len(d) == len(c) == len(y)
        assert all(v in ("APPROVE", "REJECT") for v in d)
        self.name, self.d, self.c, self.y, self.group = name, d, c, y, group
        self.ok = [a == b for a, b in zip(d, y)]
        self.high = high


def stats(s, idx, kmap=None):
    c = [s.c[i] for i in idx]
    ok = [s.ok[i] for i in idx]
    C = cum_correct(c, ok)
    n = len(idx)
    return {"aurc": aurc(C), "acc": [acc_k(C, q * n) for q in COV], "tauc": trust_auc(c, ok),
            "k": {name: acc_k(C, k) if k > 0 else NAN for name, k in (kmap or {}).items()}}


def strat_draws(y, nb=NB, seed=5):
    """Bootstrap resamples within each label, as ../../jev-five/why_five.py does."""
    P = [i for i, t in enumerate(y) if t == "REJECT"]
    N = [i for i, t in enumerate(y) if t != "REJECT"]
    rng = random.Random(seed)
    return [[rng.choice(P) for _ in P] + [rng.choice(N) for _ in N] for _ in range(nb)]


def ci(vals):
    v = sorted(x for x in vals if x == x)
    m = len(v)
    return (v[int(0.025 * m)], v[int(0.975 * m) - 1], m) if m else (NAN, NAN, 0)


def boot_p(vals):
    """Two-sided bootstrap p for 'difference = 0': share of draws on the far side of 0, doubled;
    draws of exactly 0 (common when both systems pick the same reviews) count half (mid-p)."""
    v = [x for x in vals if x == x]
    if not v:
        return NAN
    lt = sum(x < -1e-12 for x in v) / len(v)
    gt = sum(x > 1e-12 for x in v) / len(v)
    eq = 1 - lt - gt
    return min(1.0, 2 * min(lt + eq / 2, gt + eq / 2))


def perm_p(s, perms):
    """One-sided p that c ranks right verdicts above wrong ones better than a random ranking:
    share of random rankings with an AURC at most the observed one."""
    obs = aurc(cum_correct(s.c, s.ok))
    hits = sum(aurc(cum_correct([s.c[i] for i in p], s.ok)) <= obs + 1e-12 for p in perms)
    return (1 + hits) / (1 + len(perms))


def f3(x):
    return "  n/a" if x != x else f"{x:.3f}"


def f2(x):
    return " n/a" if x != x else f"{x:.2f}"


# --------------------------------------------------------------------------------------------
# Exact tests
# --------------------------------------------------------------------------------------------
def fisher(a, b, c, d):
    """Two-sided Fisher exact p for the table [[a, b], [c, d]]."""
    r1, r2, c1 = a + b, c + d, a + c
    n = r1 + r2

    def p(x):
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)

    p0 = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, c1 - r2), min(r1, c1) + 1) if p(x) <= p0 * (1 + 1e-9)))


def hyper_ge(x, N, K, n):
    """P(at least x right among n verdicts drawn at random from N, of which K are right)."""
    return sum(math.comb(K, i) * math.comb(N - K, n - i) for i in range(max(x, 0), min(K, n) + 1)) / math.comb(N, n)


def cp(x, n, a=0.05):
    """Clopper-Pearson interval for x of n."""
    def tail_ge(p):
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x, n + 1))

    def tail_le(p):
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, x + 1))

    def bisect(f, target, increasing):
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if (f(mid) < target) == increasing:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lo = 0.0 if x == 0 else bisect(tail_ge, a / 2, True)
    hi = 1.0 if x == n else bisect(tail_le, a / 2, False)
    return lo, hi


# --------------------------------------------------------------------------------------------
# WaRF's verdict, recomputed with warf.engine
# --------------------------------------------------------------------------------------------
def warf_round(votes, domain):
    """votes: [(vote, omega)] in the order cast. Same rule as orchestrator.run_review: the first
    boundary crossing is the verdict (HIGH); without one, synthesis() over all votes. Returns
    (decision, band, Lambda after all votes, normalised score or None)."""
    st, first = SPRTState(), None
    for v, w in votes:
        st, crossed = sprt_update(st, v, w)
        if crossed is not None and first is None:
            first = crossed
    if first is not None:
        return first.value, "HIGH", st.lambda_, None
    dec, conf, norm = synthesis([v for v, _ in votes], [w for _, w in votes], domain)
    return dec.value, conf.value, st.lambda_, norm


def panel(rs, key):
    """Round-1 and final verdicts of a five-persona panel (early stopping off, debate on),
    recomputed from the stored votes and checked against every logged field."""
    out, bad = [], []
    for r in rs:
        r1 = [(v["vote"], v["omega"]) for v in r["votes"]]
        for v in r["votes"]:                    # WaRF's votes = the model's argmax per agent
            if (v["vote"] == -1) != (r[key]["round1"][v["agent"]]["choice"] == "REJECT"):
                bad.append((r[key]["id"], "round1 vote", v["agent"]))
        d1, b1, l1, n1 = warf_round(r1, r["domain"])
        if abs(l1 - r["sprt_lambda"]) > 6e-4:
            bad.append((r[key]["id"], "lambda1", l1, r["sprt_lambda"]))
        if b1 == "HIGH":                        # a Round-1 stop: no debate, logged = Round 1
            if r.get("debate") or (r["decision"], r["confidence"]) != (d1, b1):
                bad.append((r[key]["id"], "R1 HIGH", d1, r["decision"], r["confidence"]))
            df, bf, lf = d1, b1, l1
        else:
            if abs(n1 - r["normalised_score"]) > 6e-4:
                bad.append((r[key]["id"], "norm1", n1, r["normalised_score"]))
            db = r.get("debate")
            if not db:
                bad.append((r[key]["id"], "no debate"))
                df, bf, lf = d1, b1, l1
            else:
                r2 = [(v["vote"], v["omega"]) for v in db["votes"]]
                for v in db["votes"]:
                    if (v["vote"] == -1) != (r[key]["round2"][v["agent"]]["choice"] == "REJECT"):
                        bad.append((r[key]["id"], "round2 vote", v["agent"]))
                df, bf, lf, n2 = warf_round(r2, r["domain"])
                if abs(lf - db["sprt_lambda"]) > 6e-4:
                    bad.append((r[key]["id"], "lambda2", lf, db["sprt_lambda"]))
                if (r["decision"], r["confidence"]) != (df, bf):
                    bad.append((r[key]["id"], "final", df, bf, r["decision"], r["confidence"]))
        p1 = [r[key]["round1"][a]["p_reject"] for a in AGENTS]
        nrej = sum(v == -1 for v, _ in r1)
        out.append({"id": r[key]["id"], "d1": d1, "b1": b1, "l1": l1, "df": df, "bf": bf, "lf": lf,
                    "margin": abs(nrej - (len(r1) - nrej)), "meanp": sum(p1) / len(p1), "nrej": nrej})
    return out, bad


# ============================================================================================
# 1. The 100 gismo6 commits
# ============================================================================================
sel = jl(EXP / "laya-five" / "selection.jsonl")
ids = [s["id"] for s in sel]
y = [s["label"] for s in sel]
J5 = EXP / "jev-five"
one = {r["jev"]["id"]: r for r in jl(J5 / "sessions_one.jsonl")}
rA = {r["jev"]["id"]: r for r in jl(J5 / "verify" / "refute" / "rerun_A.jsonl")}
rB = {r["jev"]["id"]: r for r in jl(J5 / "verify" / "refute" / "rerun_B.jsonl")}
five_raw = {r["jev"]["id"]: r for r in jl(J5 / "sessions_five.jsonl")}
std = {r["jev"]["id"]: r for r in jl(J5 / "sessions_standard.jsonl")}
lfive_raw = {r["five"]["id"]: r for r in jl(EXP / "laya-five" / "sessions.jsonl")}
for name, src, key in (("sessions_one", one, "jev"), ("rerun_A", rA, "jev"), ("rerun_B", rB, "jev"),
                       ("sessions_five", five_raw, "jev"), ("sessions_standard", std, "jev"),
                       ("laya five", lfive_raw, "five")):
    assert set(src) == set(ids), name
    assert all(src[i][key]["label"] == s["label"] for i, s in zip(ids, sel)), name

say("=" * 112)
say("Triage: WaRF's confidence against a single agent's own confidence (stored data only)")
say("=" * 112)
say(f"\n1. The 100 gismo6 commits: {sum(t == 'REJECT' for t in y)} later fixed (REJECT), "
    f"{sum(t == 'APPROVE' for t in y)} never fixed (APPROVE); domains "
    + ", ".join(f"{d} {sum(s['domain'] == d for s in sel)}" for d in sorted({s['domain'] for s in sel})))

# --- data checks: WaRF's verdicts recomputed --------------------------------------------------
fiveP, bad5 = panel([five_raw[i] for i in ids], "jev")
layaP, badL = panel([lfive_raw[i] for i in ids], "five")
say("\n  Checks: WaRF's verdicts recomputed with warf.engine from the stored votes and omegas")
say(f"    five Jev:  {len(bad5)} mismatches with the logged votes, Lambdas, normalised scores, decisions, "
    f"confidences; logged top-level decision/confidence = the final verdict after the debate "
    f"({sum(r['b1'] != 'HIGH' for r in fiveP)} debated), top-level sprt_lambda = Round 1's Lambda after all five votes")
say(f"    five Laya: {len(badL)} mismatches ({sum(r['b1'] != 'HIGH' for r in layaP)} debated)")
for b in (bad5 + badL)[:10]:
    say(f"      {b}")
std_bad = []
for i in ids:
    r = std[i]
    d, b, lam, _ = warf_round([(v["vote"], v["omega"]) for v in r["votes"]], r["domain"])
    if (d, b) != (r["decision"], r["confidence"]) or abs(lam - r["sprt_lambda"]) > 6e-4:
        std_bad.append((i, d, b, lam, r["decision"], r["confidence"], r["sprt_lambda"]))
    if b == "HIGH" and len(r["votes"]) == 5 and abs(lam) < abs(B):
        std_bad.append((i, "HIGH without a stop"))
say(f"    WaRF defaults on Jev (early stopping on): {len(std_bad)} mismatches; agents asked "
    + ", ".join(f"{k}: {sum(len(std[i]['votes']) == k for i in ids)}" for k in sorted({len(std[i]['votes']) for i in ids})))
for b in std_bad[:5]:
    say(f"      {b}")
mis = {}
for name, src in (("sessions_one", one), ("rerun_A", rA), ("rerun_B", rB)):
    mis[name] = [i for i in ids if (src[i]["jev"]["round1"]["JEV"]["p_reject"] > 0.5)
                 != (src[i]["jev"]["round1"]["JEV"]["choice"] == "REJECT")]
say("    single Jev, d = (p_reject > 0.5) against Jev's own argmax: "
    + "; ".join(f"{k} {len(v)} differ" + (f" ({', '.join(v)}: logged p 0.50)" if v else "") for k, v in mis.items()))
RES["checks"] = {"five_jev_mismatch": len(bad5), "five_laya_mismatch": len(badL), "standard_mismatch": len(std_bad),
                 "single_p_vs_argmax": {k: v for k, v in mis.items()}}


def single(name, ps, group):
    d = ["REJECT" if p > 0.5 else "APPROVE" for p in ps]
    return System(name, d, [round(abs(p - 0.5), 9) for p in ps], y, group=group)


def pj(src, i):
    return src[i]["jev"]["round1"]["JEV"]["p_reject"]


S = []
S.append(single("Jev single, |p-0.5|", [pj(one, i) for i in ids], "jev"))
S.append(single("Jev single rerun A, |p-0.5|", [pj(rA, i) for i in ids], "jev"))
S.append(single("Jev single rerun B, |p-0.5|", [pj(rB, i) for i in ids], "jev"))


def panel_systems(P, tag, group):
    hi1 = [r["b1"] == "HIGH" for r in P]
    hif = [r["bf"] == "HIGH" for r in P]
    d1 = [r["d1"] for r in P]
    out = [
        System(f"{tag} R1, WaRF band", d1, [(BAND[r["b1"]], round(abs(r["l1"]), 4)) for r in P], y, hi1, group),
        System(f"{tag} R1, |Lambda|", d1, [round(abs(r["l1"]), 4) for r in P], y, hi1, group),
        System(f"{tag} R1, vote margin", d1, [r["margin"] for r in P], y, hi1, group),
        System(f"{tag} R1, |mean p-0.5|", d1, [round(abs(r["meanp"] - 0.5), 9) for r in P], y, hi1, group),
        System(f"{tag} final, WaRF band", [r["df"] for r in P], [(BAND[r["bf"]], round(abs(r["lf"]), 4)) for r in P],
               y, hif, group),
        System(f"{tag} mean-p verdict (extra)", ["REJECT" if r["meanp"] > 0.5 else "APPROVE" for r in P],
               [round(abs(r["meanp"] - 0.5), 9) for r in P], y, hi1, group),
    ]
    return out


S += panel_systems(fiveP, "Jev five", "jev")
S.append(System("Jev WaRF defaults, WaRF band", [std[i]["decision"] for i in ids],
                [(BAND[std[i]["confidence"]], round(abs(std[i]["sprt_lambda"]), 4)) for i in ids], y,
                [std[i]["confidence"] == "HIGH" for i in ids], "jev"))
S.append(single("Laya single, |p-0.5|", [s["p_single_laya"] for s in sel], "laya"))
S += panel_systems(layaP, "Laya five", "laya")


def seat(name, recs, group):
    """One persona seat of a panel run on its own: d = its own vote (Jev's/Laya's argmax), c = |p - 0.5|.
    Same prompt and run as the panel, so the comparison isolates WaRF's aggregation."""
    return System(name, [r["choice"] for r in recs], [round(abs(r["p_reject"] - 0.5), 9) for r in recs], y, group=group)


# With uniform weights the first agent asked is SKEPTIC (profile order) in every run.
assert all(five_raw[i]["votes"][0]["agent"] == "SKEPTIC" and std[i]["votes"][0]["agent"] == "SKEPTIC"
           and lfive_raw[i]["votes"][0]["agent"] == "SKEPTIC" for i in ids)
for a in AGENTS:
    S.append(seat(f"Jev seat {a} (five run)", [five_raw[i]["jev"]["round1"][a] for i in ids], "seat"))
S.append(seat("Jev seat SKEPTIC (defaults run)", [std[i]["jev"]["round1"]["SKEPTIC"] for i in ids], "seat"))
for a in AGENTS:
    S.append(seat(f"Laya seat {a} (five run)", [lfive_raw[i]["five"]["round1"][a] for i in ids], "seat"))
S.append(single("Claude (blinded), |p-0.5|", [s["p_claude"] for s in sel], "ref"))
# 'Block the k most suspicious': every review REJECT, ranked by p(REJECT) - its selective
# accuracy at k is the share of later-fixed changes among the k highest p.
S.append(System("Jev single, block top-k by p", ["REJECT"] * len(ids), [pj(one, i) for i in ids], y, group="block"))
S.append(System("Laya single, block top-k by p", ["REJECT"] * len(ids), [s["p_single_laya"] for s in sel], y, group="block"))
S.append(System("Claude, block top-k by p", ["REJECT"] * len(ids), [s["p_claude"] for s in sel], y, group="block"))
BY = {s.name: s for s in S}

HIGHSETS = {"Jev five R1": BY["Jev five R1, WaRF band"].high, "Jev five final": BY["Jev five final, WaRF band"].high,
            "Jev WaRF defaults": BY["Jev WaRF defaults, WaRF band"].high, "Laya five R1": BY["Laya five R1, WaRF band"].high,
            "Laya five final": BY["Laya five final, WaRF band"].high}
for name, hs in HIGHSETS.items():
    sysname = {"Jev five R1": "Jev five R1, WaRF band", "Jev five final": "Jev five final, WaRF band",
               "Jev WaRF defaults": "Jev WaRF defaults, WaRF band", "Laya five R1": "Laya five R1, WaRF band",
               "Laya five final": "Laya five final, WaRF band"}[name]
    assert all(BY[sysname].d[i] == "REJECT" for i in range(len(ids)) if hs[i]), name   # HIGH APPROVE unreachable

# --- machinery checks ------------------------------------------------------------------------
say("\n  Checks of the selective-accuracy code")
s0 = BY["Jev five R1, WaRF band"]
flat = cum_correct([0] * len(ids), s0.ok)
acc_all = sum(s0.ok) / len(ids)
assert all(abs(acc_k(flat, q * len(ids)) - acc_all) < 1e-12 for q in COV)
assert abs(aurc(flat) - (1 - acc_all)) < 1e-12
orc = cum_correct([int(o) for o in s0.ok], s0.ok)
m = sum(s0.ok)
orc_exact = sum(0 if k <= m else (k - m) / k for k in range(1, len(ids) + 1)) / len(ids)
assert abs(aurc(orc) - orc_exact) < 1e-12
rng = random.Random(11)
mc = [0.0] * len(COV)
mca = 0.0
R = 4000
for _ in range(R):           # random tie orders: sort by (c, random key)
    key = [(s0.c[i], rng.random()) for i in range(len(ids))]
    order = sorted(range(len(ids)), key=lambda i: key[i], reverse=True)
    Cm = [0.0]
    for i in order:
        Cm.append(Cm[-1] + s0.ok[i])
    for t, q in enumerate(COV):
        mc[t] += acc_k(Cm, q * len(ids)) / R
    mca += aurc(Cm) / R
ex = cum_correct(s0.c, s0.ok)
dev = max(abs(mc[t] - acc_k(ex, q * len(ids))) for t, q in enumerate(COV))
say(f"    all-tied c gives a flat curve at the overall accuracy and AURC = error rate: ok; oracle AURC "
    f"matches its closed form: ok; tie averaging vs {R} random tie orders (Jev five, WaRF band): "
    f"max |difference| {dev:.4f} in accuracy, {abs(mca - aurc(ex)):.4f} in AURC")
assert dev < 0.01 and abs(mca - aurc(ex)) < 0.005

# --- bootstrap, permutations, shuffles ---------------------------------------------------------
draws = strat_draws(y)
kd = [{name: sum(hs[i] for i in idx) for name, hs in HIGHSETS.items()} for idx in draws]
kobs = {name: sum(hs) for name, hs in HIGHSETS.items()}
full = list(range(len(ids)))
OBS, BOOT = {}, {}
for s in S:
    OBS[s.name] = stats(s, full, kobs)
    BOOT[s.name] = [stats(s, idx, k) for idx, k in zip(draws, kd)]
prng = random.Random(7)
perms = []
for _ in range(NP):
    p = full[:]
    prng.shuffle(p)
    perms.append(p)
PERM = {s.name: perm_p(s, perms) for s in S if s.group != "block"}
srng = random.Random(9)
shuffles = []
for _ in range(NS):
    yy = y[:]
    srng.shuffle(yy)
    shuffles.append(yy)
SHUF, ORACLE = {}, {}
for s in S:
    accs = [0.0] * len(COV)
    au = []
    for yy in shuffles:
        ok = [a == b for a, b in zip(s.d, yy)]
        C = cum_correct(s.c, ok)
        for t, q in enumerate(COV):
            accs[t] += acc_k(C, q * len(ids)) / NS
        au.append(aurc(C))
    au.sort()
    SHUF[s.name] = {"acc": accs, "aurc": sum(au) / NS, "aurc_95": (au[int(0.025 * NS)], au[int(0.975 * NS) - 1])}
    C = cum_correct([int(o) for o in s.ok], s.ok)
    ORACLE[s.name] = {"acc": [acc_k(C, q * len(ids)) for q in COV], "aurc": aurc(C)}

say("\n  1a. Selective accuracy: accuracy among the most confident share of reviews (ties averaged)")
say(f"  {'system':<40}{'REJ':>4}{'HIGH':>5} |" + "".join(f"{int(q * 100):>6}%" for q in COV))
order_names = [s.name for s in S if s.group != "block"]
for name in order_names:
    s = BY[name]
    nh = sum(s.high) if s.high else 0
    say(f"  {name:<40}{s.d.count('REJECT'):>4}{nh if s.high else '':>5} |"
        + "".join(f"{OBS[name]['acc'][t]:>7.3f}" for t in range(len(COV))))
say("\n  95 % bootstrap intervals of the same (resampling commits within labels, 2,000 draws)")
for name in order_names:
    say(f"  {name:<40}" + "".join(f" [{ci([b['acc'][t] for b in BOOT[name]])[0]:.2f},{ci([b['acc'][t] for b in BOOT[name]])[1]:.2f}]"
                              for t in range(len(COV))))

say("\n  1b. AURC (mean selective error over all coverages; lower is better), against the same verdicts")
say("      ranked at random (= error rate; perm p: chance that a random ranking does as well) and the oracle floor;")
say("      trust AUROC: P(confidence of a right verdict > a wrong one)")
say(f"  {'system':<40}{'AURC [95% CI]':>24}{'random':>8}{'perm p':>8}{'oracle':>8}   {'trust AUROC [95% CI]':<24}")
RES["commits100"] = {}
for name in order_names:
    o = OBS[name]
    lo, hi, _ = ci([b["aurc"] for b in BOOT[name]])
    tlo, thi, _ = ci([b["tauc"] for b in BOOT[name]])
    err = 1 - sum(BY[name].ok) / len(ids)
    say(f"  {name:<40}{o['aurc']:>8.3f} [{lo:.3f}, {hi:.3f}]{err:>8.3f}{PERM[name]:>8.3f}{ORACLE[name]['aurc']:>8.3f}"
        f"   {o['tauc']:.3f} [{tlo:.3f}, {thi:.3f}]")
    RES["commits100"][name] = {
        "n_reject_verdicts": BY[name].d.count("REJECT"), "n_high": sum(BY[name].high) if BY[name].high else None,
        "acc_at": dict(zip([str(q) for q in COV], o["acc"])),
        "acc_at_ci": {str(q): ci([b["acc"][t] for b in BOOT[name]])[:2] for t, q in enumerate(COV)},
        "aurc": o["aurc"], "aurc_ci": [lo, hi], "aurc_random": err, "perm_p": PERM[name],
        "aurc_oracle": ORACLE[name]["aurc"], "trust_auroc": o["tauc"], "trust_auroc_ci": [tlo, thi]}

# --- bands of the panels -----------------------------------------------------------------------
say("\n  1c. The panels' bands: verdicts, later fixed, right")
RES["bands100"] = {}
for name in ("Jev five R1, WaRF band", "Jev five final, WaRF band", "Jev WaRF defaults, WaRF band",
             "Laya five R1, WaRF band", "Laya five final, WaRF band"):
    s = BY[name]
    cells = {}
    for i in range(len(ids)):
        band = {2: "HIGH", 1: "MEDIUM", 0: "LOW"}[s.c[i][0]]
        cells.setdefault((s.d[i], band), []).append(s.ok[i])
    say(f"  {name:<34}" + "; ".join(f"{d} {b} {len(v)} ({sum(v)} right)" for (d, b), v in sorted(cells.items())))
    RES["bands100"][name] = {f"{d} {b}": [len(v), sum(v)] for (d, b), v in cells.items()}
rej_votes = {}
for r, t in zip(fiveP, y):
    rej_votes.setdefault(r["nrej"], []).append(t == "REJECT")
say("  Jev five, Round 1, by REJECT votes: " + "; ".join(
    f"{k} of 5: {len(v)} ({sum(v)} later fixed)" for k, v in sorted(rej_votes.items())))

# --- paired differences ------------------------------------------------------------------------
say("\n  1d. Paired differences on the same commits, panel minus the single agent of the same model")
say("      (95 % bootstrap interval, the same 2,000 draws for both; p: two-sided bootstrap p). A negative")
say("      AURC difference and a positive accuracy difference favour the panel. 'acc @ HIGH share': accuracy")
say("      among the k most confident, k = the panel's number of HIGH verdicts in that draw (observed k given).")
PAIRS = [
    ("Jev five R1, WaRF band", "Jev single, |p-0.5|", "Jev five R1"),
    ("Jev five R1, |Lambda|", "Jev single, |p-0.5|", "Jev five R1"),
    ("Jev five R1, vote margin", "Jev single, |p-0.5|", "Jev five R1"),
    ("Jev five R1, |mean p-0.5|", "Jev single, |p-0.5|", "Jev five R1"),
    ("Jev five final, WaRF band", "Jev single, |p-0.5|", "Jev five final"),
    ("Jev WaRF defaults, WaRF band", "Jev single, |p-0.5|", "Jev WaRF defaults"),
    ("Jev five mean-p verdict (extra)", "Jev single, |p-0.5|", "Jev five R1"),
    ("Jev five R1, WaRF band", "Jev single rerun A, |p-0.5|", "Jev five R1"),
    ("Jev five R1, WaRF band", "Jev single rerun B, |p-0.5|", "Jev five R1"),
    ("Jev WaRF defaults, WaRF band", "Jev single rerun A, |p-0.5|", "Jev WaRF defaults"),
    ("Jev WaRF defaults, WaRF band", "Jev single rerun B, |p-0.5|", "Jev WaRF defaults"),
    ("Laya five R1, WaRF band", "Laya single, |p-0.5|", "Laya five R1"),
    ("Laya five R1, |Lambda|", "Laya single, |p-0.5|", "Laya five R1"),
    ("Laya five R1, vote margin", "Laya single, |p-0.5|", "Laya five R1"),
    ("Laya five R1, |mean p-0.5|", "Laya single, |p-0.5|", "Laya five R1"),
    ("Laya five final, WaRF band", "Laya single, |p-0.5|", "Laya five final"),
    ("Laya five mean-p verdict (extra)", "Laya single, |p-0.5|", "Laya five R1"),
    ("Jev five R1, WaRF band", "Jev seat SKEPTIC (five run)", "Jev five R1"),
    ("Jev five R1, WaRF band", "Jev seat ADVOCATE (five run)", "Jev five R1"),
    ("Jev five R1, WaRF band", "Jev seat AUDITOR (five run)", "Jev five R1"),
    ("Jev five R1, WaRF band", "Jev seat TEST-FOCUSED (five run)", "Jev five R1"),
    ("Jev five R1, WaRF band", "Jev seat BOUNDARY (five run)", "Jev five R1"),
    ("Jev WaRF defaults, WaRF band", "Jev seat SKEPTIC (defaults run)", "Jev WaRF defaults"),
    ("Laya five R1, WaRF band", "Laya seat SKEPTIC (five run)", "Laya five R1"),
    ("Laya five R1, WaRF band", "Laya seat ADVOCATE (five run)", "Laya five R1"),
    ("Laya five R1, WaRF band", "Laya seat AUDITOR (five run)", "Laya five R1"),
    ("Laya five R1, WaRF band", "Laya seat TEST-FOCUSED (five run)", "Laya five R1"),
    ("Laya five R1, WaRF band", "Laya seat BOUNDARY (five run)", "Laya five R1"),
    ("Jev single rerun A, |p-0.5|", "Jev single, |p-0.5|", "Jev five R1"),
    ("Jev single rerun B, |p-0.5|", "Jev single, |p-0.5|", "Jev five R1"),
    ("Claude (blinded), |p-0.5|", "Jev single, |p-0.5|", "Jev five R1"),
    ("Claude (blinded), |p-0.5|", "Laya single, |p-0.5|", "Laya five R1"),
]
say(f"  {'panel (or system)':<34}{'minus':<28}{'d AURC [95% CI]':>27}{'p':>6}"
    f"{'k':>4}{'acc@HIGH share, panel/single':>30}{'d acc [95% CI]':>25}{'p':>6}")
RES["paired100"] = []
for a, b, hs in PAIRS:
    dA = [x["aurc"] - z["aurc"] for x, z in zip(BOOT[a], BOOT[b])]
    dK = [x["k"][hs] - z["k"][hs] for x, z in zip(BOOT[a], BOOT[b])]
    dT = [x["tauc"] - z["tauc"] for x, z in zip(BOOT[a], BOOT[b])]
    da = OBS[a]["aurc"] - OBS[b]["aurc"]
    dk = OBS[a]["k"][hs] - OBS[b]["k"][hs]
    dt = OBS[a]["tauc"] - OBS[b]["tauc"]
    la, ha, _ = ci(dA)
    lk, hk, nk = ci(dK)
    lt, ht, _ = ci(dT)
    say(f"  {a:<34}{b:<28}{da:>+9.3f} [{la:+.3f}, {ha:+.3f}]{boot_p(dA):>6.2f}{kobs[hs]:>4}"
        f"{OBS[a]['k'][hs]:>15.3f} / {OBS[b]['k'][hs]:.3f}{dk:>+9.3f} [{lk:+.3f}, {hk:+.3f}]{boot_p(dK):>6.2f}")
    RES["paired100"].append({"a": a, "b": b, "d_aurc": da, "d_aurc_ci": [la, ha], "p_aurc": boot_p(dA),
                             "k_high": kobs[hs], "acc_a_at_k": OBS[a]["k"][hs], "acc_b_at_k": OBS[b]["k"][hs],
                             "d_acc_at_k": dk, "d_acc_at_k_ci": [lk, hk], "p_acc_at_k": boot_p(dK), "draws_with_k": nk,
                             "d_trust_auroc": dt, "d_trust_auroc_ci": [lt, ht], "p_trust": boot_p(dT)})
say("\n  Accuracy removed. Trust AUROC difference, and the AURC gain over the same verdicts ranked at random")
say("  (AURC(random) - AURC = error rate - AURC; a larger gain means c sorts the system's own verdicts better):")
say(f"  {'panel (or system)':<34}{'minus':<34}{'d trust AUROC [95% CI]':>27}{'p':>6}{'gain a / b':>16}{'d gain [95% CI]':>26}{'p':>6}")
for e, (a, b, _) in zip(RES["paired100"], PAIRS):
    ga = (1 - sum(BY[a].ok) / len(ids)) - OBS[a]["aurc"]
    gb = (1 - sum(BY[b].ok) / len(ids)) - OBS[b]["aurc"]
    dg = []
    for idx, x, z in zip(draws, BOOT[a], BOOT[b]):
        ea = 1 - sum(BY[a].ok[i] for i in idx) / len(idx)
        eb = 1 - sum(BY[b].ok[i] for i in idx) / len(idx)
        dg.append((ea - x["aurc"]) - (eb - z["aurc"]))
    lg, hg, _ = ci(dg)
    e.update({"gain_a": ga, "gain_b": gb, "d_gain": ga - gb, "d_gain_ci": [lg, hg], "p_gain": boot_p(dg)})
    say(f"  {a:<34}{b:<34}{e['d_trust_auroc']:>+9.3f} [{e['d_trust_auroc_ci'][0]:+.3f}, {e['d_trust_auroc_ci'][1]:+.3f}]"
        f"{e['p_trust']:>6.2f}{ga:>8.3f} / {gb:.3f}{ga - gb:>+9.3f} [{lg:+.3f}, {hg:+.3f}]{boot_p(dg):>6.2f}")

say("\n  Seed check: the headline intervals with two other bootstrap seeds (2,000 draws each)")
for a, b, hs in PAIRS[:1] + [p for p in PAIRS if p[0] == "Jev WaRF defaults, WaRF band" and p[1] == "Jev single, |p-0.5|"] \
        + [p for p in PAIRS if p[0] == "Laya five R1, WaRF band" and p[1] == "Laya single, |p-0.5|"]:
    cells = []
    for seed in (6, 8):
        dr2 = strat_draws(y, seed=seed)
        dA, dK = [], []
        for idx in dr2:
            k = {hs: sum(HIGHSETS[hs][i] for i in idx)}
            x, z = stats(BY[a], idx, k), stats(BY[b], idx, k)
            dA.append(x["aurc"] - z["aurc"])
            dK.append(x["k"][hs] - z["k"][hs])
        la, ha, _ = ci(dA)
        lk, hk, _ = ci(dK)
        cells.append(f"seed {seed}: d AURC [{la:+.3f}, {ha:+.3f}], d acc @ HIGH share [{lk:+.3f}, {hk:+.3f}]")
    say(f"  {a} minus {b}: " + "; ".join(cells))

say("\n  1e. WaRF's gate (policy.md: block on REJECT [HIGH]) against blocking the same number of a single")
say("      agent's highest-p commits: share later fixed among the blocked")
GATES = [("Jev five R1, WaRF band", "Jev five R1"), ("Jev five final, WaRF band", "Jev five final"),
         ("Jev WaRF defaults, WaRF band", "Jev WaRF defaults"), ("Laya five R1, WaRF band", "Laya five R1")]
RES["gate100"] = []
for g, hs in GATES:
    k = kobs[hs]
    for b in ("Jev single, block top-k by p", "Laya single, block top-k by p", "Claude, block top-k by p"):
        if g.startswith("Laya") and b.startswith("Jev") or g.startswith("Jev") and b.startswith("Laya"):
            continue
        dK = [x["k"][hs] - z["k"][hs] for x, z in zip(BOOT[g], BOOT[b])]
        lk, hk, nk = ci(dK)
        say(f"  {g:<32} k = {k:>2}: blocked later fixed {OBS[g]['k'][hs]:.3f} ({round(OBS[g]['k'][hs] * k, 2)} of {k}); "
            f"{b:<30} {OBS[b]['k'][hs]:.3f}; difference {OBS[g]['k'][hs] - OBS[b]['k'][hs]:+.3f} [{lk:+.3f}, {hk:+.3f}] "
            f"p {boot_p(dK):.2f} ({nk} draws)")
        RES["gate100"].append({"panel": g, "single": b, "k": k, "panel_precision": OBS[g]["k"][hs],
                               "single_precision": OBS[b]["k"][hs], "ci": [lk, hk], "p": boot_p(dK)})

say("  Overlap: how many of a panel's HIGH commits are among the single agent's k highest p (k = number of HIGH;")
say("  ties at the k-th p included):")
RES["overlap100"] = []
for g, hs, ref, ps in (
        ("Jev five R1", "Jev five R1", "Jev single (sessions_one)", [pj(one, i) for i in ids]),
        ("Jev WaRF defaults", "Jev WaRF defaults", "Jev single (sessions_one)", [pj(one, i) for i in ids]),
        ("Jev WaRF defaults", "Jev WaRF defaults", "its own first agent, SKEPTIC",
         [std[i]["jev"]["round1"]["SKEPTIC"]["p_reject"] for i in ids]),
        ("Laya five R1", "Laya five R1", "Laya single (sweep)", [s["p_single_laya"] for s in sel])):
    H = [i for i in range(len(ids)) if HIGHSETS[hs][i]]
    cut = sorted(ps, reverse=True)[len(H) - 1]
    top = [i for i in range(len(ids)) if ps[i] >= cut]
    both = [i for i in H if ps[i] >= cut]
    say(f"    {g:<18} HIGH {len(H):>2}: {len(both)} among {ref}'s {len(top)} commits with p >= {cut}; "
        f"later fixed: HIGH {sum(y[i] == 'REJECT' for i in H)}, top-p {sum(y[i] == 'REJECT' for i in top)}")
    RES["overlap100"].append({"panel": g, "reference": ref, "n_high": len(H), "in_top": len(both), "n_top": len(top),
                              "cut": cut, "high_later_fixed": sum(y[i] == "REJECT" for i in H),
                              "top_later_fixed": sum(y[i] == "REJECT" for i in top)})

# --- controls ------------------------------------------------------------------------------------
say("\n  1f. Controls")
say(f"  Shuffled labels ({NS} shuffles of the 100 labels; d and c kept): mean selective accuracy and AURC")
say(f"  {'system':<40}" + "".join(f"{int(q * 100):>6}%" for q in COV) + f"{'AURC':>8}{'95 % of shuffles':>20}")
maxdev = 0.0
for name in order_names:
    sh = SHUF[name]
    maxdev = max(maxdev, max(abs(v - 0.5) for v in sh["acc"]))
    say(f"  {name:<40}" + "".join(f"{v:>7.3f}" for v in sh["acc"]) + f"{sh['aurc']:>8.3f}"
        f"   [{sh['aurc_95'][0]:.3f}, {sh['aurc_95'][1]:.3f}]")
say(f"  largest deviation of a mean shuffled accuracy from 0.5: {maxdev:.3f} (flat, as it must be)")
say("  Oracle confidence (c = 1 for right verdicts, 0 for wrong): selective accuracy and AURC")
for name in ("Jev single, |p-0.5|", "Jev five R1, WaRF band", "Jev WaRF defaults, WaRF band", "Laya single, |p-0.5|",
             "Laya five R1, WaRF band", "Claude (blinded), |p-0.5|"):
    say(f"  {name:<40}" + "".join(f"{v:>7.3f}" for v in ORACLE[name]["acc"]) + f"{ORACLE[name]['aurc']:>8.3f}")
RES["controls100"] = {"shuffled": SHUF, "oracle": ORACLE, "max_shuffled_dev": maxdev, "tie_check_max_dev": dev}

# ============================================================================================
# 2. WaRF's labelled corpus (Claude Haiku 4.5 text agents, no confidence of their own)
# ============================================================================================
say("\n" + "=" * 112)
say("2. WaRF's labelled corpus (.warf/sessions.jsonl, read only): 62 developer labels, Claude Haiku 4.5")
say("=" * 112)
truths = corpus_truth()
corpus = jl(ROOT / ".warf" / "sessions.jsonl")
lab = [s for s in corpus if s.get("oracle") and s["oracle"].get("x_star") is not None]
lbl = {1: "APPROVE", -1: "REJECT"}
cbad = []
for s in lab:
    d, b, lam, _ = warf_round([(v["vote"], v["omega"]) for v in s["votes"]], s["domain"])
    if s.get("debate"):
        d, b, lam2, _ = warf_round([(v["vote"], v["omega"]) for v in s["debate"]["votes"]], s["domain"])
        if abs(lam2 - s["debate"]["sprt_lambda"]) > 6e-4:
            cbad.append((s["session_id"][:8], "lambda2"))
    elif abs(lam - s["sprt_lambda"]) > 6e-4:
        cbad.append((s["session_id"][:8], "lambda", lam, s["sprt_lambda"]))
    if (d, b) != (s["decision"], s["confidence"]):
        cbad.append((s["session_id"][:8], d, b, s["decision"], s["confidence"]))
say(f"  {len(lab)} sessions; WaRF's verdicts recomputed from the stored votes and omegas: {len(cbad)} mismatches"
    f" ({sum(bool(s.get('debate')) for s in lab)} labelled sessions with a debate, scored on Round 2)")
for b in cbad[:5]:
    say(f"    {b}")
if cbad:
    say("    (a floating-point tie: with the logged 4-decimal omegas the weighted mean is +4e-17 instead of the logged"
        " -0.0, so the margin to theta = 0.2 falls just under 0.2; the logged band, MEDIUM, is used)")


def lam_final(s):
    return s["debate"]["sprt_lambda"] if s.get("debate") else s["sprt_lambda"]


def is_validation(s):
    return "validation" in s["artifact"].replace("\\", "/").split("/")


def corpus_block(truth_name, yy, sess=None):
    sess = lab if sess is None else sess
    assert len(sess) == len(yy)
    say(f"\n  Truth: {truth_name}: {len(sess)} sessions, {yy.count('APPROVE')} APPROVE, {yy.count('REJECT')} REJECT")
    sysl = [
        System("WaRF, band (then |Lambda|)", [s["decision"] for s in sess],
               [(BAND[s["confidence"]], round(abs(lam_final(s)), 4)) for s in sess], yy,
               [s["confidence"] == "HIGH" for s in sess]),
        System("WaRF, |Lambda|", [s["decision"] for s in sess], [round(abs(lam_final(s)), 4) for s in sess], yy,
               [s["confidence"] == "HIGH" for s in sess]),
        System("WaRF, |Round-1 Lambda|", [s["decision"] for s in sess], [round(abs(s["sprt_lambda"]), 4) for s in sess], yy,
               [s["confidence"] == "HIGH" for s in sess]),
        System("WaRF, random abstention", [s["decision"] for s in sess], [0] * len(sess), yy),
        System("first agent asked, random abstention", [lbl[s["votes"][0]["vote"]] for s in sess], [0] * len(sess), yy),
        System("first agent asked, ranked by WaRF band", [lbl[s["votes"][0]["vote"]] for s in sess],
               [(BAND[s["confidence"]], round(abs(lam_final(s)), 4)) for s in sess], yy),
    ]
    by = {s.name: s for s in sysl}
    n = len(sess)
    hs = {"HIGH": [s["confidence"] == "HIGH" for s in sess]}
    dr = strat_draws(yy, seed=13)
    kdr = [{"HIGH": sum(hs["HIGH"][i] for i in idx)} for idx in dr]
    obs = {s.name: stats(s, list(range(n)), {"HIGH": sum(hs["HIGH"])}) for s in sysl}
    bt = {s.name: [stats(s, idx, k) for idx, k in zip(dr, kdr)] for s in sysl}
    pr = random.Random(17)
    pm = []
    for _ in range(NP):
        p = list(range(n))
        pr.shuffle(p)
        pm.append(p)
    say(f"  {'system':<40}" + "".join(f"{int(q * 100):>6}%" for q in COV) + f"{'AURC [95% CI]':>24}{'perm p':>8}{'trust AUROC':>12}")
    out = {"systems": {}}
    for s in sysl:
        o = obs[s.name]
        lo, hi, _ = ci([b["aurc"] for b in bt[s.name]])
        pp = perm_p(s, pm) if len(set(s.c)) > 1 else NAN
        say(f"  {s.name:<40}" + "".join(f"{v:>7.3f}" for v in o["acc"]) + f"{o['aurc']:>8.3f} [{lo:.3f}, {hi:.3f}]"
            f"{f2(pp):>8}{f3(o['tauc']):>12}")
        out["systems"][s.name] = {"acc_at": o["acc"], "aurc": o["aurc"], "aurc_ci": [lo, hi], "perm_p": pp,
                                  "trust_auroc": o["tauc"], "right": sum(s.ok), "n": n}
    say(f"  (coverages are {', '.join(f'{q * n:g}' for q in COV)} sessions; a fractional session counts fractionally)")
    say("  Paired differences (bootstrap within labels, 2,000 draws):")
    out["paired"] = []
    for a, b in (("WaRF, band (then |Lambda|)", "first agent asked, random abstention"),
                 ("WaRF, |Lambda|", "first agent asked, random abstention"),
                 ("WaRF, band (then |Lambda|)", "WaRF, random abstention"),
                 ("first agent asked, ranked by WaRF band", "first agent asked, random abstention")):
        dA = [x["aurc"] - z["aurc"] for x, z in zip(bt[a], bt[b])]
        dK = [x["k"]["HIGH"] - z["k"]["HIGH"] for x, z in zip(bt[a], bt[b])]
        la, ha, _ = ci(dA)
        lk, hk, nk = ci(dK)
        da = obs[a]["aurc"] - obs[b]["aurc"]
        dk = obs[a]["k"]["HIGH"] - obs[b]["k"]["HIGH"]
        say(f"    {a:<40} minus {b:<38} AURC {da:+.3f} [{la:+.3f}, {ha:+.3f}] p {boot_p(dA):.2f}; "
            f"acc @ HIGH share ({sum(hs['HIGH'])}) {dk:+.3f} [{lk:+.3f}, {hk:+.3f}] p {boot_p(dK):.2f}")
        out["paired"].append({"a": a, "b": b, "d_aurc": da, "ci": [la, ha], "p": boot_p(dA),
                              "d_acc_high": dk, "ci_high": [lk, hk], "p_high": boot_p(dK)})
    # acting on HIGH, on HIGH + MEDIUM, on everything
    w = by["WaRF, band (then |Lambda|)"]
    f = by["first agent asked, random abstention"]
    K_first = sum(f.ok)
    say(f"  Acting on WaRF's verdict by band (the first agent asked is right {K_first} of {n} overall):")
    out["acting"] = {}
    for rule, bands in (("HIGH only", {"HIGH"}), ("HIGH + MEDIUM", {"HIGH", "MEDIUM"}), ("everything", {"HIGH", "MEDIUM", "LOW"})):
        act = [i for i, s in enumerate(sess) if s["confidence"] in bands]
        k = len(act)
        right = sum(w.ok[i] for i in act)
        lo, hi = cp(right, k)
        first_same = sum(f.ok[i] for i in act)
        exp_r = k * K_first / n
        p_h = hyper_ge(right, n, K_first, k)
        rest = [i for i in range(n) if i not in set(act)]
        fr = sum(w.ok[i] for i in rest)
        p_f = fisher(right, k - right, fr, len(rest) - fr) if rest else NAN
        say(f"    {rule:<14} coverage {k:>2}/{n} ({k / n:.2f}): right {right}, wrong acted on {k - right}, accuracy "
            f"{right / k:.3f} [{lo:.3f}, {hi:.3f}]; WaRF on the rest {fr}/{len(rest)}"
            + (f" (Fisher p {p_f:.3f})" if rest else "")
            + f"; first agent at random abstention: expected right {exp_r:.1f}, wrong {k - exp_r:.1f} "
              f"(P(>= {right} right) = {p_h:.3f}); first agent on these same sessions: {first_same} right")
        out["acting"][rule] = {"coverage": k, "right": right, "wrong_acted_on": k - right, "acc": right / k,
                               "cp95": [lo, hi], "rest_right": fr, "rest_n": len(rest), "fisher_p": p_f,
                               "first_random_expected_right": exp_r, "hyper_p": p_h, "first_same_sessions_right": first_same}
    cells = {}
    for i, s in enumerate(sess):
        cells.setdefault(s["confidence"], []).append(i)
    say("  By band: sessions, WaRF right, first agent asked right; validation (planted-defect) files among them:")
    out["bands"] = {}
    for b in ("HIGH", "MEDIUM", "LOW"):
        ii = cells.get(b, [])
        val = [i for i in ii if is_validation(sess[i])]
        say(f"    {b:<7}{len(ii):>4}{sum(w.ok[i] for i in ii):>5}{sum(f.ok[i] for i in ii):>5}   validation files {len(val)}, "
            f"WaRF right on them {sum(w.ok[i] for i in val)}; other files {len(ii) - len(val)}, WaRF right "
            f"{sum(w.ok[i] for i in ii if i not in val)}")
        out["bands"][b] = {"n": len(ii), "warf_right": sum(w.ok[i] for i in ii), "first_right": sum(f.ok[i] for i in ii),
                           "validation_n": len(val), "validation_right": sum(w.ok[i] for i in val)}
    hi_i = cells.get("HIGH", [])
    say("    HIGH sessions: " + "; ".join(
        f"{Path(sess[i]['artifact'].replace(chr(92), '/')).name} {sess[i]['decision']} truth {yy[i]}"
        f"{' (debate)' if sess[i].get('debate') else ''}" for i in hi_i))
    nv = [i for i in range(n) if not is_validation(sess[i])]
    nvh = [i for i in nv if sess[i]["confidence"] == "HIGH"]
    say(f"    without the validation files ({len(nv)} sessions): WaRF right {sum(w.ok[i] for i in nv)}, first agent "
        f"{sum(f.ok[i] for i in nv)}; HIGH {len(nvh)} sessions, {sum(w.ok[i] for i in nvh)} right")
    return out


yy_stored = [lbl[s["oracle"]["x_star"]] for s in lab]
yy_current = []
for s in lab:
    t = truth_for(s["artifact"], truths)
    yy_current.append(t.label if t else lbl[s["oracle"]["x_star"]])
RES["corpus62"] = {"stored": corpus_block("the label stored with each session (as policy.md scores the bands)", yy_stored)}
say(f"\n  ({sum(a != b for a, b in zip(yy_stored, yy_current))} sessions get another label under the current per-file truth)")
RES["corpus62"]["current"] = corpus_block("the current label per file (tools/_groundtruth.py)", yy_current)
nonval = [i for i, s in enumerate(lab) if not is_validation(s)]
say(f"\n  Without WaRF's own planted-defect examples (validation/M-*): {len(nonval)} sessions on real code")
RES["corpus62"]["stored_without_validation"] = corpus_block(
    "stored labels, real code only", [yy_stored[i] for i in nonval], [lab[i] for i in nonval])

# ============================================================================================
# 3. The 12-file persona experiment (persona_v3: WaRF's current personas, every agent votes)
# ============================================================================================
say("\n" + "=" * 112)
say("3. The persona experiment, persona_v3 (12 files, Claude Haiku 4.5, every agent votes)")
say("=" * 112)
pool = load_pool(EXP, "persona_v3")
items = sorted(pool.items())
arts = [a for a, _ in items]
ses = [s for _, s in items]
y12c = []
for a, s in items:
    t = truth_for(a, truths)
    y12c.append(t.label if t else lbl[s["oracle"]["x_star"]])
y12s = [lbl[s["oracle"]["x_star"]] for s in ses]
uni = [uniform_replay(s) for s in ses]
agr = [round(agreement(s), 6) for s in ses]
order12 = ses[0]["_order"]
RES["persona12"] = {}


def persona_block(truth_name, yy):
    n = len(ses)
    say(f"\n  Truth: {truth_name}: {yy.count('APPROVE')} clean, {yy.count('REJECT')} defective")
    sysl = [
        System("WaRF uniform, band", [u[0] for u in uni], [(BAND[u[1]], round(abs(u[2]), 4)) for u in uni], yy,
               [u[1] == "HIGH" for u in uni]),
        System("WaRF uniform, vote agreement", [u[0] for u in uni], agr, yy, [u[1] == "HIGH" for u in uni]),
        System("WaRF as run, band", [s["decision"] for s in ses],
               [(BAND[s["confidence"]], round(abs(s["sprt_lambda"]), 4)) for s in ses], yy,
               [s["confidence"] == "HIGH" for s in ses]),
        System("WaRF as run, vote agreement", [s["decision"] for s in ses], agr, yy, [s["confidence"] == "HIGH" for s in ses]),
        System("first agent asked as run, random", [lbl[s["votes"][0]["vote"]] for s in ses], [0] * n, yy),
    ]
    for a in order12:
        sysl.append(System(f"{a} alone, random", [lbl[next(v['vote'] for v in s['votes'] if v['agent'] == a)] for s in ses],
                           [0] * n, yy))
    pr = random.Random(23)
    pm = []
    for _ in range(NP):
        p = list(range(n))
        pr.shuffle(p)
        pm.append(p)
    say(f"  {'system':<36}{'right':>6}" + "".join(f"{int(q * 100):>6}%" for q in COV) + f"{'AURC':>8}{'perm p':>8}{'trust AUROC':>12}")
    out = {"systems": {}}
    for s in sysl:
        C = cum_correct(s.c, s.ok)
        accs = [acc_k(C, q * n) for q in COV]
        pp = perm_p(s, pm) if len(set(s.c)) > 1 else NAN
        ta = trust_auc(s.c, s.ok)
        say(f"  {s.name:<36}{sum(s.ok):>6}" + "".join(f"{v:>7.3f}" for v in accs) + f"{aurc(C):>8.3f}{f2(pp):>8}{f3(ta):>12}")
        out["systems"][s.name] = {"right": sum(s.ok), "acc_at": accs, "aurc": aurc(C), "perm_p": pp, "trust_auroc": ta}
    say(f"  (coverages are {', '.join(f'{q * n:g}' for q in COV)} files)")
    out["acting"] = {}
    for tag, sname, bands_of in (("uniform", "WaRF uniform, band", [u[1] for u in uni]),
                                 ("as run", "WaRF as run, band", [s["confidence"] for s in ses])):
        w = next(s for s in sysl if s.name == sname)
        for rule, bands in (("HIGH only", {"HIGH"}), ("HIGH + MEDIUM", {"HIGH", "MEDIUM"})):
            act = [i for i in range(n) if bands_of[i] in bands]
            k = len(act)
            right = sum(w.ok[i] for i in act)
            rest = [i for i in range(n) if i not in act]
            fr = sum(w.ok[i] for i in rest)
            p_f = fisher(right, k - right, fr, len(rest) - fr) if rest else NAN
            lo, hi = cp(right, k)
            singles = []
            for s in sysl[4:]:
                K = sum(s.ok)
                singles.append(f"{s.name.split(',')[0].replace(' alone', '')} {K}/{n}: exp. wrong {k * (n - K) / n:.1f}, "
                               f"P(>= {right} right) {hyper_ge(right, n, K, k):.3f}")
            say(f"  {tag:<8}{rule:<14} coverage {k}/{n}: right {right}, wrong acted on {k - right}, accuracy {right / k:.2f} "
                f"[{lo:.2f}, {hi:.2f}]; rest {fr}/{len(rest)} (Fisher p {p_f:.2f})")
            say("      random abstention at the same coverage: " + "; ".join(singles))
            out["acting"][f"{tag} {rule}"] = {"coverage": k, "right": right, "wrong_acted_on": k - right, "cp95": [lo, hi],
                                              "rest_right": fr, "rest_n": len(rest), "fisher_p": p_f}
    return out


say("  file                      truth     agreement  uniform           as run            source")
for a, s, u, g, t in zip(arts, ses, uni, agr, y12c):
    say(f"  {Path(a.replace(chr(92), '/')).name:<26}{t:<10}{g:>6.2f}     {u[0]:<8}{u[1]:<8}  {s['decision']:<8}{s['confidence']:<8}  "
        f"{'validation/ (planted defect)' if is_validation(s) else 'real code'}")
RES["persona12"]["current"] = persona_block("the current label per file (help.py REJECT)", y12c)
RES["persona12"]["stored"] = persona_block("the label stored with each session (help.py APPROVE)", y12s)

(HERE / "triage.log").write_text("\n".join(LOG) + "\n", encoding="utf-8")


def clean(o):
    if isinstance(o, float):
        return None if o != o else round(o, 6)
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


(HERE / "triage.json").write_text(json.dumps(clean(RES), indent=1), encoding="utf-8")
