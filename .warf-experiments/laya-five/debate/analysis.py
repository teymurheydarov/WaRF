"""What WaRF's debate round did to the five Laya agents (laya-five). Read-only on the experiment.

    PYTHONIOENCODING=utf-8 C:\\workdir\\claudeVersuch\\gs\\cf\\python.exe -I analysis.py [B]

Needs cut.json from tokens.py (which parts of the Round-1 summary each Round-2 call kept).
Writes results.json next to this file."""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stats import (auc_w, corr, counts, delong_paired, hanley_mcneil, logit, mean, ols, pct,  # noqa: E402
                   sign_test)

EXP = Path(r"C:\workdir\warf\WaRF\.warf-experiments\laya-five")
AG = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
B = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
rng = random.Random(20261101)

sel = [json.loads(l) for l in (EXP / "selection.jsonl").open(encoding="utf-8")]
pair_of = {s["id"]: i // 2 for i, s in enumerate(sel)}
S = {s["id"]: s for s in sel}
ALL = [json.loads(l) for l in (EXP / "sessions.jsonl").open(encoding="utf-8")]
R = [r for r in ALL if len(r["five"]["round2"]) == 5]          # the 98 commits that had a debate
cut = json.loads((HERE / "cut.json").read_text(encoding="utf-8"))["cuts"]
n = len(R)
y = [r["five"]["label"] == "REJECT" for r in R]
res = {"n_debate": n, "n_all": len(ALL), "later_fixed_in_debate": sum(y)}
print(f"{len(ALL)} commits, {n} with a debate round ({sum(y)} later fixed, {n - sum(y)} never fixed); B = {B}")


def p(r, rnd, a):
    return r["five"][rnd][a]["p_reject"]


def rej(r, rnd, a):
    return r["five"][rnd][a]["choice"] == "REJECT"


def ci(v):
    return pct(v, 0.025), pct(v, 0.975)


# ---------------------------------------------------------------- per-agent variables
V = {}
for a in AG:
    others = [b for b in AG if b != a]
    V[a] = {
        "p1": [p(r, "round1", a) for r in R],
        "p2": [p(r, "round2", a) for r in R],
        "own": [float(rej(r, "round1", a)) for r in R],
        "K": [float(sum(rej(r, "round1", b) for b in others)) for r in R],
        # what the readouts showed: p(REJECT) to two decimals, averaged over the four others
        "mp": [mean([round(p(r, "round1", b), 2) for b in others]) for r in R],
        "po": [[p(r, "round1", b) for b in others] for r in R],
        "full": [cut[f"{r['five']['id']}|{a}"]["dropped"] == 0 for r in R],
        "labels_all": [all(ok for k, ok in cut[f"{r['five']['id']}|{a}"]["parts"].items() if k.startswith("label:"))
                       for r in R],
        "Kseen": [float(sum(rej(r, "round1", b) for b in others
                            if cut[f"{r['five']['id']}|{a}"]["parts"][f"label:{b}"])) for r in R],
    }

# ---------------------------------------------------------------- Q1: does Round-2 p follow the others?
MODELS = {
    # name: (outcome(row index) -> float, design row(row index) -> list, index of the coefficient reported)
    "naive: p2 ~ K": (lambda v, i: v["p2"][i], lambda v, i: [1.0, v["K"][i]], 1),
    "naive: p2 - p1 ~ K": (lambda v, i: v["p2"][i] - v["p1"][i], lambda v, i: [1.0, v["K"][i]], 1),
    "p2 ~ p1 + K (main)": (lambda v, i: v["p2"][i], lambda v, i: [1.0, v["p1"][i], v["K"][i]], 2),
    "p2 ~ p1 + p1^2 + own vote + K": (lambda v, i: v["p2"][i],
                                      lambda v, i: [1.0, v["p1"][i], v["p1"][i] ** 2, v["own"][i], v["K"][i]], 4),
    "logit p2 ~ logit p1 + K": (lambda v, i: logit(v["p2"][i]), lambda v, i: [1.0, logit(v["p1"][i]), v["K"][i]], 2),
    "p2 ~ p1 + others' mean readout (per 0.1)": (lambda v, i: v["p2"][i],
                                                 lambda v, i: [1.0, v["p1"][i], 10 * v["mp"][i]], 2),
}


def fit(a, model, rows, w=None):
    """The reported coefficient (column j of the model) and all coefficients. A control column
    with no variation among the rows drawn (TEST-FOCUSED never votes REJECT in Round 1, so its own
    vote is constant) is dropped; the reported column is never dropped (None if it is constant)."""
    fy, fx, j = MODELS[model]
    v = V[a]
    X = [fx(v, i) for i in rows]
    yy = [fy(v, i) for i in rows]
    if w is not None:
        w = [w[i] for i in rows]
    used = [i for i in range(len(rows)) if w is None or w[i]]
    keep = [c for c in range(len(X[0]))
            if c == 0 or c == j or len({X[i][c] for i in used}) > 1]
    if len({X[i][j] for i in used}) < 2:
        return None, None
    Xk = [[row[c] for c in keep] for row in X]
    beta = ols(Xk, yy, w)
    if beta is None:
        return None, None
    full = [0.0] * len(X[0])
    for c, b in zip(keep, beta):
        full[c] = b
    return full[j], full


def subset(a, name):
    if name == "all 98":
        return list(range(n))
    if name == "summary read in full":
        return [i for i in range(n) if V[a]["full"][i]]
    if name == "every vote label seen":
        return [i for i in range(n) if V[a]["labels_all"][i]]
    raise KeyError(name)


SUBSETS = ("all 98", "summary read in full")
q1 = {}
boot_w = [counts(rng, n) for _ in range(B)]                      # shared commit resamples
for sub in SUBSETS:
    q1[sub] = {}
    print(f"\nQ1 [{sub}]  coefficient on the others' Round-1 REJECT votes, 95 % bootstrap over commits")
    for model in MODELS:
        q1[sub][model] = {}
        line = []
        per_agent_boot = {}
        for a in AG:
            rows = subset(a, sub)
            k_var = len({V[a]["K"][i] for i in rows})
            est, beta = fit(a, model, rows)
            draws = []
            for w in boot_w:
                if sum(w[i] for i in rows) < 10:
                    continue
                e, _ = fit(a, model, rows, w)
                draws.append(e)
            ok = [d for d in draws if d is not None]
            per_agent_boot[a] = draws
            lo, hi = ci(ok)
            q1[sub][model][a] = {"n": len(rows), "est": est, "lo": lo, "hi": hi, "beta": beta,
                                 "boot_failed": len(draws) - len(ok), "K_values": k_var}
            line.append(f"{a[:8]:>8} {est:+.3f} [{lo:+.3f},{hi:+.3f}] n={len(rows)}")
        # pooled: the mean of the five coefficients, on the same resamples
        if all(len(per_agent_boot[a]) == B for a in AG):
            pooled = [mean([per_agent_boot[a][b] for a in AG]) for b in range(B)
                      if all(per_agent_boot[a][b] is not None for a in AG)]
            est = mean([q1[sub][model][a]["est"] for a in AG])
            lo, hi = ci(pooled)
            q1[sub][model]["pooled"] = {"est": est, "lo": lo, "hi": hi}
            line.append(f"  pooled {est:+.3f} [{lo:+.3f},{hi:+.3f}]")
        print(f"  {model}")
        print("     " + " | ".join(line))
res["q1"] = q1

# the main model's other coefficients, for context (regression to the mean: slope on p1 < 1)
print("\n  main model p2 = b0 + b1 p1 + c K, all 98: b0, b1, c; residual sd; mean shift p2 - p1")
for a in AG:
    v = V[a]
    est, beta = fit(a, "p2 ~ p1 + K (main)", list(range(n)))
    resid = [v["p2"][i] - (beta[0] + beta[1] * v["p1"][i] + beta[2] * v["K"][i]) for i in range(n)]
    sd = (sum(e * e for e in resid) / (n - 3)) ** 0.5
    sh = [v["p2"][i] - v["p1"][i] for i in range(n)]
    shb = [sum(w[i] * sh[i] for i in range(n)) / n for w in boot_w]
    lo, hi = ci(shb)
    print(f"  {a:<13} b0 {beta[0]:+.3f}  b1 {beta[1]:.3f}  c {beta[2]:+.4f}  resid sd {sd:.3f}  "
          f"corr(p1,p2) {corr(v['p1'], v['p2']):.3f}  mean shift {mean(sh):+.3f} [{lo:+.3f},{hi:+.3f}]  "
          f"corr(p1,K) {corr(v['p1'], v['K']):.2f}")
    res.setdefault("main_detail", {})[a] = {"b0": beta[0], "b1": beta[1], "c": beta[2], "resid_sd": sd,
                                            "mean_shift": mean(sh), "shift_lo": lo, "shift_hi": hi,
                                            "corr_p1_K": corr(v["p1"], v["K"])}

# ------------------------------------------------ Q1 controls: shuffled K, planted effect, negative-control outcomes
print("\n  shuffled control: K permuted across commits (2000 shuffles), main model, all 98")
res["q1_shuffle"] = {}
for a in AG:
    v = V[a]
    obs = q1["all 98"]["p2 ~ p1 + K (main)"][a]["est"]
    null = []
    for _ in range(2000):
        Kp = v["K"][:]
        rng.shuffle(Kp)
        X = [[1.0, v["p1"][i], Kp[i]] for i in range(n)]
        null.append(ols(X, v["p2"])[2])
    pv = (1 + sum(abs(x) >= abs(obs) for x in null)) / (1 + len(null))
    lo, hi = ci(null)
    res["q1_shuffle"][a] = {"obs": obs, "null_lo": lo, "null_hi": hi, "p": pv}
    print(f"  {a:<13} observed {obs:+.4f}; shuffled 95 % range [{lo:+.4f},{hi:+.4f}]; permutation p = {pv:.3f}")

print("\n  planted control: p2 + delta*K for delta = 0.01, 0.02, 0.05 (main model, all 98, bootstrap B/4)")
res["q1_planted"] = {}
for delta in (0.01, 0.02, 0.05):
    line = []
    for a in AG:
        v = V[a]
        y2 = [v["p2"][i] + delta * v["K"][i] for i in range(n)]
        X = [[1.0, v["p1"][i], v["K"][i]] for i in range(n)]
        est = ols(X, y2)[2]
        draws = [ols(X, y2, w)[2] for w in boot_w[: B // 4]]
        lo, hi = ci(draws)
        res["q1_planted"][f"{a}|{delta}"] = {"est": est, "lo": lo, "hi": hi}
        line.append(f"{a[:8]} {est:+.3f} [{lo:+.3f},{hi:+.3f}]")
    print(f"  delta {delta:.2f}: " + " | ".join(line))

print("\n  negative-control outcomes (never saw the five agents' votes) on the agent's own p1 and K, all 98")
NC = {
    "single Laya, sweep question": lambda r: S[r["five"]["id"]]["p_single_laya"],
    "single Laya, debate prompt alone": lambda r: S[r["five"]["id"]]["p_single_debate"]["alone"],
    "single Laya, debate, shuffled CLAUDE": lambda r: S[r["five"]["id"]]["p_single_debate"]["shuffled"],
}
res["q1_negative_control"] = {}
for treat, col in (("K", lambda v, i: v["K"][i]), ("mean readout per 0.1", lambda v, i: 10 * v["mp"][i])):
    print(f"   treatment: {treat}")
    for name, fn in NC.items():
        out = [fn(r) for r in R]
        line = []
        for a in AG:
            v = V[a]
            X = [[1.0, v["p1"][i], col(v, i)] for i in range(n)]
            est = ols(X, out)[2]
            draws = [ols(X, out, w)[2] for w in boot_w[: B // 2]]
            lo, hi = ci(draws)
            res["q1_negative_control"][f"{treat}|{name}|{a}"] = {"est": est, "lo": lo, "hi": hi}
            line.append(f"{a[:8]} {est:+.3f} [{lo:+.3f},{hi:+.3f}]")
        print(f"  {name:<36} " + " | ".join(line))

# regression discontinuity at SKEPTIC's threshold: SKEPTIC's p sits near 0.5, so whether the summary
# shows it as APPROVE or REJECT is close to a coin flip at a fixed latent. Within |p_S - 0.5| <= h:
#   y = a + b p1_agent + g 1[p_S > 0.5] + d1 s + d2 s 1[p_S > 0.5],  s = p_S - 0.5
# g on y = p2 is the jump caused by the label; on y = p1 (which never saw the summary) it must be ~0.
print("\n  discontinuity at SKEPTIC's Round-1 threshold (the label it shows the other four flips at p = 0.5)")
res["q1_rd"] = {}
pS = [p(r, "round1", "SKEPTIC") for r in R]
for h in (0.10, 0.15):
    rows = [i for i in range(n) if abs(pS[i] - 0.5) <= h]
    left = sum(pS[i] <= 0.5 for i in rows)
    print(f"   bandwidth {h:.2f}: {len(rows)} commits ({left} shown APPROVE, {len(rows) - left} REJECT)")
    for a in AG[1:]:
        v = V[a]
        line = []
        for outname, outc, ctrl in (("p2", v["p2"], True), ("placebo p1", v["p1"], False)):
            def design(i):
                s = pS[i] - 0.5
                t = 1.0 if pS[i] > 0.5 else 0.0
                return ([1.0, v["p1"][i]] if ctrl else [1.0]) + [t, s, s * t]
            j = 2 if ctrl else 1
            X = [design(i) for i in rows]
            yy = [outc[i] for i in rows]
            est = ols(X, yy)[j]
            draws = []
            for w in boot_w:
                ww = [w[i] for i in rows]
                if sum(ww) < 10:
                    continue
                bta = ols(X, yy, ww)
                if bta is not None:
                    draws.append(bta[j])
            lo, hi = ci(draws)
            res["q1_rd"][f"{h}|{a}|{outname}"] = {"n": len(rows), "est": est, "lo": lo, "hi": hi}
            line.append(f"{outname} jump {est:+.3f} [{lo:+.3f},{hi:+.3f}]")
        print(f"  {a:<13} " + " | ".join(line))

# hidden vote labels (TEST-FOCUSED lost BOUNDARY's label in 11 calls): seen vs hidden REJECTs
a = "TEST-FOCUSED"
v = V[a]
hidden = [v["K"][i] - v["Kseen"][i] for i in range(n)]
print(f"\n  {a}: commits where a hidden label was a REJECT: {sum(h > 0 for h in hidden)} (too few to separate seen from hidden)")
res["tf_hidden_reject_labels"] = sum(h > 0 for h in hidden)

# ---------------------------------------------------------------- Q2: vote changes toward the label?
print("\nQ2  vote changes Round 1 -> Round 2, toward / away from the git-history label (two-sided sign test)")
q2 = {}
tot_t = tot_a = 0
for a in AG:
    t = aw = ra_t = ra_a = ar_t = ar_a = 0
    for r, lab in zip(R, y):
        c1, c2 = rej(r, "round1", a), rej(r, "round2", a)
        if c1 == c2:
            continue
        toward = c2 == lab
        t += toward
        aw += not toward
        if c1 and not c2:
            ra_t += toward
            ra_a += not toward
        else:
            ar_t += toward
            ar_a += not toward
    tot_t += t
    tot_a += aw
    q2[a] = {"changes": t + aw, "toward": t, "away": aw, "p": sign_test(t, t + aw),
             "REJECT->APPROVE": [ra_t, ra_a], "APPROVE->REJECT": [ar_t, ar_a]}
    print(f"  {a:<13} {t + aw:>3} changes: {t} toward, {aw} away, sign test p = {sign_test(t, t + aw):.3f}   "
          f"(REJECT->APPROVE {ra_t}/{ra_a}, APPROVE->REJECT {ar_t}/{ar_a} toward/away)")
q2["pooled"] = {"changes": tot_t + tot_a, "toward": tot_t, "away": tot_a, "p": sign_test(tot_t, tot_t + tot_a)}
print(f"  {'pooled':<13} {tot_t + tot_a:>3} changes: {tot_t} toward, {tot_a} away, sign test p = "
      f"{sign_test(tot_t, tot_t + tot_a):.3f}")
# commits carry several changes: a label-swap test inside the matched pairs keeps that dependence
pairs = {}
for i, r in enumerate(R):
    pairs.setdefault(pair_of[r["five"]["id"]], []).append(i)
chg = [[(rej(r, "round1", a), rej(r, "round2", a)) for a in AG] for r in R]


def net_toward(lab):
    s = 0
    for i in range(n):
        for c1, c2 in chg[i]:
            if c1 != c2:
                s += 1 if c2 == lab[i] else -1
    return s


obs = net_toward(y)
null = []
for _ in range(20000):
    lab = y[:]
    for idx in pairs.values():
        if rng.random() < 0.5:                       # swap which member of the pair was later fixed
            for i in idx:
                lab[i] = not lab[i]
    null.append(net_toward(lab))
pv = (1 + sum(abs(x) >= abs(obs) for x in null)) / (1 + len(null))
q2["pooled"]["pair_swap_p"] = pv
q2["pooled"]["net_toward"] = obs
print(f"  pooled, label swap within the matched pairs (keeps the five agents of a commit together): "
      f"net toward {obs:+d}, p = {pv:.3f}")
commits_changed = sum(any(c1 != c2 for c1, c2 in chg[i]) for i in range(n))
print(f"  changes fall on {commits_changed} of {n} commits")
q2["commits_with_change"] = commits_changed
res["q2"] = q2

# ---------------------------------------------------------------- Q3: ranking, Round 1 vs Round 2
print("\nQ3  panel ranking: AUC of the mean of the five p(REJECT), Round 1 vs Round 2")
m1 = [mean([p(r, "round1", a) for a in AG]) for r in R]
m2 = [mean([p(r, "round2", a) for a in AG]) for r in R]
units = [idx for idx in pairs.values()]
q3 = {}


def paired(name, s1, s2, lab, units_):
    a1, a2 = auc_w(s1, lab), auc_w(s2, lab)
    n1, n0 = sum(lab), len(lab) - sum(lab)
    diffs_pair, diffs_strat = [], []
    pos_i = [i for i, t in enumerate(lab) if t]
    neg_i = [i for i, t in enumerate(lab) if not t]
    for _ in range(B):
        w = counts(rng, len(lab), units_)
        diffs_pair.append(auc_w(s2, lab, w) - auc_w(s1, lab, w))
        w = [0] * len(lab)
        for _ in range(n1):
            w[pos_i[rng.randrange(n1)]] += 1
        for _ in range(n0):
            w[neg_i[rng.randrange(n0)]] += 1
        diffs_strat.append(auc_w(s2, lab, w) - auc_w(s1, lab, w))
    dl = delong_paired(s1, s2, lab)
    q3[name] = {"n": len(lab), "auc_r1": a1, "se_r1": hanley_mcneil(a1, n1, n0), "auc_r2": a2,
                "se_r2": hanley_mcneil(a2, n1, n0), "diff": a2 - a1,
                "pair_boot": ci(diffs_pair), "strat_boot": ci(diffs_strat),
                "boot_se": (sum((d - mean(diffs_strat)) ** 2 for d in diffs_strat) / (B - 1)) ** 0.5,
                "delong": {"se": dl[3], "z": dl[4], "p": dl[5]}}
    q = q3[name]
    print(f"  {name:<44} n={len(lab)}  R1 {a1:.3f} ±{q['se_r1']:.3f}  R2 {a2:.3f} ±{q['se_r2']:.3f}  "
          f"R2-R1 {a2 - a1:+.3f}  pair-bootstrap [{q['pair_boot'][0]:+.3f},{q['pair_boot'][1]:+.3f}]  "
          f"stratified [{q['strat_boot'][0]:+.3f},{q['strat_boot'][1]:+.3f}]  DeLong p {dl[5]:.2f}")


paired("mean p of the five (98 debated)", m1, m2, y, units)
# all 100: the two commits WaRF decided in Round 1 keep their Round-1 p as their final position
yA = [r["five"]["label"] == "REJECT" for r in ALL]
pA = {}
for i, r in enumerate(ALL):
    pA.setdefault(pair_of[r["five"]["id"]], []).append(i)
m1A = [mean([p(r, "round1", a) for a in AG]) for r in ALL]
m2A = [mean([p(r, "round2" if r["five"]["round2"] else "round1", a) for a in AG]) for r in ALL]
paired("mean p, all 100 (2 undebated keep Round 1)", m1A, m2A, yA, list(pA.values()))
k1 = [float(sum(rej(r, "round1", a) for a in AG)) for r in R]
k2 = [float(sum(rej(r, "round2", a) for a in AG)) for r in R]
paired("number of REJECT votes (98 debated)", k1, k2, y, units)
for a in AG:
    paired(f"{a} p(REJECT) (98 debated)", V[a]["p1"], V[a]["p2"], y, units)
res["q3"] = q3

# how much did the panel's ordering move?
def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    rk = [0.0] * len(v)
    for pos, i in enumerate(order):
        rk[i] = pos
    return rk


print(f"  Spearman(mean p Round 1, mean p Round 2) = {corr(ranks(m1), ranks(m2)):.3f}; "
      f"Pearson = {corr(m1, m2):.3f}")
res["q3_rank_corr"] = corr(ranks(m1), ranks(m2))

# ---------------------------------------------------------------- Q4: how much of the summary was seen
print("\nQ4  Round-2 summary cut by Laya's window (state_tokens_dropped > 0), per agent")
q4 = {}
for a in AG:
    rows = [cut[f"{r['five']['id']}|{a}"] for r in R]
    nc = sum(c["dropped"] > 0 for c in rows)
    instr_only = sum(c["dropped"] > 0 and all(ok for k, ok in c["parts"].items() if k != "turn") for c in rows)
    lost_readout = sum(any(not ok for k, ok in c["parts"].items() if k.startswith("other:")) for c in rows)
    lost_label = sum(any(not ok for k, ok in c["parts"].items() if k.startswith("label:")) for c in rows)
    seen_frac = mean([c["seen_tail_tokens"] / c["tail_tokens"] for c in rows])
    lab_cut = [y[i] for i, c in enumerate(rows) if c["dropped"] > 0]
    q4[a] = {"n": n, "cut": nc, "frac": nc / n, "instructions_only": instr_only, "lost_a_readout": lost_readout,
             "lost_a_vote_label": lost_label, "mean_frac_tokens_seen": seen_frac,
             "cut_later_fixed": sum(lab_cut)}
    print(f"  {a:<13} cut {nc:>2}/{n} ({100 * nc / n:4.1f} %): only the closing instructions {instr_only}, "
          f"an agent's readout lost {lost_readout}, an agent's vote label lost {lost_label}; "
          f"mean share of summary tokens seen {100 * seen_frac:.1f} %; cut commits later fixed {sum(lab_cut)}/{nc}")
res["q4"] = q4

(HERE / "results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print("\nwrote", HERE / "results.json")
