"""
Evidence for and against WaRF's claimed benefits, from stored data only.

No model or service is called. Nothing outside this folder is written.
Reads:
  .warf/sessions.jsonl                         the labelled corpus (Claude Haiku 4.5, 62 developer labels)
  .warf-experiments/sessions.jsonl             the 12-file persona experiment (mixed vs cloned pools)
  .warf-experiments/jev-five/sessions_one.jsonl, sessions_standard.jsonl
                                               one Jev agent / WaRF's default review on Jev, 100 gismo6 commits
  .warf-experiments/jev-five/verify/refute/features.jsonl   added lines per commit
  .warf-experiments/laya-five/sessions.jsonl, selection.jsonl   five Laya agents; Claude's and single Laya's p
Writes claims_evidence.log next to this file.

    PYTHONIOENCODING=utf-8 C:/workdir/claudeVersuch/gs/cf/python.exe -B claims_evidence.py

Pure Python (numpy's BLAS crashes in this interpreter).
"""
import collections
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path("C:/workdir/warf/WaRF")
EXP = ROOT / ".warf-experiments"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from _groundtruth import corpus_truth, truth_for          # noqa: E402
from compare_pools import load_pool, uniform_replay        # noqa: E402
from warf.engine import A, B, LLR_APPROVE, LLR_REJECT, THETA, synthesis   # noqa: E402

out = []


def say(s=""):
    out.append(s)
    print(s)


def read(p):
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]


# ── exact statistics, pure Python ─────────────────────────────────────────────────────────────

def binom_pmf(k, n, p):
    return math.comb(n, k) * p ** k * (1 - p) ** (n - k)


def binom_test(k, n, p=0.5):
    """Two-sided exact binomial test (sum of outcomes no more likely than the observed one)."""
    obs = binom_pmf(k, n, p)
    return min(1.0, sum(binom_pmf(i, n, p) for i in range(n + 1) if binom_pmf(i, n, p) <= obs * (1 + 1e-9)))


def cp_ci(k, n, level=0.95):
    """Clopper-Pearson interval by bisection on the binomial tail."""
    a = (1 - level) / 2

    def upper_tail(p):            # P(X >= k | p)
        return sum(binom_pmf(i, n, p) for i in range(k, n + 1))

    def lower_tail(p):            # P(X <= k | p)
        return sum(binom_pmf(i, n, p) for i in range(0, k + 1))

    def solve(f, target, increasing):
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if (f(mid) < target) == increasing:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(upper_tail, a, True)
    upper = 1.0 if k == n else solve(lower_tail, a, False)
    return lower, upper


def sign_p(b, c):
    """Exact two-sided sign (McNemar) test on b against c discordant items."""
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def fisher(a, b, c, d):
    """Two-sided Fisher exact test for [[a, b], [c, d]] (rows: groups; cols: right, wrong)."""
    r1, r2, c1 = a + b, c + d, a + c
    n = r1 + r2

    def pr(x):
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)
    obs = pr(a)
    lo, hi = max(0, c1 - r2), min(r1, c1)
    return min(1.0, sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= obs * (1 + 1e-9)))


def trend_exact(bands):
    """Exact conditional test that accuracy rises with the band order.

    bands: [(n, right)] from the lowest band to the highest. Conditional on the band sizes
    and the total number right, the counts right per band are multivariate hypergeometric
    under 'accuracy does not depend on the band'. Statistic: sum of band index * right.
    Returns the one-sided p of a statistic at least as large as observed.
    """
    sizes = [n for n, _ in bands]
    total = sum(k for _, k in bands)
    N = sum(sizes)
    obs = sum(i * k for i, (_, k) in enumerate(bands))
    denom = math.comb(N, total)
    p = 0.0

    def rec(i, left, stat, prob):
        nonlocal p
        if i == len(sizes) - 1:
            if 0 <= left <= sizes[i]:
                s = stat + i * left
                if s >= obs:
                    p += prob * math.comb(sizes[i], left)
            return
        for k in range(0, min(sizes[i], left) + 1):
            rec(i + 1, left - k, stat + i * k, prob * math.comb(sizes[i], k))
    rec(0, total, 0, 1.0)
    return p / denom


def pct(k, n):
    return f"{k}/{n} = {k / n:.0%}" if n else f"{k}/{n}"


def ci_str(k, n):
    lo, hi = cp_ci(k, n)
    return f"[{lo:.2f}, {hi:.2f}]"


def bal(pairs):
    """Balanced accuracy of (prediction, truth) pairs."""
    by = collections.defaultdict(list)
    for p, t in pairs:
        by[t].append(p == t)
    rec = [sum(v) / len(v) for v in by.values()]
    return sum(rec) / len(rec)


def x_of(label):
    return 1 if label == "APPROVE" else -1


def boot_diff(items, f1, f2, reps=10000, seed=7, strata=None):
    """Bootstrap 95% interval of f1(sample) - f2(sample), resampling items (within strata)."""
    rng = random.Random(seed)
    groups = collections.defaultdict(list)
    for it in items:
        groups[strata(it) if strata else 0].append(it)
    ds = []
    for _ in range(reps):
        smp = []
        for g in groups.values():
            smp.extend(rng.choice(g) for _ in g)
        try:
            ds.append(f1(smp) - f2(smp))
        except ZeroDivisionError:
            continue
    ds.sort()
    return f1(items) - f2(items), ds[int(0.025 * len(ds))], ds[int(0.975 * len(ds)) - 1]


# ══════════════════════════════════════════════════════════════════════════════════════════════
say("=" * 104)
say("1. The labelled corpus (.warf/sessions.jsonl), Claude Haiku 4.5")
say("=" * 104)
corpus = read(ROOT / ".warf" / "sessions.jsonl")
lab = [s for s in corpus if s.get("oracle")]
truths = corpus_truth()

# 1a. Early stopping and cost
say("\n1a. Early stopping and cost (all logged sessions)")
for s in corpus:
    s["_era"] = "5-agent default" if s["created_at"][:10] >= "2026-07-22" else "3-agent default"
cnt = collections.Counter((s["_era"], len(s["votes"]), s["sprt_fired"]) for s in corpus)
say(f"  {len(corpus)} sessions; sprt_fired (HIGH) on {sum(s['sprt_fired'] for s in corpus)} "
    f"({sum(s['sprt_fired'] for s in corpus) / len(corpus):.0%}); the technical document quotes 109 of 246 (44%).")
for era in ("3-agent default", "5-agent default"):
    rows = sorted((k[1], k[2], v) for k, v in cnt.items() if k[0] == era)
    say(f"  {era}: " + ", ".join(f"{n} votes {'fired' if f else 'no boundary'} x{v}" for n, f, v in rows))
full5 = [s for s in corpus if s["_era"] == "5-agent default"
         and (len(s["votes"]) == 5 or (s["sprt_fired"] and len(s["votes"]) in (3, 4)))]
calls = [len(s["votes"]) for s in full5]
early = sum(1 for s in full5 if s["sprt_fired"] and len(s["votes"]) < 5)
say(f"  5-agent era, sessions that are full five-agent pools or stopped early at k=3/4 (upper bound on"
    f" early stops: some 3-vote sessions may be '--agents' pools of three): {len(full5)}")
say(f"    stopped before the fifth agent: {pct(early, len(full5))}; agent calls per review {sum(calls) / len(calls):.2f}"
    f" (a single agent: 1.00; five without early stopping: 5.00)")
tok = [(len(s["votes"]), s["sprt_fired"], s["total_tokens_in"] + s["total_tokens_out"]) for s in corpus
       if s["total_tokens_in"] + s["total_tokens_out"] > 0]
say(f"  token counts are logged on {len(tok)} of {len(corpus)} sessions (the CLI provider reports none)")
by_n = collections.defaultdict(list)
for n, f, t in tok:
    by_n[(n, f)].append(t)
for key in sorted(by_n):
    v = sorted(by_n[key])
    say(f"    {key[0]} votes, {'fired' if key[1] else 'no boundary'}: n {len(v)}, median tokens {v[len(v) // 2]},"
        f" per call {v[len(v) // 2] / key[0]:.0f}")

# 1b. Confidence bands vs the first agent asked
say("\n1b. Confidence bands on the 62 labelled sessions (stored labels), WaRF vs the first agent asked")
bands = {}
for band in ("LOW", "MEDIUM", "HIGH"):
    ss = [s for s in lab if s["confidence"] == band]
    w = [x_of(s["decision"]) == s["oracle"]["x_star"] for s in ss]
    f = [s["votes"][0]["vote"] == s["oracle"]["x_star"] for s in ss]
    b = sum(1 for a_, c_ in zip(w, f) if a_ and not c_)
    c = sum(1 for a_, c_ in zip(w, f) if c_ and not a_)
    bands[band] = (len(ss), sum(w), sum(f))
    say(f"  {band:<7} WaRF {pct(sum(w), len(ss)):<14} {ci_str(sum(w), len(ss))}   first agent {pct(sum(f), len(ss)):<14}"
        f" {ci_str(sum(f), len(ss))}   WaRF-only/agent-only right {b}/{c}, sign p {sign_p(b, c):.2f}")
order = ("LOW", "MEDIUM", "HIGH")
say(f"  exact trend test, accuracy rising LOW < MEDIUM < HIGH: WaRF one-sided p "
    f"{trend_exact([(bands[k][0], bands[k][1]) for k in order]):.3f}; first agent on the same bands p "
    f"{trend_exact([(bands[k][0], bands[k][2]) for k in order]):.3f}")
hn, hk = bands["HIGH"][0], bands["HIGH"][1]
rn, rk = bands["LOW"][0] + bands["MEDIUM"][0], bands["LOW"][1] + bands["MEDIUM"][1]
say(f"  HIGH vs the rest, WaRF right: {pct(hk, hn)} vs {pct(rk, rn)}, Fisher p {fisher(hk, hn - hk, rk, rn - rk):.2f}")
lk, ln_ = bands["LOW"][1], bands["LOW"][0]
say(f"  LOW 'below a coin flip': {pct(lk, ln_)}, exact binomial p vs 0.5 = {binom_test(lk, ln_):.3f}"
    f" (inverting LOW would give {ln_ - lk}/{ln_}; the first agent asked was right on {bands['LOW'][2]})")
mk, mn = bands["MEDIUM"][1], bands["MEDIUM"][0]
say(f"  MEDIUM vs LOW, WaRF right: Fisher p {fisher(mk, mn - mk, lk, ln_ - lk):.3f}")
ub = {}
for s in lab:
    d_, conf_, _, _ = uniform_replay(dict(s))
    ub.setdefault(conf_, []).append(x_of(d_) == s["oracle"]["x_star"])
say("  the same votes replayed at equal weights (what agreement alone gives): "
    + ", ".join(f"{k} {pct(sum(ub.get(k, [])), len(ub.get(k, [])))}" for k in order)
    + f"; trend p {trend_exact([(len(ub.get(k, [])), sum(ub.get(k, []))) for k in order]):.3f}")
say("  five equal-weight votes in LOGIC: a 3-2 split gives normalised +-0.2, margin exactly 0.2 -> "
    + "/".join(synthesis(v, [0.5] * 5, "LOGIC")[1].value for v in ([1, 1, 1, -1, -1], [1, 1, -1, -1, -1]))
    + " (LOW cannot occur in LOGIC on a fresh five-agent install)")
say("  split by what was reviewed (synthetic = validation/ files with a planted defect; real = requests, urllib3, G+Smo):")
for kind in ("synthetic", "real"):
    ss = [s for s in lab if ("validation" in s["artifact"].replace("\\", "/").split("/")) == (kind == "synthetic")]
    say(f"    {kind:<9} n {len(ss):>2}: " + ", ".join(
        f"{k} {pct(sum(x_of(s['decision']) == s['oracle']['x_star'] for s in ss if s['confidence'] == k), sum(1 for s in ss if s['confidence'] == k))}"
        for k in order)
        + f"; first agent asked right {pct(sum(s['votes'][0]['vote'] == s['oracle']['x_star'] for s in ss), len(ss))}"
        + f", WaRF right {pct(sum(x_of(s['decision']) == s['oracle']['x_star'] for s in ss), len(ss))}")
    if kind == "real":
        rb = [(sum(1 for s in ss if s["confidence"] == k),
               sum(x_of(s["decision"]) == s["oracle"]["x_star"] for s in ss if s["confidence"] == k)) for k in order]
        say(f"    real code only, exact trend test: one-sided p {trend_exact(rb):.3f}")
say("  HIGH sessions in detail:")
for s in [s for s in lab if s["confidence"] == "HIGH"]:
    say(f"    {s['created_at'][:10]}  {Path(s['artifact'].replace(chr(92), '/')).name:<30} {s['decision']:<7}"
        f" truth {s['oracle']['x_star_label']:<7} votes {len(s['votes'])} debate {'yes' if s.get('debate') else 'no'}"
        f"{'' if x_of(s['decision']) == s['oracle']['x_star'] else '   WRONG'}")

# 1c. Per-domain reliability: is the domain difference real?
say("\n1c. Per-domain accuracy of each agent where it voted (stored labels; debate sessions scored on Round 2 as WaRF does)")
per = collections.defaultdict(lambda: [0, 0])
appr = collections.defaultdict(lambda: [0, 0])       # an always-APPROVE agent on the same sessions
pairs_ad = collections.defaultdict(list)
for s in lab:
    votes = (s.get("debate") or {}).get("votes") or s["votes"]
    for v in votes:
        if v["agent"] == "SAST-BANDIT":
            continue
        k = per[(v["agent"], s["domain"])]
        k[0] += v["vote"] == s["oracle"]["x_star"]
        k[1] += 1
        a_ = appr[(v["agent"], s["domain"])]
        a_[0] += s["oracle"]["x_star"] == 1
        a_[1] += 1
        pairs_ad[(v["agent"], s["domain"])].append((v["vote"], s["oracle"]["x_star"]))
for agent in ("AUDITOR", "ADVOCATE", "SKEPTIC", "BOUNDARY", "TEST-FOCUSED"):
    lg, sc = per[(agent, "LOGIC")], per[(agent, "SECURITY")]
    pf = per[(agent, "PERFORMANCE")]
    fp = fisher(lg[0], lg[1] - lg[0], sc[0], sc[1] - sc[0]) if lg[1] and sc[1] else float("nan")
    say(f"  {agent:<13} LOGIC {pct(*lg):<14} SECURITY {pct(*sc):<14} PERFORMANCE {pct(*pf):<10}"
        f" LOGIC vs SECURITY Fisher p {fp:.2f}")
    say(f"  {'':<13} always-APPROVE on the same sessions: LOGIC {pct(*appr[(agent, 'LOGIC')]):<9}"
        f" SECURITY {pct(*appr[(agent, 'SECURITY')]):<9}; balanced accuracy LOGIC "
        f"{bal(pairs_ad[(agent, 'LOGIC')]) if len({t for _, t in pairs_ad[(agent, 'LOGIC')]}) > 1 else float('nan'):.2f}"
        f" SECURITY {bal(pairs_ad[(agent, 'SECURITY')]):.2f}")
base = collections.Counter((s["domain"], s["oracle"]["x_star_label"]) for s in lab)
say("  labels by domain: " + ", ".join(f"{d} {base[(d, 'APPROVE')]} APPROVE / {base[(d, 'REJECT')]} REJECT"
                                       for d in ("LOGIC", "SECURITY", "PERFORMANCE")))

# 1d. Learned weights against equal weights, same votes
say("\n1d. Learned weights vs equal weights on the same votes (62 labelled sessions)")
chg = []
for s in lab:
    uni = uniform_replay(dict(s))[0]
    if uni != s["decision"]:
        chg.append((uni, s["decision"], s["oracle"]["x_star_label"]))
to_right = sum(1 for u, d, t in chg if d == t)
say(f"  decisions changed by the learned weights: {len(chg)}; changed to right {to_right}, to wrong {len(chg) - to_right};"
    f" sign p {sign_p(to_right, len(chg) - to_right):.3f}")

# 1e. SAST votes on record
say("\n1e. Bandit (--sast) votes on record")
for s in corpus:
    sv = [v for v in s["votes"] if v["agent"] == "SAST-BANDIT"]
    if sv:
        t = truth_for(s["artifact"], truths)
        say(f"  {s['created_at'][:10]} {Path(s['artifact'].replace(chr(92), '/')).name:<16} Bandit {sv[0]['label']:<7}"
            f" WaRF {s['decision']} [{s['confidence']}]  corpus label for the file: {t.label if t else 'none'}")

# 1f. The August five-SKEPTIC run in the corpus
say("\n1f. The 12 August SKEPTIC-clone run in the corpus (early stopping on)")
for s in corpus:
    names = [v["agent"] for v in s["votes"]]
    if names and all(n.startswith("SKEPTIC-") for n in names):
        t = truth_for(s["artifact"], truths)
        tl = t.label if t else "none"
        say(f"  {Path(s['artifact'].replace(chr(92), '/')).name:<14} {s['decision']} [{s['confidence']}] after {len(names)} votes;"
            f" corpus label {tl}{'   WRONG' if t and t.label != s['decision'] else ''}")

# ══════════════════════════════════════════════════════════════════════════════════════════════
say("\n" + "=" * 104)
say("2. The 12-file persona experiment: 'harder to fool' (uniform weights, early stopping as in a review)")
say("=" * 104)
home = EXP
pools = {}
for prof in ("persona_v3", "h2h_auditor5", "h2h_skeptic5"):
    pool = load_pool(home, prof)
    items = sorted(pool.items())
    rows = []
    for a, s in items:
        t = truth_for(a, truths)
        x = t.x_star if t else s["oracle"]["x_star"]
        d, conf, lam, k = uniform_replay(s)
        rows.append((Path(a.replace("\\", "/")).name, x, d, conf, k, s))
    pools[prof] = rows
    high = [r for r in rows if r[3] == "HIGH"]
    wrong_high = [r for r in high if x_of(r[2]) != r[1]]
    right = sum(x_of(r[2]) == r[1] for r in rows)
    say(f"  {prof:<13} right {pct(right, len(rows)):<14} HIGH {len(high):>2}, wrong at HIGH {len(wrong_high)}"
        + (f" ({', '.join(r[0] + ' ' + r[2] for r in wrong_high)})" if wrong_high else "")
        + f"; agent calls with early stopping {sum(r[4] for r in rows)} of {5 * len(rows)}")
    say(f"  {'':<13} by band: " + ", ".join(
        f"{k} {pct(sum(x_of(r[2]) == r[1] for r in rows if r[3] == k), sum(1 for r in rows if r[3] == k))}"
        for k in ("LOW", "MEDIUM", "HIGH")))
wh = {p: sum(1 for r in rows if r[3] == "HIGH" and x_of(r[2]) != r[1]) for p, rows in pools.items()}
n12 = len(pools["persona_v3"])
say(f"  wrong-at-HIGH, mixed panel vs five SKEPTICs: {wh['persona_v3']}/{n12} vs {wh['h2h_skeptic5']}/{n12},"
    f" Fisher p {fisher(wh['persona_v3'], n12 - wh['persona_v3'], wh['h2h_skeptic5'], n12 - wh['h2h_skeptic5']):.2f}")
hp = {p: [r for r in rows if r[3] == "HIGH"] for p, rows in pools.items()}
say(f"  wrong among HIGH verdicts: mixed {sum(x_of(r[2]) != r[1] for r in hp['persona_v3'])}/{len(hp['persona_v3'])},"
    f" five AUDITORs {sum(x_of(r[2]) != r[1] for r in hp['h2h_auditor5'])}/{len(hp['h2h_auditor5'])},"
    f" five SKEPTICs {sum(x_of(r[2]) != r[1] for r in hp['h2h_skeptic5'])}/{len(hp['h2h_skeptic5'])}")
# single agents of the mixed panel on the same files
say("  single agents of the mixed panel on the same 12 files (every agent voted):")
for name in ("AUDITOR", "ADVOCATE", "SKEPTIC", "TEST-FOCUSED", "BOUNDARY"):
    pairs = [(next(v["vote"] for v in r[5]["votes"] if v["agent"] == name), r[1]) for r in pools["persona_v3"]]
    say(f"    {name:<13} right {pct(sum(p == t for p, t in pairs), len(pairs))}, wrong {sum(p != t for p, t in pairs)}"
        f" (a single agent never reaches HIGH: |lambda| <= {abs(LLR_REJECT):.3f} < {abs(B):.3f})")

# ══════════════════════════════════════════════════════════════════════════════════════════════
say("\n" + "=" * 104)
say("3. Jev on 100 gismo6 commits (git-history labels: REJECT = later fixed), one agent vs WaRF's default review")
say("=" * 104)
one = {s["jev"]["commit"]: s for s in read(EXP / "jev-five" / "sessions_one.jsonl")}
std = {s["jev"]["commit"]: s for s in read(EXP / "jev-five" / "sessions_standard.jsonl")}
feat = {f["commit"]: f for f in read(EXP / "jev-five" / "verify" / "refute" / "features.jsonl")}
commits = sorted(one)
assert set(commits) == set(std) == set(feat)
truth = {c: x_of(one[c]["jev"]["label"]) for c in commits}
p1 = {c: one[c]["jev"]["round1"]["JEV"]["p_reject"] for c in commits}
v1 = {c: one[c]["votes"][0]["vote"] for c in commits}
dW = {c: x_of(std[c]["decision"]) for c in commits}
cW = {c: std[c]["confidence"] for c in commits}
nW = {c: len(std[c]["votes"]) for c in commits}
added = {c: feat[c]["added"] for c in commits}
fixed = [c for c in commits if truth[c] == -1]
say(f"  {len(commits)} commits, {len(fixed)} later fixed")

# 3a. decisions
b = sum(1 for c in commits if dW[c] == truth[c] != v1[c])
cc = sum(1 for c in commits if v1[c] == truth[c] != dW[c])
say("\n3a. Decisions")
say(f"  one Jev agent: REJECT {sum(v == -1 for v in v1.values())}, right {sum(v1[c] == truth[c] for c in commits)},"
    f" balanced accuracy {bal([(v1[c], truth[c]) for c in commits]):.3f}")
say(f"  WaRF default:  REJECT {sum(v == -1 for v in dW.values())}, right {sum(dW[c] == truth[c] for c in commits)},"
    f" balanced accuracy {bal([(dW[c], truth[c]) for c in commits]):.3f}")
d, lo, hi = boot_diff(commits, lambda s: bal([(dW[c], truth[c]) for c in s]), lambda s: bal([(v1[c], truth[c]) for c in s]),
                      strata=lambda c: truth[c])
say(f"  WaRF minus one agent, balanced accuracy {d:+.3f} [{lo:+.3f}, {hi:+.3f}] (bootstrap within label);"
    f" exact McNemar on right/wrong: WaRF-only {b}, agent-only {cc}, p {sign_p(b, cc):.2f}")

# 3b. confidence bands
say("\n3b. Does WaRF's confidence track accuracy here? (independent labels, uniform priors, nothing learned)")
rowsb = []
for band in ("LOW", "MEDIUM", "HIGH"):
    cs = [c for c in commits if cW[c] == band]
    k = sum(dW[c] == truth[c] for c in cs)
    dec = collections.Counter(std[c]["decision"] for c in cs)
    rowsb.append((len(cs), k))
    say(f"  {band:<7} n {len(cs):>3} ({dict(dec)})  right {pct(k, len(cs)) if cs else '-'} {ci_str(k, len(cs)) if cs else ''}")
say(f"  exact trend test LOW < MEDIUM < HIGH: one-sided p {trend_exact(rowsb):.3f}")
# the same for one Jev agent's own confidence |p - 0.5|, in terciles
conf1 = sorted(commits, key=lambda c: abs(p1[c] - 0.5))
ter = [conf1[:33], conf1[33:66], conf1[66:]]
rows1 = []
for name, cs in zip(("low |p-0.5|", "mid |p-0.5|", "high |p-0.5|"), ter):
    k = sum(v1[c] == truth[c] for c in cs)
    rows1.append((len(cs), k))
    say(f"  one Jev agent, {name:<13} n {len(cs)}  right {pct(k, len(cs))} {ci_str(k, len(cs))}"
        f"  |p-0.5| {min(abs(p1[c] - 0.5) for c in cs):.2f}..{max(abs(p1[c] - 0.5) for c in cs):.2f}")
say(f"  exact trend test for the single agent's own confidence: one-sided p {trend_exact(rows1):.3f}")

# 3c. The CI gate at a matched block rate
say("\n3c. The CI gate: '--fail-on HIGH' against a single-agent threshold that blocks as many commits")
blockW = [c for c in commits if dW[c] == -1 and cW[c] == "HIGH"]
nb = len(blockW)
t1 = sorted((p1[c] for c in commits), reverse=True)[nb - 1]
block1 = [c for c in commits if p1[c] >= t1]
ta = sorted((added[c] for c in commits), reverse=True)[nb - 1]
blockA = [c for c in commits if added[c] >= ta]


def prec(bl, s=None):
    s = commits if s is None else s
    sset = s
    blk = [c for c in sset if c in bl]
    return sum(truth[c] == -1 for c in blk) / len(blk)


for name, bl in (("WaRF REJECT [HIGH]", blockW), (f"one Jev agent, p(REJECT) >= {t1:.2f}", block1),
                 (f"added lines >= {ta}", blockA)):
    k = sum(truth[c] == -1 for c in bl)
    say(f"  {name:<34} blocks {len(bl):>2}: later fixed {pct(k, len(bl)):<12} {ci_str(k, len(bl))};"
        f" recall {k}/{len(fixed)}")
sW, s1 = set(blockW), set(block1)
d, lo, hi = boot_diff(commits, lambda s: prec(sW, s), lambda s: prec(s1, s))
say(f"  precision, WaRF minus one agent: {d:+.3f} [{lo:+.3f}, {hi:+.3f}] (bootstrap over commits, thresholds fixed);"
    f" overlap of the two blocked sets {len(sW & s1)}")
say(f"  calls: WaRF {sum(nW.values()) / len(commits):.2f} per commit (SPRT stopped {sum(1 for c in commits if std[c]['sprt_fired'])}),"
    f" one agent 1.00; Jev cost ${sum(std[c]['jev']['cost'] for c in commits):.4f} vs ${sum(one[c]['jev']['cost'] for c in commits):.4f};"
    f" tokens {sum(std[c]['total_tokens_in'] + std[c]['total_tokens_out'] for c in commits)} vs "
    f"{sum(one[c]['total_tokens_in'] + one[c]['total_tokens_out'] for c in commits)}")
k_wrong_high = sum(1 for c in blockW if truth[c] == 1)
nf = len(commits) - len(fixed)
say(f"  HIGH REJECT on a never-fixed change: {pct(k_wrong_high, nf)} of never-fixed {ci_str(k_wrong_high, nf)}"
    f" (Wald's bound assumed 10%); share of HIGH REJECTs that were never fixed {pct(k_wrong_high, nb)}")
# agreement among the five seats: how many unanimous
unan = collections.Counter(sum(v["vote"] == -1 for v in std[c]["votes"]) for c in commits)
say(f"  REJECT votes among the agents asked (WaRF default): {dict(sorted(unan.items()))}")

# ══════════════════════════════════════════════════════════════════════════════════════════════
say("\n" + "=" * 104)
say("4. Five Laya agents (debate on, early stopping off): confidence bands of WaRF's final verdict")
say("=" * 104)
lf = {s["five"]["commit"]: s for s in read(EXP / "laya-five" / "sessions.jsonl")}
rowsl = []
for band in ("LOW", "MEDIUM", "HIGH"):
    cs = [c for c in lf if lf[c]["confidence"] == band]
    k = sum(x_of(lf[c]["decision"]) == x_of(lf[c]["five"]["label"]) for c in cs)
    rowsl.append((len(cs), k))
    say(f"  {band:<7} n {len(cs):>3} ({dict(collections.Counter(lf[c]['decision'] for c in cs))})  right "
        f"{pct(k, len(cs)) if cs else '-'} {ci_str(k, len(cs)) if cs else ''}")
say(f"  exact trend test LOW < MEDIUM < HIGH: one-sided p {trend_exact(rowsl):.3f}")

# ══════════════════════════════════════════════════════════════════════════════════════════════
say("\n" + "=" * 104)
say("5. WaRF's rule over three DIFFERENT models (stored votes: blinded Claude, one Jev, one Laya; one seat each)")
say("=" * 104)
sel = {s["commit"]: s for s in read(EXP / "laya-five" / "selection.jsonl")}
assert set(sel) == set(commits)
pc = {c: sel[c]["p_claude"] for c in commits}
pl = {c: sel[c]["p_single_laya"] for c in commits}
vl = {c: -1 if pl[c] >= 0.5 else 1 for c in commits}
say(f"  Laya's vote is its argmax: REJECT on {sum(v == -1 for v in vl.values())} of 100, so its seat always adds +0.49 to lambda")


def warf_rule(seats, c, omegas):
    """WaRF's review on stored votes: heaviest first, SPRT with early stopping, else synthesis."""
    order = sorted(seats, key=lambda s: -omegas[s])
    lam = 0.0
    for s in order:
        v = seats[s][c]
        lam += omegas[s] * (LLR_APPROVE if v == 1 else LLR_REJECT)
        if lam >= A:
            return 1, "HIGH"
        if lam <= B:
            return -1, "HIGH"
    dec, conf, _ = synthesis([seats[s][c] for s in order], [omegas[s] for s in order], sel[c]["domain"])
    return x_of(dec.value), conf.value


for cname, thr in (("p >= 0.5", 0.5), ("top quarter", sorted(pc.values(), reverse=True)[24])):
    vc = {c: -1 if pc[c] >= thr else 1 for c in commits}
    seats = {"CLAUDE": vc, "JEV": v1, "LAYA": vl}
    uni = {s: 0.5 for s in seats}
    dU = {c: warf_rule(seats, c, uni)[0] for c in commits}
    # leave-one-out learned omega: (1 + right) / (2 + n) on the other 99 commits, gamma 1
    dL = {}
    for c in commits:
        om = {s: (1 + sum(seats[s][o] == truth[o] for o in commits if o != c)) / (2 + len(commits) - 1) for s in seats}
        dL[c] = warf_rule(seats, c, om)[0]
    say(f"  Claude's vote = REJECT if {cname} (REJECT on {sum(v == -1 for v in vc.values())}):")
    for name, dd in (("Claude alone", vc), ("Jev alone", v1), ("WaRF rule, uniform omega", dU),
                     ("WaRF rule, leave-one-out omega", dL)):
        say(f"    {name:<32} REJECT {sum(v == -1 for v in dd.values()):>3}  balanced accuracy"
            f" {bal([(dd[c], truth[c]) for c in commits]):.3f}")
    b = sum(1 for c in commits if dU[c] == truth[c] != vc[c])
    c2 = sum(1 for c in commits if vc[c] == truth[c] != dU[c])
    d, lo, hi = boot_diff(commits, lambda s: bal([(dU[c], truth[c]) for c in s]), lambda s: bal([(vc[c], truth[c]) for c in s]),
                          strata=lambda c: truth[c])
    say(f"    WaRF rule minus Claude alone: {d:+.3f} [{lo:+.3f}, {hi:+.3f}]; McNemar WaRF-only {b} / Claude-only {c2},"
        f" p {sign_p(b, c2):.2f}; decisions changed by learned omega: {sum(dU[c] != dL[c] for c in commits)}")

# ══════════════════════════════════════════════════════════════════════════════════════════════
say("\n" + "=" * 104)
say("6. The SPRT's vote model: measured P1 = P(APPROVE | good), P0 = P(APPROVE | bad), pooled over seats")
say("=" * 104)
say(f"  assumed: P1 0.80, P0 0.30 -> LLR APPROVE {LLR_APPROVE:+.3f}, REJECT {LLR_REJECT:+.3f}")


def llr_line(name, pairs):
    """pairs: (vote, truth) over all seats and items; Laplace-smoothed rates."""
    g = [v for v, t in pairs if t == 1]
    bd = [v for v, t in pairs if t == -1]
    p1 = (sum(v == 1 for v in g) + 1) / (len(g) + 2)
    p0 = (sum(v == 1 for v in bd) + 1) / (len(bd) + 2)
    say(f"  {name:<44} votes {len(pairs):>4}: P1 {p1:.3f}  P0 {p0:.3f}  -> LLR APPROVE {math.log(p1 / p0):+.3f},"
        f" REJECT {math.log((1 - p1) / (1 - p0)):+.3f}")


llr_line("Claude Haiku, persona_v3, 12 files", [(v["vote"], r[1]) for r in pools["persona_v3"] for v in r[5]["votes"]])
five = {s["jev"]["commit"]: s for s in read(EXP / "jev-five" / "sessions_five.jsonl")}
llr_line("Jev, five personas, Round 1, 100 commits", [(v["vote"], truth[c]) for c in commits for v in five[c]["votes"]])
llr_line("Laya, five personas, Round 1, 100 commits",
         [(v["vote"], x_of(lf[c]["five"]["label"])) for c in lf for v in lf[c]["votes"]])
llr_line("Jev, one agent, 100 commits", [(v1[c], truth[c]) for c in commits])

# ══════════════════════════════════════════════════════════════════════════════════════════════
say("\n" + "=" * 104)
say("7. How often each routing-table row fires: (decision, confidence) in every log")
say("=" * 104)
for p in (ROOT / ".warf" / "sessions.jsonl", EXP / "sessions.jsonl", EXP / "jev-five" / "sessions_standard.jsonl",
          EXP / "jev-five" / "sessions_five.jsonl", EXP / "laya-five" / "sessions.jsonl"):
    rows = read(p)
    cn = collections.Counter(f"{s['decision']} {s['confidence']}" for s in rows)
    say(f"  {str(p.relative_to(ROOT)):<46} {len(rows):>4}: " + ", ".join(f"{k} {v}" for k, v in sorted(cn.items())))
    for s in rows:
        if s["decision"] == "APPROVE" and s["confidence"] == "HIGH":
            t = truth_for(s["artifact"], truths)
            say(f"    APPROVE HIGH: profile {s.get('profile')}, {Path(s['artifact'].replace(chr(92), '/')).name},"
                f" stored label {(s.get('oracle') or {}).get('x_star_label')}, corpus label now {t.label if t else 'none'}")

say("\n" + "=" * 104)
say("8. Each persona seat alone (Round 1) against WaRF's decision, balanced accuracy on the 100 commits")
say("=" * 104)
for tag, sessions, lab_of, warf_dec in (
        ("Jev", list(five.values()), lambda s: x_of(s["jev"]["label"]), {c: dW[c] for c in commits}),
        ("Laya", list(lf.values()), lambda s: x_of(s["five"]["label"]), {c: x_of(lf[c]["decision"]) for c in lf})):
    parts = []
    for name in ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY"):
        pr_ = [(next(v["vote"] for v in s["votes"] if v["agent"] == name), lab_of(s)) for s in sessions]
        parts.append(f"{name} {bal(pr_):.2f} ({sum(p == -1 for p, _ in pr_)} REJ)")
    key = "jev" if tag == "Jev" else "five"
    wd = bal([(warf_dec[s[key]["commit"]], lab_of(s)) for s in sessions])
    say(f"  {tag:<5} " + ", ".join(parts) + f";  WaRF {'default' if tag == 'Jev' else 'final'} {wd:.2f}")

(HERE / "claims_evidence.log").write_text("\n".join(out) + "\n", encoding="utf-8")
