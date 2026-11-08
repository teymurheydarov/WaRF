"""Independent recompute and audit of score_five.log (does not import score_five.py or warf).

    python -B verify/five-audit/audit.py > verify/five-audit/audit.log
"""
import hashlib
import json
import math
import random
import re
from itertools import combinations
from pathlib import Path

H = Path(__file__).resolve().parents[2]          # .../planted
WARF = H.parents[1] / "warf"

# ---- constants re-derived from the source text, not imported -------------------------------
eng = (WARF / "engine.py").read_text(encoding="utf-8")
P1 = float(re.search(r"^P1 = ([\d.]+)", eng, re.M).group(1))
P0 = float(re.search(r"^P0 = ([\d.]+)", eng, re.M).group(1))
AE = float(re.search(r"^ALPHA_ERR = ([\d.]+)", eng, re.M).group(1))
BE = float(re.search(r"^BETA_ERR\s*= ([\d.]+)", eng, re.M).group(1))
A = math.log((1 - BE) / AE)
B = math.log(BE / (1 - AE))
LA, LR = math.log(P1 / P0), math.log((1 - P1) / (1 - P0))
THETA = {"LOGIC": 0.0, "SECURITY": 0.2, "PERFORMANCE": -0.1}
assert '"LOGIC":       0.0' in eng and '"SECURITY":   +0.2' in eng and '"PERFORMANCE": -0.1' in eng
orch = (WARF / "orchestrator.py").read_text(encoding="utf-8")
REPLY_FORMAT = ("First line of your response must be exactly one word: APPROVE or REJECT.\n"
                "Subsequent lines: your reasoning.")
assert ('"First line of your response must be exactly one word: APPROVE or REJECT.\\n"\n'
        '    "Subsequent lines: your reasoning."') in orch
INPUT_LABEL = "Patch under review (unified diff)"
assert f'INPUT_LABEL = "{INPUT_LABEL}"' in (H.parents[1] / "tools" / "run_laya_sweep.py").read_text(encoding="utf-8")
ORDER = ["SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY"]
MODEL = "claude-opus-5-5"


def p(*a):
    print(*a)


items = [json.loads(l) for l in (H / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
planted = [it for it in items if it["kind"] == "planted"]
num = {it["base"]: k + 1 for k, it in enumerate(planted)}
assert len(items) == 108 and len(planted) == 54 and len(by_id) == 108


def load(arm):
    recs = {}
    for f in sorted(H.glob(f"{arm}.w*.jsonl")):
        for l in f.open(encoding="utf-8"):
            r = json.loads(l)
            i = r["planted"]["id"]
            assert i not in recs, (arm, i)
            recs[i] = r
    return recs


one, five = load("claude"), load("claude-standard")
p(f"records: claude {len(one)}, claude-standard {len(five)}; ids == items: "
  f"{set(one) == set(by_id)}, {set(five) == set(by_id)}")
p(f"errors.jsonl present: {(H / 'errors.jsonl').exists()}")
bases = list(num)
R1 = {i: r["decision"] == "REJECT" for i, r in one.items()}
R5 = {i: r["decision"] == "REJECT" for i, r in five.items()}
truth = {i: by_id[i]["kind"] == "planted" for i in by_id}

# ================= (1) recompute =================================================================
HARMLESS, NOCOMPILE, DEAD = {15, 18, 22, 31, 33}, {17, 32, 35, 47, 54}, {46, 50}
ORIG_DEFECT = {5, 7, 26, 31, 36, 39, 52, 53}
rs = (H / "verify" / "testcheck" / "rescore.py").read_text(encoding="utf-8")
for name, s in [("HARMLESS", HARMLESS), ("NOCOMPILE", NOCOMPILE), ("DEAD", DEAD), ("ORIG_DEFECT", ORIG_DEFECT)]:
    m = re.search(rf"^{name} = (\{{[\d,]+\}})", rs, re.M)
    assert m and eval(m.group(1)) == s, name
p("hand-class sets equal rescore.py: yes")


def ba(R, bs):
    return (sum(R[f"{b}:planted"] for b in bs) / len(bs) + sum(not R[f"{b}:clean"] for b in bs) / len(bs)) / 2


def mcnemar_exact(k, n):
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


def q(xs, f):                       # type-7 quantile
    xs = sorted(xs)
    h = (len(xs) - 1) * f
    lo = math.floor(h)
    return xs[lo] + (h - lo) * (xs[min(lo + 1, len(xs) - 1)] - xs[lo])


subsets = {"all": bases,
           "cleaned": [b for b in bases if num[b] not in HARMLESS | NOCOMPILE | DEAD | ORIG_DEFECT]}
rng4 = random.Random(4)             # replicate score_five's draw sequence exactly
for name, bs in subsets.items():
    p(f"\n== (1) {name}: {len(bs)} bases ==")
    boots = [[rng4.choice(bs) for _ in bs] for _ in range(2000)]
    rngB = random.Random(20261104)
    big = [[rngB.choice(bs) for _ in bs] for _ in range(20000)]
    for lab, R in (("one", R1), ("five", R5)):
        xs = sorted(ba(R, s) for s in boots)
        ys = [ba(R, s) for s in big]
        p(f"  {lab:<4} BA {ba(R, bs):.4f}  caught {sum(R[b + ':planted'] for b in bs)}/{len(bs)}  "
          f"passed {sum(not R[b + ':clean'] for b in bs)}/{len(bs)}  "
          f"seed4 2000 [xs[49], xs[1949]] = [{xs[49]:.4f}, {xs[1949]:.4f}]  "
          f"20000-resample 2.5/97.5 % = [{q(ys, .025):.4f}, {q(ys, .975):.4f}]")
    d = ba(R5, bs) - ba(R1, bs)
    xs = sorted(ba(R5, s) - ba(R1, s) for s in boots)
    ys = [ba(R5, s) - ba(R1, s) for s in big]
    p(f"  five-one {d:+.4f}  seed4 [{xs[49]:+.4f}, {xs[1949]:+.4f}]  20000 [{q(ys, .025):+.4f}, {q(ys, .975):+.4f}]  "
      f"share of resamples with d<=0: {sum(y <= 0 for y in ys) / len(ys):.3f}, d<0: {sum(y < 0 for y in ys) / len(ys):.3f}")
    ids = [f"{b}:{k}" for b in bs for k in ("clean", "planted")]
    o5 = [i for i in ids if R5[i] == truth[i] and R1[i] != truth[i]]
    o1 = [i for i in ids if R1[i] == truth[i] and R5[i] != truth[i]]
    p(f"  only five right {len(o5)} {o5}\n  only one right {len(o1)} {o1}\n"
      f"  McNemar exact two-sided p = {mcnemar_exact(len(o5), len(o5) + len(o1)):.4f}")
    # check: the difference in BA equals (only5 - only1) / (2n)
    assert abs(d - (len(o5) - len(o1)) / (2 * len(bs))) < 1e-12

p("\n== (1) Claude alone's clean REJECTs and the five-Claude verdict ==")
for b in bases:
    i = f"{b}:clean"
    if R1[i]:
        r = five[i]
        p(f"  #{num[b]:<3} {r['decision']:<8}{r['confidence']:<7}"
          f"{''.join('R' if v['vote'] == -1 else 'A' for v in r['votes'])}  {b}")

# ================= (2) audit of claude-standard records =========================================
p("\n== (2) claude-standard record audit ==")
prof = json.loads((H / "profiles" / "claude-standard.json").read_text(encoding="utf-8"))
ph = {x["name"]: x["persona_hash"] for x in prof}
for x in prof:
    assert hashlib.sha256(" ".join(x["persona"].split()).encode()).hexdigest()[:12] == x["persona_hash"]
    assert x.get("provider") is None and x.get("model") is None and x.get("last_updated") is None
    assert all(w["alpha"] == 1.0 and w["beta"] == 1.0 for w in x["weights"].values())
p(f"  profile: names {[x['name'] for x in prof]}, uniform alpha=beta=1, no provider/model override, "
  f"persona hashes recomputed OK")


def first_word(t):
    return t.split()[0].upper().rstrip(".,:") if t.split() else ""


def parse_vote(t):
    fw = first_word(t)
    if fw == "APPROVE":
        return 1
    if fw == "REJECT":
        return -1
    return 1 if re.search(r"\bAPPROVE\b", t, re.I) else -1


def expected_chars(it):
    ctx = f"Project context:\n{it['context']}\n\n" if it["context"] else ""
    return len(f"Domain: {it['domain']}\n\n{ctx}{INPUT_LABEL}:\n```\n{it['code']}\n```\n\n{REPLY_FORMAT}")


problems = []
counts = {"replay_ok": 0, "firstline_exact": 0, "calls": 0, "domains": {}}
for i, r in five.items():
    it = by_id[i]
    vs, cs = r["votes"], r["planted"]["calls"]
    names = [v["agent"] for v in vs]
    counts["domains"][r["domain"]] = counts["domains"].get(r["domain"], 0) + 1
    if names != ORDER[:len(names)]:
        problems.append((i, "order", names))
    if [c["agent"] for c in cs] != names:
        problems.append((i, "calls!=votes", [c["agent"] for c in cs]))
    if r["domain"] != it["domain"] or r["theta"] != THETA[it["domain"]]:
        problems.append((i, "domain", r["domain"]))
    if r["artifact"] != f"{it['commit']}:{it['file']}":
        problems.append((i, "artifact", r["artifact"]))
    for v, c in zip(vs, cs):
        counts["calls"] += 1
        if not (v["model"] == MODEL == c["model"] and v["provider"] == "claude_cli" and v["omega"] == 0.5):
            problems.append((i, "model/omega", v["agent"], v["model"], c["model"], v["provider"], v["omega"]))
        if v["persona"] != ph[v["agent"]][:len(v["persona"])]:
            problems.append((i, "persona", v["agent"]))
        t = c["reply"]
        fl = t.split("\n", 1)[0].strip()
        if fl in ("APPROVE", "REJECT"):
            counts["firstline_exact"] += 1
        else:
            problems.append((i, "first line not exact", v["agent"], fl[:60]))
        if first_word(t) not in ("APPROVE", "REJECT") or not c["exact"]:
            problems.append((i, "first word", v["agent"], first_word(t)))
        if parse_vote(t) != v["vote"] or (v["label"] == "REJECT") != (v["vote"] == -1):
            problems.append((i, "vote!=reply", v["agent"]))
        reasoning = t[t.index("\n"):].strip() if "\n" in t else ""
        if reasoning != v["reasoning"]:
            problems.append((i, "reasoning!=reply", v["agent"]))
        if c["sent_chars"] != expected_chars(it):
            problems.append((i, "sent_chars!=expected", v["agent"], c["sent_chars"], expected_chars(it)))
        if c["sent_chars"] != one[i]["planted"]["call"]["sent_chars"]:
            problems.append((i, "sent_chars!=claude alone", v["agent"]))
        if v["tokens_in"] or v["tokens_out"]:
            problems.append((i, "tokens", v["agent"]))
    # replay WaRF vote mode: omega 0.5, SPRT, early stop on, synthesis on exhaustion
    lam, dec = 0.0, None
    k_stop = None
    for k, v in enumerate(vs):
        lam += 0.5 * (LA if v["vote"] == 1 else LR)
        if lam >= A:
            dec, k_stop = "APPROVE", k + 1
            break
        if lam <= B:
            dec, k_stop = "REJECT", k + 1
            break
    if dec is not None:
        conf, norm, fired = "HIGH", None, True
        ok_len = k_stop == len(vs)
    else:
        ok_len = len(vs) == 5
        fired = False
        nrm = sum(0.5 * v["vote"] for v in vs) / (0.5 * len(vs))
        th = THETA[r["domain"]]
        dec = "APPROVE" if nrm >= th else "REJECT"
        conf = "MEDIUM" if abs(nrm - th) >= 0.2 else "LOW"
        norm = nrm
    good = (ok_len and dec == r["decision"] and conf == r["confidence"] and bool(r["sprt_fired"]) == fired
            and abs(round(lam, 4) - r["sprt_lambda"]) < 1e-3
            and (norm is None and r["normalised_score"] is None or norm is not None and r["normalised_score"] is not None
                 and abs(norm - r["normalised_score"]) < 1e-3))
    if good:
        counts["replay_ok"] += 1
    else:
        problems.append((i, "replay", [v["vote"] for v in vs], dec, conf, r["decision"], r["confidence"],
                         r["sprt_lambda"], r["sprt_fired"], r["normalised_score"]))
    # panel verdict vs plain majority of the votes cast
    if (sum(v["vote"] for v in vs) < 0) != (r["decision"] == "REJECT"):
        problems.append((i, "verdict != majority of votes cast"))
p(f"  SPRT: A={A:.4f} B={B:.4f}; 0.5*LLR approve {0.5 * LA:+.4f} reject {0.5 * LR:+.4f}; "
  f"RRRR -> {4 * 0.5 * LR:+.4f}, RRR -> {3 * 0.5 * LR:+.4f}, AAAAA -> {5 * 0.5 * LA:+.4f}")
p(f"  domains: {counts['domains']}")
p(f"  replay matches decision/confidence/lambda/fired/normalised/length: {counts['replay_ok']}/{len(five)}")
p(f"  calls checked: {counts['calls']}; first line exactly APPROVE/REJECT: {counts['firstline_exact']}")
p(f"  problems: {len(problems)}")
for x in problems[:40]:
    p("   ", x)
# Claude alone records
pr1 = []
for i, r in one.items():
    c = r["planted"]["call"]
    v = r["votes"][0]
    fl = c["reply"].split("\n", 1)[0].strip()
    if not (len(r["votes"]) == 1 and v["model"] == MODEL == c["model"] and v["agent"] == "CLAUDE" and fl in ("APPROVE", "REJECT")
            and parse_vote(c["reply"]) == v["vote"] and (v["vote"] == -1) == (r["decision"] == "REJECT")
            and c["sent_chars"] == expected_chars(by_id[i])):
        pr1.append((i, v["agent"], v["model"], fl[:40]))
p(f"  claude-alone records with a problem (model, agent, first line, vote, sent_chars): {len(pr1)} {pr1[:5]}")
gaps = [i for i, r in five.items() if len(r["votes"]) < 5 and [v["vote"] for v in r["votes"]] != [-1] * 4]
p(f"  records with <5 votes that are not RRRR early stops (would reveal a skipped/timed-out seat): {gaps}")

# ================= (3) discordant items ===========================================================
disc = [i for i in by_id if R1[i] != R5[i]]
p(f"\n== (3) discordant items: {len(disc)} ==")
for i in disc:
    r = five[i]
    p(f"  {i} truth={'planted' if truth[i] else 'clean'} one={one[i]['decision']} five={r['decision']} "
      f"votes={''.join(v['agent'][0] + ('R' if v['vote'] == -1 else 'A') + ' ' for v in r['votes'])}")

# ================= (4) independence ===============================================================
p("\n== (4) how far the five behave like independent samples ==")
split = {}
for i, r in five.items():
    key = ("planted" if truth[i] else "clean", len(r["votes"]), sum(v["vote"] == -1 for v in r["votes"]))
    split[key] = split.get(key, 0) + 1
for k in sorted(split):
    p(f"  {k}: {split[k]}")
seat = {a: {"clean": [0, 0], "planted": [0, 0]} for a in ORDER}
for i, r in five.items():
    for v in r["votes"]:
        s = seat[v["agent"]]["planted" if truth[i] else "clean"]
        s[0] += v["vote"] == -1
        s[1] += 1
p("  per-seat REJECT clean / planted: " + "; ".join(f"{a} {s['clean'][0]}/{s['clean'][1]} / {s['planted'][0]}/{s['planted'][1]}"
                                                    for a, s in seat.items()))
p(f"  Claude alone REJECT clean {sum(R1[i] for i in by_id if not truth[i])}/54, planted {sum(R1[i] for i in by_id if truth[i])}/54")

# within-item agreement of each seat with Claude alone, and what independence would predict
p("  agreement of each seat with Claude alone's answer on the same item (observed vs independent given stratum rates):")
for a in ORDER:
    for st in ("clean", "planted"):
        pairs = [(R1[i], v["vote"] == -1) for i, r in five.items() if truth[i] == (st == "planted")
                 for v in r["votes"] if v["agent"] == a]
        n = len(pairs)
        if not n:
            continue
        obs = sum(x == y for x, y in pairs) / n
        p1 = sum(x for x, _ in pairs) / n
        p2 = sum(y for _, y in pairs) / n
        exp = p1 * p2 + (1 - p1) * (1 - p2)
        kap = (obs - exp) / (1 - exp) if exp < 1 else float("nan")
        both = sum(x and y for x, y in pairs)
        p(f"    {a:<13}{st:<8} n={n:2d} agree {obs:.3f} (indep. {exp:.3f}, kappa {kap:+.2f}); "
          f"one R & seat R {both}, one R & seat A {sum(x and not y for x, y in pairs)}, "
          f"one A & seat R {sum(y and not x for x, y in pairs)}")

# four always-asked seats: pairwise kappa within stratum, Fleiss kappa, intraclass correlation,
# and observed vs independent-Bernoulli distribution of the REJECT count
FOUR = ORDER[:4]
for st in ("clean", "planted"):
    ids = [i for i in by_id if truth[i] == (st == "planted")]
    M = [[next(v["vote"] == -1 for v in five[i]["votes"] if v["agent"] == a) for a in FOUR] for i in ids]
    rates = [sum(row[j] for row in M) / len(M) for j in range(4)]
    # Poisson-binomial under independence with seat-specific rates
    dist = [1.0]
    for pj in rates:
        dist = [(dist[k] if k < len(dist) else 0) * (1 - pj) + (dist[k - 1] if k >= 1 else 0) * pj
                for k in range(len(dist) + 1)]
    obs = [sum(sum(row) == k for row in M) for k in range(5)]
    p(f"  {st}: four always-asked seats, REJECT count 0..4 observed {obs}, independent "
      f"{[round(x * len(M), 1) for x in dist]}")
    # Fleiss kappa (exchangeable raters)
    n = 4
    pbar = sum(sum(row) for row in M) / (n * len(M))
    Pi = [(sum(row) * (sum(row) - 1) + (n - sum(row)) * (n - sum(row) - 1)) / (n * (n - 1)) for row in M]
    Pe = pbar ** 2 + (1 - pbar) ** 2
    fk = (sum(Pi) / len(Pi) - Pe) / (1 - Pe)
    p(f"    Fleiss kappa {fk:+.3f} (pooled REJECT rate {pbar:.3f}); effective independent votes among 4 "
      f"= 4/(1+3*rho) = {4 / (1 + 3 * fk):.2f} with rho = kappa")
    for a1, a2 in combinations(range(4), 2):
        x = [row[a1] for row in M]
        y = [row[a2] for row in M]
        o = sum(u == w for u, w in zip(x, y)) / len(x)
        px, py = sum(x) / len(x), sum(y) / len(y)
        e = px * py + (1 - px) * (1 - py)
        k = (o - e) / (1 - e) if e < 1 else float("nan")
        p(f"    {FOUR[a1]}-{FOUR[a2]}: agree {o:.3f}, indep {e:.3f}, kappa {k:+.2f}")

# majority-of-independent-samples counterfactual: if each seat were an independent draw with
# Claude alone's per-stratum error rate, how often would a 5-vote majority be wrong?
for st in ("clean", "planted"):
    ids = [i for i in by_id if truth[i] == (st == "planted")]
    e1 = sum(R1[i] != truth[i] for i in ids) / len(ids)
    pm = sum(math.comb(5, k) * e1 ** k * (1 - e1) ** (5 - k) for k in range(3, 6))
    e5 = sum(R5[i] != truth[i] for i in ids) / len(ids)
    p(f"  {st}: Claude alone error {e1:.3f}; majority of 5 iid such votes would err {pm:.3f}; "
      f"panel errs {e5:.3f}")
# Claude alone vs the panel's verdict, and how often the panel's majority is unanimous
p(f"  panel verdict equals Claude alone on {sum(R1[i] == R5[i] for i in by_id)}/108")
una = sum(len({v['vote'] for v in r['votes']}) == 1 for r in five.values())
p(f"  unanimous panels (all votes cast agree): {una}/108")
p(f"  total Claude calls in claude-standard: {sum(len(r['planted']['calls']) for r in five.values())}")

# each always-asked seat as a single reviewer (post hoc; same calls as the panel)
p("\n  each always-asked seat scored alone (BA over 54 bases; discordance vs Claude alone):")
for a in FOUR:
    S = {i: next(v["vote"] == -1 for v in five[i]["votes"] if v["agent"] == a) for i in by_id}
    o5 = sum(S[i] == truth[i] and R1[i] != truth[i] for i in by_id)
    o1 = sum(R1[i] == truth[i] and S[i] != truth[i] for i in by_id)
    p(f"    {a:<13} BA {ba(S, bases):.4f}  caught {sum(S[b + ':planted'] for b in bases)}/54  "
      f"passed {sum(not S[b + ':clean'] for b in bases)}/54  only seat right {o5}, only one right {o1}, "
      f"McNemar p {mcnemar_exact(o5, o5 + o1):.4f}")
