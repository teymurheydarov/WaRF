"""Would WaRF's own mechanism keep the gain of a mixed-model panel?

Three seats on the 100 gismo6 commits of ../../laya-five/selection.jsonl (50 later fixed, label
REJECT; 50 never fixed, label APPROVE; matched in pairs of similar size):
    JEV     single Jev agent, ../../jev-five/sessions_one.jsonl, p_reject
    LAYA    single Laya agent, selection.jsonl p_single_laya
    CLAUDE  blinded Claude Opus, selection.jsonl p_claude
A seat votes REJECT when its p > 0.5.

Stored outputs only: no model or service is asked. WaRF's decision rules are warf/engine.py's own
functions (sprt_update, synthesis, bayesian_update, omega_from_beta, apply_decay) and constants
(A, B, LLR_APPROVE, LLR_REJECT, THETA), driven the way warf/orchestrator.py's run_review and
apply_oracle drive them (agents heaviest omega first, ties in profile order; Round 1 only, no debate).
The probability variant (d) needs a per-vote LLR, which engine.py does not have: sprt_update_llr and
synthesis_llr below mirror sprt_update and synthesis line for line and are checked against them.
Pure Python: numpy's BLAS crashes in gs\\cf\\python.exe.
Writes mixed_panel.log and mixed_panel.json next to this file and nothing else.

    PYTHONIOENCODING=utf-8 python -B .warf-experiments/why-warf/mixed/mixed_panel.py
"""
import itertools
import json
import math
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import NormalDist, median

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
ROOT = EXP.parent
sys.path.insert(0, str(ROOT))
from warf.engine import (A, B, DOMAINS, LLR_APPROVE, LLR_REJECT, THETA, Confidence,  # noqa: E402
                         Decision, SPRTState, apply_decay, bayesian_update, omega_ci,
                         omega_from_beta, sprt_update, synthesis)
from warf.state import ORACLE_TIERS  # noqa: E402

T0 = time.time()
GAMMA = ORACLE_TIERS["DEVELOPER"]
SEATS = ("JEV", "LAYA", "CLAUDE")
ORDERS = list(itertools.permutations(SEATS))
N01 = NormalDist()
OUT, RES = [], {}


def say(s=""):
    OUT.append(s)
    print(s, flush=True)


def head(s):
    say()
    say("=" * 110)
    say(s)
    say("=" * 110)


def jl(path):
    return [json.loads(line) for line in path.open(encoding="utf-8")]


# ------------------------------------------------------------------------------------------- data
sel = jl(EXP / "laya-five" / "selection.jsonl")
one = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_one.jsonl")}
std = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_standard.jsonl")}
ids = [s["id"] for s in sel]
n = len(ids)
y = [s["label"] == "REJECT" for s in sel]            # True: later fixed, REJECT is right
XSTAR = [-1 if t else 1 for t in y]                  # the developer oracle's x*
dom = [s["domain"] for s in sel]
P = {"JEV": [one[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids],
     "LAYA": [s["p_single_laya"] for s in sel],
     "CLAUDE": [s["p_claude"] for s in sel]}
assert all(one[i]["jev"]["label"] == s["label"] for i, s in zip(ids, sel))
assert all(y[2 * k] and not y[2 * k + 1] for k in range(n // 2)), "rows 2k, 2k+1 are a matched pair"

want = {s["commit"] for s in sel}
when = {}
with (EXP / "laya-sweep" / "plan.jsonl").open(encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if r["sha"] in want:
            when[r["sha"]] = datetime.fromisoformat(r["date"].replace("Z", "+00:00"))
assert len(when) == len(want)
T = [when[s["commit"]] for s in sel]
TIME_ORDER = sorted(range(n), key=lambda i: (T[i], ids[i]))


# ---------------------------------------------------------------------------------------- metrics
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


def bal(rej, pos):
    """Balanced accuracy of REJECT decisions (True = REJECT) against later-fixed labels."""
    n1 = sum(pos)
    tp = sum(1 for r, t in zip(rej, pos) if r and t)
    tn = sum(1 for r, t in zip(rej, pos) if not r and not t)
    return (tp / n1 + tn / (len(pos) - n1)) / 2


PIDX = [i for i in range(n) if y[i]]
NIDX = [i for i in range(n) if not y[i]]
_rng = random.Random(5)
BOOT = [[_rng.choice(PIDX) for _ in PIDX] + [_rng.choice(NIDX) for _ in NIDX] for _ in range(2000)]
YB = [[y[i] for i in idx] for idx in BOOT]
ALL = list(range(n))


def interval(stat, boot=None, yb=None):
    """stat(idx, labels) on all commits, and its 95 % interval over resamples within each label."""
    boot, yb = boot or BOOT, yb or YB
    d = sorted(stat(idx, yy) for idx, yy in zip(boot, yb))
    return [stat(ALL, y), d[int(0.025 * len(d))], d[int(0.975 * len(d)) - 1]]


def ci_auc(s):
    return interval(lambda idx, yy: auc([s[i] for i in idx], yy))


def ci_ba(r):
    return interval(lambda idx, yy: bal([r[i] for i in idx], yy))


def vs_auc(s1, s2):
    return interval(lambda idx, yy: auc([s1[i] for i in idx], yy) - auc([s2[i] for i in idx], yy))


def vs_ba(r1, r2):
    return interval(lambda idx, yy: bal([r1[i] for i in idx], yy) - bal([r2[i] for i in idx], yy))


def vs_mean_auc(s, members):
    return interval(lambda idx, yy: auc([s[i] for i in idx], yy)
                    - sum(auc([m[i] for i in idx], yy) for m in members) / len(members))


def vs_mean_ba(r, members):
    return interval(lambda idx, yy: bal([r[i] for i in idx], yy)
                    - sum(bal([m[i] for i in idx], yy) for m in members) / len(members))


def sign_p(b, c):
    """Exact two-sided sign test, b against c discordant items."""
    k = b + c
    if k == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(k, i) for i in range(min(b, c) + 1)) / 2 ** k)


def mcnemar(r1, r2):
    """Commits r1 decides right and r2 wrong, the reverse, and the exact sign test on them."""
    b = sum(1 for i in range(n) if r1[i] == y[i] and r2[i] != y[i])
    c = sum(1 for i in range(n) if r1[i] != y[i] and r2[i] == y[i])
    return b, c, sign_p(b, c)


def fmt(t, d=3):
    return f"{t[0]:+.{d}f} [{t[1]:+.{d}f}, {t[2]:+.{d}f}]"


def fmt0(t, d=3):
    return f"{t[0]:.{d}f} [{t[1]:.{d}f}, {t[2]:.{d}f}]"


def logit(p):
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


def sigmoid(z):
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


def zavg(members):
    """why_five.py's logit average: each member's logit scaled to unit SD over all commits, equal weights."""
    zs = []
    for m in members:
        mu = sum(m) / len(m)
        sd = math.sqrt(sum((v - mu) ** 2 for v in m) / len(m))
        zs.append([(v - mu) / sd for v in m])
    return [sum(col) / len(col) for col in zip(*zs)]


# ------------------------------------------------------------------------- WaRF's review, Round 1
def sprt_update_llr(state, llr, omega):
    """engine.sprt_update with the step log-likelihood ratio passed in instead of chosen by the vote."""
    new_lambda = state.lambda_ + omega * llr
    new_state = SPRTState(lambda_=new_lambda, k=state.k + 1)
    if new_lambda >= A:
        return new_state, Decision.APPROVE
    if new_lambda <= B:
        return new_state, Decision.REJECT
    return new_state, None


def synthesis_llr(llrs, weights, domain):
    """engine.synthesis with each agent's APPROVE log-odds in place of its +1/-1 vote."""
    theta = THETA[domain]
    normalised = sum(w * v for w, v in zip(weights, llrs)) / sum(weights)
    margin = abs(normalised - theta)
    decision = Decision.APPROVE if normalised >= theta else Decision.REJECT
    confidence = Confidence.MEDIUM if margin >= 0.2 else Confidence.LOW
    return decision, confidence, normalised


def review(order, omega, vote, domain, stop="early", llr=None):
    """run_review's Round 1 for one commit. `order` is already heaviest omega first.
    stop: 'early' = WaRF's default (stop at the first boundary crossing);
          'all'   = --no-early-stop (every agent votes, the first crossing is still the verdict);
          'none'  = no SPRT verdict at all: every agent votes and the synthesis decides.
    llr: per-seat APPROVE log-odds replacing the fixed LLR (variant d), or None for WaRF as it is.
    Returns (REJECT?, confidence, Lambda, normalised score or None, [(seat, vote, omega)])."""
    state, cast, early = SPRTState(), [], None
    for s in order:
        if early is not None and stop == "early":
            break
        w = omega[s]
        if llr is None:
            state, boundary = sprt_update(state, vote[s], w)
        else:
            state, boundary = sprt_update_llr(state, llr[s], w)
        cast.append((s, vote[s], w))
        if boundary is not None and early is None and stop != "none":
            early = boundary
    if early is not None:
        return early == Decision.REJECT, Confidence.HIGH, state.lambda_, None, cast
    ws = [w for _, _, w in cast]
    if llr is None:
        dec, conf, norm = synthesis([v for _, v, _ in cast], ws, domain)
    else:
        dec, conf, norm = synthesis_llr([llr[s] for s, _, _ in cast], ws, domain)
    return dec == Decision.REJECT, conf, state.lambda_, norm, cast


# The mirrors agree with engine.py wherever both apply.
for lam0 in (-2.2, -1.0, 0.0, 1.0, 2.5):
    for v in (1, -1):
        for w in (0.1, 0.5, 0.9, 1.0):
            s1, b1 = sprt_update(SPRTState(lam0, 2), v, w)
            s2, b2 = sprt_update_llr(SPRTState(lam0, 2), LLR_APPROVE if v == 1 else LLR_REJECT, w)
            assert (s1.lambda_, s1.k, b1) == (s2.lambda_, s2.k, b2)
for vs in itertools.product((1, -1), repeat=3):
    for ws in ((0.5, 0.5, 0.5), (0.7, 0.4, 0.55), (0.9, 0.3, 0.3)):
        for d in DOMAINS:
            assert synthesis(list(vs), list(ws), d) == synthesis_llr(list(vs), list(ws), d)


def uniform_panel(seats, votes, stop="early", llr=None):
    """Every commit reviewed with all omegas at 0.5 (WaRF's uniform prior); `seats` is the profile order."""
    om = {s: 0.5 for s in seats}
    rej, score, k, high = [], [], [], 0
    for i in range(n):
        r, conf, lam, _, cast = review(seats, om, {s: votes[s][i] for s in seats}, dom[i], stop,
                                       None if llr is None else {s: llr[s][i] for s in seats})
        rej.append(r)
        score.append(-lam)
        k.append(len(cast))
        high += conf == Confidence.HIGH
    return {"rej": rej, "score": score, "k": k, "high": high}


def stream_run(stream, profile, votes, oracle, *, mode="panel", learn=True, decay=False, stop="early",
               llr=None):
    """Review the commits in `stream` one after another as WaRF would, then label each one.
    Effective omega per seat and domain (apply_decay over the weeks since the seat's last update when
    decay=True, reviews dated at commit time), seats asked heaviest first (stable sort: ties keep the
    profile order), then apply_oracle: bayesian_update with gamma = DEVELOPER for every seat that voted.
    mode: 'panel'        WaRF's review;
          'route_shadow' every seat votes and learns; the decision is the vote of the heaviest seat;
          'route_only'   --max-agents 1: only the heaviest seat is asked, and only it learns.
    Returns per-commit records (commit index order) and the final (alpha, beta)."""
    al = {s: {d: 1.0 for d in DOMAINS} for s in profile}
    be = {s: {d: 1.0 for d in DOMAINS} for s in profile}
    last = {s: None for s in profile}
    out = [None] * n
    for pos, i in enumerate(stream):
        d = dom[i]
        om = {}
        for s in profile:
            if decay and last[s] is not None:
                weeks = max(0.0, (T[i] - last[s]).total_seconds() / (7 * 24 * 3600))
                a_eff, b_eff = apply_decay(al[s][d], be[s][d], weeks)
                om[s] = a_eff / (a_eff + b_eff)
            else:
                om[s] = omega_from_beta(al[s][d], be[s][d])
        order = sorted(profile, key=lambda s: om[s], reverse=True)
        v_i = {s: votes[s][i] for s in profile}
        l_i = None if llr is None else {s: llr[s][i] for s in profile}
        if mode == "panel":
            rej, conf, lam, norm, cast = review(order, om, v_i, d, stop, l_i)
        elif mode == "route_only":
            rej, conf, lam, norm, cast = review(order[:1], om, v_i, d, stop, l_i)
        elif mode == "route_shadow":
            _, conf, lam, norm, cast = review(order, om, v_i, d, "none", l_i)
            rej = v_i[order[0]] == -1
        else:
            raise ValueError(mode)
        if learn:
            for s, v, _ in cast:
                al[s][d], be[s][d] = bayesian_update(al[s][d], be[s][d], v == oracle[i], GAMMA)
                last[s] = T[i]
        out[i] = {"rej": rej, "conf": conf, "score": -lam, "k": len(cast), "top": order[0],
                  "om": om, "pos": pos}
    return out, al, be


def leader_after(al, be, profile, d="LOGIC"):
    om = {s: omega_from_beta(al[s][d], be[s][d]) for s in profile}
    return sorted(profile, key=lambda s: om[s], reverse=True)[0]


def settle(recs, stream, final):
    """Commits reviewed before the heaviest seat is `final` for good (0: it led throughout)."""
    lead = [recs[i]["top"] for i in stream]
    last_other = max((p for p, s in enumerate(lead) if s != final), default=-1)
    return last_other + 1


# ------------------------------------------------------------------------------ out-of-fold calibration
def platt(xs, ts, a=0.0, b=0.0):
    """Logistic regression of the label on one feature (Newton's method)."""
    for _ in range(200):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, t in zip(xs, ts):
            q = sigmoid(a + b * x)
            r, w = q - t, q * (1 - q)
            g0 += r
            g1 += r * x
            h00 += w
            h01 += w * x
            h11 += w * x * x
        det = h00 * h11 - h01 * h01
        da = (h11 * g0 - h01 * g1) / det
        db = (h00 * g1 - h01 * g0) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-10:
            return a, b
    raise RuntimeError("Platt fit did not converge")


TY = [1.0 if t else 0.0 for t in y]
FOLDS = [[i for i in range(n) if i // 2 != k] for k in range(n // 2)]


def lopo(p):
    """Calibrated REJECT log-odds a + b*logit(p), (a, b) fitted on the other 49 matched pairs."""
    x = [logit(v) for v in p]
    a0, b0 = platt(x, TY)
    out = [0.0] * n
    for k, tr in enumerate(FOLDS):
        a, b = platt([x[i] for i in tr], [TY[i] for i in tr], a0, b0)
        for i in (2 * k, 2 * k + 1):
            out[i] = a + b * x[i]
    return out, (a0, b0)


def seat_views(Pd):
    """Votes, APPROVE log-odds and calibrated versions of every seat in Pd."""
    V = {s: [-1 if p > 0.5 else 1 for p in Pd[s]] for s in Pd}
    LR = {s: [-logit(p) for p in Pd[s]] for s in Pd}
    cal = {s: lopo(Pd[s]) for s in Pd}
    LC = {s: [-z for z in cal[s][0]] for s in Pd}
    VC = {s: [-1 if z > 0 else 1 for z in cal[s][0]] for s in Pd}
    return V, LR, LC, VC, {s: cal[s][1] for s in Pd}


V, LR, LC, VC, CALFIT = seat_views(P)
REJ = {s: [v == -1 for v in V[s]] for s in SEATS}
REJC = {s: [v == -1 for v in VC[s]] for s in SEATS}


def compare(name, rej, score, seat_rej, key, seat_score=None, members_note="votes at p > 0.5"):
    """Print and store: BA and AUC of a variant, and paired differences against every seat and the mean member."""
    seat_score = seat_score or P
    b = ci_ba(rej)
    a = ci_auc(score) if score is not None else None
    rec = {"ba": b, "auc": a, "rejects": sum(rej),
           "rejects_later_fixed": sum(1 for r, t in zip(rej, y) if r and t), "vs": {}}
    say(f"\n  {name}")
    say(f"    REJECT {sum(rej)} of {n} ({rec['rejects_later_fixed']} later fixed); "
        f"balanced accuracy {fmt0(b)}" + (f"; AUC {fmt0(a)}" if a else ""))
    for s in SEATS:
        db = vs_ba(rej, seat_rej[s])
        bb, cc, pp = mcnemar(rej, seat_rej[s])
        line = f"    vs {s:<7} decision {fmt(db)}  right only here / only {s}: {bb:>2} / {cc:>2}, sign p {pp:.3f}"
        r2 = {"d_ba": db, "only_panel": bb, "only_seat": cc, "sign_p": pp}
        if score is not None:
            da = vs_auc(score, seat_score[s])
            line += f"   AUC {fmt(da)}"
            r2["d_auc"] = da
        say(line)
        rec["vs"][s] = r2
    mb = vs_mean_ba(rej, [seat_rej[s] for s in SEATS])
    line = f"    vs mean member  decision {fmt(mb)}"
    rec["vs"]["mean"] = {"d_ba": mb}
    if score is not None:
        ma = vs_mean_auc(score, [seat_score[s] for s in SEATS])
        line += f"   AUC {fmt(ma)}"
        rec["vs"]["mean"]["d_auc"] = ma
    say(line + f"   (members' decisions: {members_note})")
    RES[key] = rec
    return rec


# ============================================================================================== 0
head("0. Data, seats, and a check of the simulator against WaRF's own stored reviews")
say(f"  {n} commits, {sum(y)} later fixed (REJECT), {n - sum(y)} never fixed (APPROVE); "
    f"domains {dict((d, dom.count(d)) for d in DOMAINS if d in dom)}; "
    f"commit dates {T[TIME_ORDER[0]].date()} to {T[TIME_ORDER[-1]].date()}")
say(f"  engine.py: A {A:+.3f}, B {B:+.3f}, LLR_APPROVE {LLR_APPROVE:+.3f}, LLR_REJECT {LLR_REJECT:+.3f}, "
    f"THETA {THETA}, oracle gamma {GAMMA}")
say(f"\n  {'seat':<8} {'REJECT votes':>12} {'of later fixed':>15} {'of never fixed':>15} {'vote bal.acc':>13} "
    f"{'AUC of p':>20} {'p range':>13}  Platt a, b (all data)")
RES["seats"] = {}
for s in SEATS:
    rj = REJ[s]
    tp = sum(1 for r, t in zip(rj, y) if r and t)
    a = ci_auc(P[s])
    say(f"  {s:<8} {sum(rj):>12} {tp:>15} {sum(rj) - tp:>15} {bal(rj, y):>13.3f} {fmt0(a):>20} "
        f"{min(P[s]):>6.2f}-{max(P[s]):.2f}  {CALFIT[s][0]:+.2f}, {CALFIT[s][1]:+.2f}")
    RES["seats"][s] = {"reject_votes": sum(rj), "reject_votes_later_fixed": tp, "vote_ba": bal(rj, y),
                       "auc": a, "platt": CALFIT[s],
                       "calibrated_reject_votes": sum(REJC[s]),
                       "calibrated_vote_ba": bal(REJC[s], y)}
say("  calibrated votes (out-of-fold Platt p > 0.5): " + ", ".join(
    f"{s} {sum(REJC[s])} REJECT, bal.acc {bal(REJC[s], y):.3f}" for s in SEATS))
za = zavg([[logit(p) for p in P[s]] for s in SEATS])
RES["zavg_auc"] = ci_auc(za)
say(f"  reference, why_five.py's logit average of the three: AUC {fmt0(RES['zavg_auc'])}")
def _corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb)


def _within(x):
    m1 = sum(v for v, t in zip(x, y) if t) / sum(y)
    m0 = sum(v for v, t in zip(x, y) if not t) / (n - sum(y))
    return [v - (m1 if t else m0) for v, t in zip(x, y)]


RES["pairs"] = {}
for s1, s2 in itertools.combinations(SEATS, 2):
    dis = sum(V[s1][i] != V[s2][i] for i in range(n)) / n
    l1, l2 = [logit(p) for p in P[s1]], [logit(p) for p in P[s2]]
    r_all, r_in = _corr(l1, l2), _corr(_within(l1), _within(l2))
    say(f"  {s1}-{s2}: votes disagree on {dis:.2f} of commits"
        + ("  (under 0.15: a clone pair by SPECIFICATION 3.1.2)" if dis < 0.15 else "")
        + f"; correlation of logit p {r_all:+.2f}, within label {r_in:+.2f}")
    RES["pairs"][f"{s1}-{s2}"] = {"disagree": dis, "r": r_all, "r_within": r_in}

ok_one = ok_std = 0
for i in ids:
    for store, tag in ((one, "one"), (std, "std")):
        r = store[i]
        vs = r["votes"]
        rj, conf, lam, _, cast = review([v["agent"] for v in vs], {v["agent"]: v["omega"] for v in vs},
                                        {v["agent"]: v["vote"] for v in vs}, r["domain"], "early")
        same = (("REJECT" if rj else "APPROVE") == r["decision"] and conf.value == r["confidence"]
                and abs(lam - float(r["sprt_lambda"])) < 1e-3 and len(cast) == len(vs))
        if tag == "one":
            ok_one += same
        else:
            ok_std += same
say(f"\n  simulator replaying WaRF's stored reviews from their own votes and omegas: single Jev agent "
    f"{ok_one}/{n} identical (decision, confidence, Lambda, agents asked); WaRF's default five-agent "
    f"review on Jev, early stopping on, {ok_std}/{n} identical")
RES["replay_check"] = {"one": ok_one, "standard": ok_std}
assert ok_one == n and ok_std == n

# ============================================================================================== a
head("(a) WaRF as it is: uniform omega 0.5, fixed LLRs, early stopping on, every seat order")
say(f"  Reach of the SPRT with three seats at omega 0.5: all three REJECT gives Lambda "
    f"{3 * 0.5 * LLR_REJECT:+.3f} (B = {B:+.3f}); all three APPROVE {3 * 0.5 * LLR_APPROVE:+.3f} (A = {A:+.3f}).")
say("  Neither boundary can be reached, so every review ends in the synthesis (a majority of three).")
runs = {}
for order in ORDERS:
    for stop in ("early", "all", "none"):
        runs[(order, stop)] = uniform_panel(order, V, stop)
base = runs[(ORDERS[0], "early")]
same_all = all(r["rej"] == base["rej"] and r["score"] == base["score"] for r in runs.values())
bas = [bal(r["rej"], y) for (o, st), r in runs.items() if st == "early"]
aucs = [auc(r["score"], y) for (o, st), r in runs.items() if st == "early"]
highs = sum(r["high"] for r in runs.values())
say(f"  6 orders x 3 stopping rules: identical decisions and Lambda in all 18 runs: {same_all}; "
    f"SPRT verdicts (HIGH) {highs}; agents asked per review {sorted(set(k for r in runs.values() for k in r['k']))}")
say(f"  balanced accuracy over the 6 orders: mean {sum(bas) / 6:.3f}, range {min(bas):.3f} to {max(bas):.3f}; "
    f"AUC of -Lambda: mean {sum(aucs) / 6:.3f}, range {min(aucs):.3f} to {max(aucs):.3f}")
nrej = [sum(V[s][i] == -1 for s in SEATS) for i in range(n)]
say("  REJECT votes per commit: " + ", ".join(
    f"{k}: {nrej.count(k)} commits ({sum(1 for i in range(n) if nrej[i] == k and y[i])} later fixed)"
    for k in range(4) if nrej.count(k)))
conf = {}
for i in range(n):
    _, c, _, _, _ = review(list(SEATS), {s: 0.5 for s in SEATS}, {s: V[s][i] for s in SEATS}, dom[i])
    conf[c.value] = conf.get(c.value, [0, 0])
    conf[c.value][0] += 1
    conf[c.value][1] += base["rej"][i] == y[i]
say("  WaRF's confidence: " + ", ".join(f"{c} {v[0]} reviews, {v[1]} right" for c, v in sorted(conf.items())))
RES["a_orders"] = {"identical": same_all, "ba_mean": sum(bas) / 6, "ba_range": [min(bas), max(bas)],
                   "auc_mean": sum(aucs) / 6, "auc_range": [min(aucs), max(aucs)], "sprt_verdicts": highs,
                   "confidence": conf}
compare("(a) WaRF, uniform weights, votes (any order, early stopping on or off)", base["rej"], base["score"],
        REJ, "a_uniform_votes")
cal_runs = [uniform_panel(o, VC, "early") for o in ORDERS]
assert all(r["rej"] == cal_runs[0]["rej"] for r in cal_runs)
compare("(a') diagnostic: the same, but each seat votes with an out-of-fold calibrated threshold "
        "(calibrated p > 0.5)", cal_runs[0]["rej"], cal_runs[0]["score"], REJC, "a_uniform_calibrated_votes",
        members_note="calibrated votes")

# ============================================================================================== b
head("(b) Learned weights, prequential in commit-date order: review with the current omegas, then the label")
say("  Structure: with three seats the weighted vote differs from the majority only if a lone dissenter's")
say("  omega exceeds the other two combined (LOGIC; SECURITY, theta +0.2: a lone REJECT needs 2/3 of their sum).")
say(f"  A REJECT boundary needs the rejecting seats' omegas to sum to {-B / -LLR_REJECT:.3f} with no APPROVE in between;")
say(f"  an APPROVE boundary needs {A / LLR_APPROVE:.3f}, more than three seats at omega < 0.982 can give.")
B_ = {}
for order in ORDERS:
    for name, kw in (("learned", {}), ("learned, decay", {"decay": True}), ("uniform", {"learn": False})):
        B_[(order, name)] = stream_run(TIME_ORDER, order, V, XSTAR, **kw)
for name in ("learned", "learned, decay", "uniform"):
    rs = [B_[(o, name)][0] for o in ORDERS]
    rej = [[r[i]["rej"] for i in range(n)] for r in rs]
    sc = [[r[i]["score"] for i in range(n)] for r in rs]
    hi = [sum(r[i]["conf"] == Confidence.HIGH for i in range(n)) for r in rs]
    bs = [bal(x, y) for x in rej]
    au = [auc(x, y) for x in sc]
    say(f"  {name:<15} 6 tie-break orders: balanced accuracy {min(bs):.3f} to {max(bs):.3f}, "
        f"AUC of -Lambda {min(au):.3f} to {max(au):.3f}, SPRT verdicts {sorted(set(hi))}, "
        f"decisions identical across orders: {all(x == rej[0] for x in rej)}")
L_rec, L_al, L_be = B_[(ORDERS[0], "learned")]
U_rec = B_[(ORDERS[0], "uniform")][0]
D_rec = B_[(ORDERS[0], "learned, decay")][0]
L_rej = [L_rec[i]["rej"] for i in range(n)]
U_rej = [U_rec[i]["rej"] for i in range(n)]
D_rej = [D_rec[i]["rej"] for i in range(n)]
for nm, x in (("learned", L_rej), ("learned, decay", D_rej)):
    ch = [i for i in range(n) if x[i] != U_rej[i]]
    b_, c_, p_ = mcnemar(x, U_rej)
    say(f"  {nm} vs uniform, same order: {len(ch)} decisions differ ({b_} to right, {c_} to wrong), sign p {p_:.3f}"
        + (f"; commits {[ids[i] for i in ch]} ({[dom[i] for i in ch]})" if ch else ""))
say("  omegas after all 100 labels (LOGIC, 95 % interval by omega_ci; SECURITY saw 4 labels):")
for s in SEATS:
    a_, b2 = L_al[s]["LOGIC"], L_be[s]["LOGIC"]
    lo, hi_ = omega_ci(a_, b2)
    say(f"    {s:<7} alpha {a_:>5.1f} beta {b2:>5.1f} omega {a_ / (a_ + b2):.3f} [{lo:.3f}, {hi_:.3f}];  "
        f"SECURITY omega {omega_from_beta(L_al[s]['SECURITY'], L_be[s]['SECURITY']):.3f}")
traj = {}
for cut in (10, 25, 50, 75, 100):
    i = TIME_ORDER[cut - 1]
    traj[cut] = {s: round(L_rec[i]["om"][s], 3) for s in SEATS}
say("  LOGIC omegas when the k-th commit is reviewed: " + "; ".join(
    f"k={k}: " + ", ".join(f"{s} {v:.2f}" for s, v in om.items()) for k, om in traj.items()))
mx = max(max(L_rec[i]["om"].values()) for i in range(n))
mx2 = max(sorted(L_rec[i]["om"].values())[-1] + sorted(L_rec[i]["om"].values())[-2] for i in range(n))
say(f"  largest omega reached {mx:.3f}; largest sum of the two heaviest {mx2:.3f} (REJECT boundary at k=2 needs 1.797)")
L_score = [L_rec[i]["score"] for i in range(n)]
compare("(b) WaRF, learned weights (prequential, commit-date order, early stopping on)", L_rej, L_score, REJ,
        "b_learned_votes")
say(f"    vs uniform weights, same order: AUC of -Lambda {fmt(vs_auc(L_score, base['score']))}")
RES["b_learned_votes"]["vs_uniform_auc"] = vs_auc(L_score, base["score"])
RES["b_learned_votes"]["vs_uniform_decisions"] = mcnemar(L_rej, U_rej)
RES["b_learned_votes"]["final_omega"] = {s: {"alpha": L_al[s]["LOGIC"], "beta": L_be[s]["LOGIC"],
                                             "ci": omega_ci(L_al[s]["LOGIC"], L_be[s]["LOGIC"])} for s in SEATS}
RES["b_learned_votes"]["trajectory"] = traj
RES["b_decay"] = {"ba": bal(D_rej, y), "auc": auc([D_rec[i]["score"] for i in range(n)], y),
                  "vs_uniform_decisions": mcnemar(D_rej, U_rej)}
say(f"  learned weights with WaRF's decay (0.95 per week, reviews dated at commit time): balanced accuracy "
    f"{bal(D_rej, y):.3f}, AUC {auc([D_rec[i]['score'] for i in range(n)], y):.3f}")

rng = random.Random(11)
R_ORD = 200
diffs, n_changed, ba_l, ba_u, au_l = [], [], [], [], []
for _ in range(R_ORD):
    st = list(range(n))
    rng.shuffle(st)
    for order in ORDERS:
        lr = stream_run(st, order, V, XSTAR)[0]
        ur = stream_run(st, order, V, XSTAR, learn=False)[0]
        lrj = [lr[i]["rej"] for i in range(n)]
        urj = [ur[i]["rej"] for i in range(n)]
        ba_l.append(bal(lrj, y))
        ba_u.append(bal(urj, y))
        au_l.append(auc([lr[i]["score"] for i in range(n)], y))
        n_changed.append(sum(a != b for a, b in zip(lrj, urj)))
        diffs.append(ba_l[-1] - ba_u[-1])


def q(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p * len(v)))]


say(f"  {R_ORD} random review orders x 6 tie-break orders: learned balanced accuracy mean {sum(ba_l) / len(ba_l):.3f} "
    f"[{q(ba_l, .025):.3f}, {q(ba_l, .975):.3f}], uniform {sum(ba_u) / len(ba_u):.3f}; learned minus uniform "
    f"{sum(diffs) / len(diffs):+.4f} [{q(diffs, .025):+.3f}, {q(diffs, .975):+.3f}]; decisions changed per run: "
    f"max {max(n_changed)}, mean {sum(n_changed) / len(n_changed):.2f}; AUC of -Lambda mean {sum(au_l) / len(au_l):.3f}")
RES["b_random_orders"] = {"runs": len(diffs), "ba_learned_mean": sum(ba_l) / len(ba_l),
                          "ba_uniform_mean": sum(ba_u) / len(ba_u), "diff_mean": sum(diffs) / len(diffs),
                          "diff_interval": [q(diffs, .025), q(diffs, .975)], "changed_max": max(n_changed),
                          "changed_mean": sum(n_changed) / len(n_changed), "auc_learned_mean": sum(au_l) / len(au_l)}

rng = random.Random(13)
R_SH = 1000
sh_diff, sh_changed, sh_true_ba, sh_auc_diff, sh_true_auc_diff = [], [], [], [], []
for _ in range(R_SH):
    perm = y[:]
    rng.shuffle(perm)
    orc = [-1 if t else 1 for t in perm]
    lr = stream_run(TIME_ORDER, ORDERS[0], V, orc)[0]
    lrj = [lr[i]["rej"] for i in range(n)]
    sh_diff.append(bal(lrj, perm) - bal(U_rej, perm))
    sh_changed.append(sum(a != b for a, b in zip(lrj, U_rej)))
    sh_true_ba.append(bal(lrj, y))
    sh_auc_diff.append(auc([lr[i]["score"] for i in range(n)], perm) - auc(base["score"], perm))
    sh_true_auc_diff.append(auc([lr[i]["score"] for i in range(n)], y) - auc(base["score"], y))
obs_diff = bal(L_rej, y) - bal(U_rej, y)
obs_auc_diff = auc(L_score, y) - auc(base["score"], y)
p_ba = (1 + sum(d >= obs_diff for d in sh_diff)) / (1 + R_SH)
p_auc = (1 + sum(d >= obs_auc_diff for d in sh_auc_diff)) / (1 + R_SH)
say(f"  control, {R_SH} shuffles of the labels (oracle and scoring both shuffled, commit-date order): learned minus "
    f"uniform balanced accuracy mean {sum(sh_diff) / R_SH:+.4f} [{q(sh_diff, .025):+.3f}, {q(sh_diff, .975):+.3f}], "
    f"decisions changed max {max(sh_changed)}; AUC of -Lambda learned minus uniform mean "
    f"{sum(sh_auc_diff) / R_SH:+.4f} [{q(sh_auc_diff, .025):+.3f}, {q(sh_auc_diff, .975):+.3f}]")
say(f"    observed with the real labels: balanced accuracy {obs_diff:+.4f} (one-sided p {p_ba:.3f}), "
    f"AUC {obs_auc_diff:+.4f} (one-sided p {p_auc:.3f}); trained on shuffled labels and scored on the real ones: "
    f"balanced accuracy mean {sum(sh_true_ba) / R_SH:.3f} [{q(sh_true_ba, .025):.3f}, {q(sh_true_ba, .975):.3f}]")
rng = random.Random(29)
iid_auc_diff = []
while len(iid_auc_diff) < R_SH:
    lab = [rng.random() < 0.5 for _ in range(n)]
    if sum(lab) in (0, n):
        continue
    lr = stream_run(TIME_ORDER, ORDERS[0], V, [-1 if t else 1 for t in lab])[0]
    iid_auc_diff.append(auc([lr[i]["score"] for i in range(n)], lab) - auc(base["score"], lab))
say(f"    labels drawn independently instead (no fixed 50/50 split): AUC of -Lambda learned minus uniform mean "
    f"{sum(iid_auc_diff) / R_SH:+.4f} [{q(iid_auc_diff, .025):+.3f}, {q(iid_auc_diff, .975):+.3f}]")
say(f"    weights trained on shuffled labels, Lambda scored on the real labels: AUC learned minus uniform mean "
    f"{sum(sh_true_auc_diff) / R_SH:+.4f} [{q(sh_true_auc_diff, .025):+.3f}, {q(sh_true_auc_diff, .975):+.3f}]")
say("    (so the drop appears only when the labels that moved the weights are the labels scored: each label shifts")
say("    every later Lambda toward itself, which works against the AUC's comparisons across time)")
RES["b_iid_label_control_auc_diff"] = [sum(iid_auc_diff) / R_SH, q(iid_auc_diff, .025), q(iid_auc_diff, .975)]
RES["b_trained_shuffled_scored_true_auc_diff"] = [sum(sh_true_auc_diff) / R_SH, q(sh_true_auc_diff, .025),
                                                   q(sh_true_auc_diff, .975)]
RES["b_shuffle_control"] = {"shuffles": R_SH, "ba_diff_mean": sum(sh_diff) / R_SH,
                            "ba_diff_interval": [q(sh_diff, .025), q(sh_diff, .975)], "changed_max": max(sh_changed),
                            "auc_diff_mean": sum(sh_auc_diff) / R_SH,
                            "auc_diff_interval": [q(sh_auc_diff, .025), q(sh_auc_diff, .975)],
                            "observed_ba_diff": obs_diff, "p_ba": p_ba, "observed_auc_diff": obs_auc_diff,
                            "p_auc": p_auc, "trained_on_shuffled_true_ba_mean": sum(sh_true_ba) / R_SH}

# ============================================================================================== c
head("(c) WaRF's routing rule (SPECIFICATION 1, principle 3): use only the vote of the heaviest seat")
best_vote = max(SEATS, key=lambda s: bal(REJ[s], y))
say(f"  The weights count right votes, so the seat they can single out is the best VOTER: "
    f"{', '.join(f'{s} {bal(REJ[s], y):.3f}' for s in SEATS)} -> {best_vote}; the best RANKER by AUC is CLAUDE.")
for s1, s2 in (("JEV", "CLAUDE"), ("JEV", "LAYA"), ("CLAUDE", "LAYA")):
    b_, c_, p_ = mcnemar(REJ[s1], REJ[s2])
    say(f"  votes right {s1} only / {s2} only: {b_} / {c_}, sign p {p_:.3f}")
mc_rng = random.Random(17)
pj = sum(mc_rng.betavariate(L_al["JEV"]["LOGIC"], L_be["JEV"]["LOGIC"])
         > max(mc_rng.betavariate(L_al["CLAUDE"]["LOGIC"], L_be["CLAUDE"]["LOGIC"]),
               mc_rng.betavariate(L_al["LAYA"]["LOGIC"], L_be["LAYA"]["LOGIC"])) for _ in range(20000)) / 20000
say(f"  after all 100 labels, WaRF's Beta posteriors give P(JEV's vote accuracy is the highest) = {pj:.2f} "
    f"(Monte Carlo, independent Betas)")
RES["c"] = {"best_voter": best_vote, "p_jev_best_posterior": pj, "true_order": {}, "random_orders": {}}
for tag, mode, VV, RR in (("votes", "route_shadow", V, REJ), ("votes", "route_only", V, REJ),
                          ("calibrated votes", "route_shadow", VC, REJC)):
    key = mode if tag == "votes" else f"{mode}, calibrated votes"
    say(f"\n  {key}: " + ("every seat votes and learns, the decision is the heaviest seat's vote"
                          if mode == "route_shadow" else
                          "warf review --max-agents 1: only the heaviest seat is asked, and only it learns")
        + ("" if tag == "votes" else " (diagnostic: each seat votes at its out-of-fold calibrated threshold; "
           "best calibrated voter " + max(SEATS, key=lambda s: bal(REJC[s], y)) + ")"))
    res_o = {}
    for order in ORDERS:
        recs, al, be = stream_run(TIME_ORDER, order, VV, XSTAR, mode=mode)
        rj = [recs[i]["rej"] for i in range(n)]
        fin = leader_after(al, be, order)
        routed = {s: sum(recs[i]["top"] == s for i in range(n)) for s in SEATS}
        sv = settle(recs, TIME_ORDER, fin)
        b_, c_, p_ = mcnemar(rj, RR[fin])
        res_o["-".join(order)] = {"ba": bal(rj, y), "routed": routed, "final_leader": fin, "settled_after": sv,
                                  "vs_final_leader_alone": [b_, c_, p_], "vs_uniform_vote_panel": mcnemar(rj, base["rej"])}
        say(f"    profile order {'-'.join(order):<18} bal.acc {bal(rj, y):.3f}; routed to "
            + ", ".join(f"{s} {routed[s]}" for s in SEATS)
            + f"; leader after 100 labels {fin}, settled after {sv} commits; vs {fin} alone {b_}/{c_} (p {p_:.2f}); "
            f"vs uniform vote panel {mcnemar(rj, base['rej'])[0]}/{mcnemar(rj, base['rej'])[1]} "
            f"(p {mcnemar(rj, base['rej'])[2]:.2f})")
    RES["c"]["true_order"][key] = res_o
    rng = random.Random(19)
    bas, fins, svs, rt = [], {s: 0 for s in SEATS}, {s: [] for s in SEATS}, {s: 0 for s in SEATS}
    for _ in range(R_ORD):
        st = list(range(n))
        rng.shuffle(st)
        for order in ORDERS:
            recs, al, be = stream_run(st, order, VV, XSTAR, mode=mode)
            rj = [recs[i]["rej"] for i in range(n)]
            bas.append(bal(rj, y))
            fin = leader_after(al, be, order)
            fins[fin] += 1
            svs[fin].append(settle(recs, st, fin))
            for i in range(n):
                rt[recs[i]["top"]] += 1
    tot = R_ORD * len(ORDERS)
    say(f"    {R_ORD} random orders x 6: bal.acc mean {sum(bas) / tot:.3f} [{q(bas, .025):.3f}, {q(bas, .975):.3f}]; "
        f"leader after 100 labels " + ", ".join(f"{s} {fins[s] / tot:.2f}" for s in SEATS)
        + "; share of commits routed " + ", ".join(f"{s} {rt[s] / (tot * n):.2f}" for s in SEATS))
    for s in SEATS:
        if svs[s]:
            say(f"      runs ending with {s} as leader: it led for good after median {median(svs[s]):.0f} commits "
                f"(quartiles {q(svs[s], .25)}, {q(svs[s], .75)}; 90th percentile {q(svs[s], .9)})")
    RES["c"]["random_orders"][key] = {
        "ba_mean": sum(bas) / tot, "ba_interval": [q(bas, .025), q(bas, .975)],
        "final_leader_share": {s: fins[s] / tot for s in SEATS},
        "routed_share": {s: rt[s] / (tot * n) for s in SEATS},
        "settle": {s: {"median": median(svs[s]), "quartiles": [q(svs[s], .25), q(svs[s], .75)],
                       "p90": q(svs[s], .9)} for s in SEATS if svs[s]}}
recs = stream_run(TIME_ORDER, ORDERS[0], V, XSTAR, mode="route_shadow")[0]
compare("(c) routing, every seat learns (commit-date order, profile order JEV-LAYA-CLAUDE)",
        [recs[i]["rej"] for i in range(n)], None, REJ, "c_route_shadow")
recs = stream_run(TIME_ORDER, ORDERS[0], VC, XSTAR, mode="route_shadow")[0]
compare("(c') routing on calibrated votes, every seat learns (commit-date order, profile order JEV-LAYA-CLAUDE)",
        [recs[i]["rej"] for i in range(n)], None, REJC, "c_route_shadow_calibrated", members_note="calibrated votes")

# ============================================================================================== d
head("(d) 'Use the probability' (IDEAS.md): each seat adds its log-odds instead of a fixed LLR")
say("  Lambda += omega * log((1-p)/p) (WaRF's sign: positive = APPROVE). 'sum': every seat adds, no SPRT,")
say("  decision APPROVE iff the omega-weighted mean log-odds >= theta (the synthesis rule with log-odds for votes).")
say("  'early': WaRF's boundaries A, B on the same Lambda, early stopping on, every seat order.")
for tag, llr, sr, srn in (("raw", LR, REJ, "votes at p > 0.5"), ("calibrated", LC, REJC, "calibrated votes")):
    runs_e = [uniform_panel(o, V, "early", llr) for o in ORDERS]
    bas_e = [bal(r["rej"], y) for r in runs_e]
    aus_e = [auc(r["score"], y) for r in runs_e]
    say(f"\n  {tag} log-odds, uniform omega, early stopping on: SPRT verdicts per order {[r['high'] for r in runs_e]}, "
        f"mean agents asked {sum(sum(r['k']) for r in runs_e) / (6 * n):.2f}; bal.acc mean {sum(bas_e) / 6:.3f} "
        f"(range {min(bas_e):.3f} to {max(bas_e):.3f}); AUC of -Lambda mean {sum(aus_e) / 6:.3f} "
        f"(range {min(aus_e):.3f} to {max(aus_e):.3f})")
    RES[f"d_{tag}_early_orders"] = {"verdicts": [r["high"] for r in runs_e], "ba": bas_e, "auc": aus_e}
    full = uniform_panel(list(SEATS), V, "none", llr)
    compare(f"(d) {tag} log-odds, uniform omega, every seat adds, sign of the sum against theta",
            full["rej"], full["score"], sr, f"d_{tag}_sum", members_note=srn)
    worst = min(range(6), key=lambda j: bas_e[j])
    compare(f"(d) {tag} log-odds, uniform omega, early stopping on, the order with the lowest bal.acc "
            f"({'-'.join(ORDERS[worst])})", runs_e[worst]["rej"], runs_e[worst]["score"], sr,
            f"d_{tag}_early_worst", members_note=srn)
    best = max(range(6), key=lambda j: bas_e[j])
    say(f"    (best order {'-'.join(ORDERS[best])}: bal.acc {bas_e[best]:.3f}, AUC {aus_e[best]:.3f})")
    lr = stream_run(TIME_ORDER, ORDERS[0], V, XSTAR, stop="none", llr=llr)[0]
    compare(f"(d) {tag} log-odds with learned omegas (prequential, commit-date order), every seat adds",
            [lr[i]["rej"] for i in range(n)], [lr[i]["score"] for i in range(n)], sr, f"d_{tag}_learned",
            members_note=srn)
say(f"\n  for scale: why_five.py's logit average (z-scored, equal weights) AUC {fmt0(RES['zavg_auc'])}; "
    f"vs CLAUDE {fmt(vs_auc(za, P['CLAUDE']))}; vs mean member {fmt(vs_mean_auc(za, [P[s] for s in SEATS]))}")
RES["zavg_vs_claude"] = vs_auc(za, P["CLAUDE"])
RES["zavg_vs_mean"] = vs_mean_auc(za, [P[s] for s in SEATS])
sum_raw = uniform_panel(list(SEATS), V, "none", LR)
sum_cal = uniform_panel(list(SEATS), V, "none", LC)
say(f"  raw log-odds sum minus the vote panel, AUC {fmt(vs_auc(sum_raw['score'], base['score']))}, decisions "
    f"{fmt(vs_ba(sum_raw['rej'], base['rej']))}, right only here/only the vote panel "
    f"{mcnemar(sum_raw['rej'], base['rej'])[0]}/{mcnemar(sum_raw['rej'], base['rej'])[1]} "
    f"(p {mcnemar(sum_raw['rej'], base['rej'])[2]:.3f})")
say(f"  calibrated log-odds sum minus the vote panel, AUC {fmt(vs_auc(sum_cal['score'], base['score']))}, decisions "
    f"{fmt(vs_ba(sum_cal['rej'], base['rej']))}, right only here/only the vote panel "
    f"{mcnemar(sum_cal['rej'], base['rej'])[0]}/{mcnemar(sum_cal['rej'], base['rej'])[1]} "
    f"(p {mcnemar(sum_cal['rej'], base['rej'])[2]:.3f})")
RES["d_vs_vote_panel"] = {"raw_auc": vs_auc(sum_raw["score"], base["score"]),
                          "raw_ba": vs_ba(sum_raw["rej"], base["rej"]),
                          "cal_auc": vs_auc(sum_cal["score"], base["score"]),
                          "cal_ba": vs_ba(sum_cal["rej"], base["rej"])}
share = {s: sum(abs(LR[s][i]) for i in range(n)) / sum(abs(LR[t][i]) for t in SEATS for i in range(n)) for s in SEATS}
say("  share of the summed |log-odds| each seat contributes, raw: " + ", ".join(f"{s} {v:.2f}" for s, v in share.items())
    + "; LAYA's raw log-odds are all positive (APPROVE), mean " + f"{sum(LR['LAYA']) / n:+.2f}")

# ============================================================================================== e
head("(e) Positive control: LAYA replaced by a synthetic seat with independent signal (AUC 0.70 expected)")
DELTA = math.sqrt(2) * N01.inv_cdf(0.70)
say(f"  SYN: score s = +/-{DELTA / 2:.3f} (later fixed / never fixed) + N(0, 1), independent of everything else;")
say(f"  p = sigmoid({DELTA:.3f} * s), its exact posterior (calibrated); votes REJECT iff s > 0. 500 draws.")
R_SYN = 500
rng = random.Random(23)
E = {k: [] for k in ("syn_auc", "syn_ba", "a_ba", "a_auc", "a_ba_vs_best", "a_ba_vs_claude", "a_ba_vs_mean",
                     "a_auc_vs_best", "a_auc_vs_claude", "dr_auc", "dr_ba", "dr_auc_vs_best", "dr_auc_vs_claude",
                     "dr_auc_vs_mean", "dr_ba_vs_best", "dc_auc", "dc_ba", "dc_auc_vs_best", "dc_auc_vs_claude",
                     "dc_auc_vs_mean", "dc_ba_vs_bestcal", "dr_early_ba", "dr_early_auc", "z_auc",
                     "z_auc_vs_best", "rho_jev", "rho_claude", "a_identical_orders")}
POW = {k: [] for k in ("a_ba_vs_best", "dr_auc_vs_claude", "dc_auc_vs_claude", "dc_auc_vs_best")}
pow_boot = BOOT[:200]
pow_yb = YB[:200]
SE = ("JEV", "SYN", "CLAUDE")


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb)


def within(x):
    m1 = sum(v for v, t in zip(x, y) if t) / sum(y)
    m0 = sum(v for v, t in zip(x, y) if not t) / (n - sum(y))
    return [v - (m1 if t else m0) for v, t in zip(x, y)]


for rep in range(R_SYN):
    s_ = [(DELTA / 2 if t else -DELTA / 2) + rng.gauss(0, 1) for t in y]
    Pe = {"JEV": P["JEV"], "SYN": [sigmoid(DELTA * v) for v in s_], "CLAUDE": P["CLAUDE"]}
    Ve = {"JEV": V["JEV"], "SYN": [-1 if v > 0 else 1 for v in s_], "CLAUDE": V["CLAUDE"]}
    LRe = {"JEV": LR["JEV"], "SYN": [-logit(p) for p in Pe["SYN"]], "CLAUDE": LR["CLAUDE"]}
    syn_cal = lopo(Pe["SYN"])[0]
    LCe = {"JEV": LC["JEV"], "SYN": [-z for z in syn_cal], "CLAUDE": LC["CLAUDE"]}
    rej_m = {s: [v == -1 for v in Ve[s]] for s in SE}
    rejc_m = {"JEV": REJC["JEV"], "SYN": [z > 0 for z in syn_cal], "CLAUDE": REJC["CLAUDE"]}
    m_auc = {s: auc(Pe[s], y) for s in SE}
    m_ba = {s: bal(rej_m[s], y) for s in SE}
    m_bac = {s: bal(rejc_m[s], y) for s in SE}
    pa = [uniform_panel(o, Ve, "early") for o in itertools.permutations(SE)]
    E["a_identical_orders"].append(all(r["rej"] == pa[0]["rej"] for r in pa))
    a_rej, a_sc = pa[0]["rej"], pa[0]["score"]
    dr = uniform_panel(list(SE), Ve, "none", LRe)
    dre = [uniform_panel(o, Ve, "early", LRe) for o in itertools.permutations(SE)]
    dc = uniform_panel(list(SE), Ve, "none", LCe)
    z = zavg([[logit(p) for p in Pe[s]] for s in SE])
    E["syn_auc"].append(m_auc["SYN"])
    E["syn_ba"].append(m_ba["SYN"])
    E["rho_jev"].append(corr(within(LRe["SYN"]), within(LR["JEV"])))
    E["rho_claude"].append(corr(within(LRe["SYN"]), within(LR["CLAUDE"])))
    E["a_ba"].append(bal(a_rej, y))
    E["a_auc"].append(auc(a_sc, y))
    E["a_ba_vs_best"].append(E["a_ba"][-1] - max(m_ba.values()))
    E["a_ba_vs_claude"].append(E["a_ba"][-1] - m_ba["CLAUDE"])
    E["a_ba_vs_mean"].append(E["a_ba"][-1] - sum(m_ba.values()) / 3)
    E["a_auc_vs_best"].append(E["a_auc"][-1] - max(m_auc.values()))
    E["a_auc_vs_claude"].append(E["a_auc"][-1] - m_auc["CLAUDE"])
    E["dr_auc"].append(auc(dr["score"], y))
    E["dr_ba"].append(bal(dr["rej"], y))
    E["dr_auc_vs_best"].append(E["dr_auc"][-1] - max(m_auc.values()))
    E["dr_auc_vs_claude"].append(E["dr_auc"][-1] - m_auc["CLAUDE"])
    E["dr_auc_vs_mean"].append(E["dr_auc"][-1] - sum(m_auc.values()) / 3)
    E["dr_ba_vs_best"].append(E["dr_ba"][-1] - max(m_ba.values()))
    E["dr_early_ba"].append(sum(bal(r["rej"], y) for r in dre) / 6)
    E["dr_early_auc"].append(sum(auc(r["score"], y) for r in dre) / 6)
    E["dc_auc"].append(auc(dc["score"], y))
    E["dc_ba"].append(bal(dc["rej"], y))
    E["dc_auc_vs_best"].append(E["dc_auc"][-1] - max(m_auc.values()))
    E["dc_auc_vs_claude"].append(E["dc_auc"][-1] - m_auc["CLAUDE"])
    E["dc_auc_vs_mean"].append(E["dc_auc"][-1] - sum(m_auc.values()) / 3)
    E["dc_ba_vs_bestcal"].append(E["dc_ba"][-1] - max(m_bac.values()))
    E["z_auc"].append(auc(z, y))
    E["z_auc_vs_best"].append(E["z_auc"][-1] - max(m_auc.values()))
    if rep < 100:
        best_b = max(SE, key=lambda s: m_ba[s])
        best_a = max(SE, key=lambda s: m_auc[s])
        for key, stat in (
                ("a_ba_vs_best", lambda idx, yy: bal([a_rej[i] for i in idx], yy) - bal([rej_m[best_b][i] for i in idx], yy)),
                ("dr_auc_vs_claude", lambda idx, yy: auc([dr["score"][i] for i in idx], yy) - auc([P["CLAUDE"][i] for i in idx], yy)),
                ("dc_auc_vs_claude", lambda idx, yy: auc([dc["score"][i] for i in idx], yy) - auc([P["CLAUDE"][i] for i in idx], yy)),
                ("dc_auc_vs_best", lambda idx, yy: auc([dc["score"][i] for i in idx], yy) - auc([Pe[best_a][i] for i in idx], yy))):
            POW[key].append(interval(stat, pow_boot, pow_yb)[1] > 0)


def summ(k):
    v = E[k]
    return {"mean": sum(v) / len(v), "lo": q(v, .025), "hi": q(v, .975), "share_pos": sum(x > 0 for x in v) / len(v)}


say(f"  SYN realised AUC mean {sum(E['syn_auc']) / R_SYN:.3f} [{q(E['syn_auc'], .025):.3f}, {q(E['syn_auc'], .975):.3f}], "
    f"vote bal.acc mean {sum(E['syn_ba']) / R_SYN:.3f}; within-label correlation with JEV "
    f"{sum(E['rho_jev']) / R_SYN:+.3f}, with CLAUDE {sum(E['rho_claude']) / R_SYN:+.3f} "
    f"(JEV-CLAUDE: {corr(within(LR['JEV']), within(LR['CLAUDE'])):+.3f})")
say(f"  vote panel identical in all 6 orders in {sum(E['a_identical_orders'])} of {R_SYN} draws")
say(f"\n  {'(mean over draws [2.5 %, 97.5 % of draws], share of draws > 0)':<66} {'value':>8}")
rows = (("(a) votes: bal.acc", "a_ba"), ("(a) votes: bal.acc minus best member's vote", "a_ba_vs_best"),
        ("(a) votes: bal.acc minus CLAUDE's vote", "a_ba_vs_claude"),
        ("(a) votes: bal.acc minus mean member's vote", "a_ba_vs_mean"),
        ("(a) votes: AUC of -Lambda", "a_auc"), ("(a) votes: AUC minus best member's AUC", "a_auc_vs_best"),
        ("(a) votes: AUC minus CLAUDE's AUC", "a_auc_vs_claude"),
        ("(d) raw log-odds sum: AUC", "dr_auc"), ("(d) raw: AUC minus best member", "dr_auc_vs_best"),
        ("(d) raw: AUC minus CLAUDE", "dr_auc_vs_claude"), ("(d) raw: AUC minus mean member", "dr_auc_vs_mean"),
        ("(d) raw: bal.acc", "dr_ba"), ("(d) raw: bal.acc minus best member's vote", "dr_ba_vs_best"),
        ("(d) raw, early stopping on (mean of 6 orders): bal.acc", "dr_early_ba"),
        ("(d) raw, early stopping on (mean of 6 orders): AUC", "dr_early_auc"),
        ("(d) calibrated log-odds sum: AUC", "dc_auc"), ("(d) calibrated: AUC minus best member", "dc_auc_vs_best"),
        ("(d) calibrated: AUC minus CLAUDE", "dc_auc_vs_claude"),
        ("(d) calibrated: AUC minus mean member", "dc_auc_vs_mean"), ("(d) calibrated: bal.acc", "dc_ba"),
        ("(d) calibrated: bal.acc minus best member's calibrated vote", "dc_ba_vs_bestcal"),
        ("logit average (z-scored): AUC", "z_auc"), ("logit average: AUC minus best member", "z_auc_vs_best"))
RES["e"] = {}
for label, k in rows:
    sm = summ(k)
    RES["e"][k] = sm
    say(f"  {label:<66} {sm['mean']:+.3f} [{sm['lo']:+.3f}, {sm['hi']:+.3f}]  {sm['share_pos']:.2f}")
say("\n  power on n = 100 (first 100 draws, paired bootstrap with 200 resamples): share of draws whose 95 % interval "
    "excludes 0")
for k, v in POW.items():
    say(f"    {k:<22} {sum(v) / len(v):.2f}")
RES["e"]["power"] = {k: sum(v) / len(v) for k, v in POW.items()}

# ============================================================================================== summary
head("Summary: each variant against its best, average and weakest member (paired, same 100 commits)")
say(f"  {'variant':<52} {'bal.acc':>7} {'- JEV vote':>22} {'- CLAUDE vote':>22} {'- mean':>22} {'- LAYA':>22}")
for key, label in (("a_uniform_votes", "(a) uniform, votes (any order)"),
                   ("a_uniform_calibrated_votes", "(a') uniform, calibrated votes"),
                   ("b_learned_votes", "(b) learned weights, votes"),
                   ("c_route_shadow", "(c) routing to the heaviest seat"),
                   ("c_route_shadow_calibrated", "(c') routing, calibrated votes"),
                   ("d_raw_sum", "(d) raw log-odds, every seat"),
                   ("d_raw_early_worst", "(d) raw log-odds, early stop, worst order"),
                   ("d_calibrated_sum", "(d) calibrated log-odds, every seat"),
                   ("d_calibrated_learned", "(d) calibrated log-odds, learned omega")):
    r = RES[key]
    say(f"  {label:<52} {r['ba'][0]:>7.3f} {fmt(r['vs']['JEV']['d_ba']):>22} {fmt(r['vs']['CLAUDE']['d_ba']):>22} "
        f"{fmt(r['vs']['mean']['d_ba']):>22} {fmt(r['vs']['LAYA']['d_ba']):>22}")
say("  (decisions of the members: their votes at p > 0.5, or their calibrated votes for the calibrated variants)")
say(f"\n  {'variant':<52} {'AUC':>7} {'- JEV':>22} {'- CLAUDE':>22} {'- mean':>22} {'- LAYA':>22}")
for key, label in (("a_uniform_votes", "(a) uniform, votes: -Lambda"),
                   ("b_learned_votes", "(b) learned weights, votes: -Lambda"),
                   ("d_raw_sum", "(d) raw log-odds sum"),
                   ("d_calibrated_sum", "(d) calibrated log-odds sum"),
                   ("d_calibrated_learned", "(d) calibrated, learned omega")):
    r = RES[key]
    say(f"  {label:<52} {r['auc'][0]:>7.3f} {fmt(r['vs']['JEV']['d_auc']):>22} {fmt(r['vs']['CLAUDE']['d_auc']):>22} "
        f"{fmt(r['vs']['mean']['d_auc']):>22} {fmt(r['vs']['LAYA']['d_auc']):>22}")
say(f"  {'logit average (why_five.py), for scale':<52} {RES['zavg_auc'][0]:>7.3f} {'':>22} "
    f"{fmt(RES['zavg_vs_claude']):>22} {fmt(RES['zavg_vs_mean']):>22}")
say(f"\n  {time.time() - T0:.0f} s")

(HERE / "mixed_panel.log").write_text("\n".join(OUT) + "\n", encoding="utf-8")


def _js(o):
    if isinstance(o, (Decision, Confidence)):
        return o.value
    raise TypeError(type(o))


(HERE / "mixed_panel.json").write_text(json.dumps(RES, indent=1, default=_js), encoding="utf-8")
