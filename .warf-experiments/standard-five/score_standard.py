"""Score WaRF's standard panel (five personas on Claude Haiku 4.5) and the AUDITOR-five-times arm
against the git-history labels of ../laya-five/selection.jsonl, side by side with Laya, Jev and
blinded Claude on the same 100 commits. A text agent gives only a vote, so a panel's score is its
share of REJECT votes among the agents that voted (an agent that timed out has none); one
vote alone ranks at its balanced accuracy.
Pure Python: numpy's BLAS crashes in gs\\cf\\python.exe.

    python .warf-experiments/standard-five/score_standard.py        # -> score.log, score.json"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "jev-five" / "verify" / "refute"))
from vstats import binom_two_sided, chi2_sf_1, delong_paired, delong_single, solve  # noqa: E402

AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")


def jl(path):
    return [json.loads(line) for line in Path(path).open(encoding="utf-8")] if Path(path).exists() else []


sel = jl(EXP / "laya-five" / "selection.jsonl")
ids = [s["id"] for s in sel]
label = {s["id"]: s["label"] == "REJECT" for s in sel}
five = {r["std"]["id"]: r for p in sorted(HERE.glob("five.w*.jsonl")) for r in jl(p)}
aud = {}
for p in sorted(HERE.glob("auditor5.w*.jsonl")):
    for r in jl(p):
        aud.setdefault(r["std"]["id"], {})[r["std"]["sample"]] = r
feat = {r["id"]: r for r in jl(EXP / "jev-five" / "verify" / "refute" / "features.jsonl")}
jone = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_one.jsonl")}
jfive = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_five.jsonl")}
lfive = {r["five"]["id"]: r for r in jl(EXP / "laya-five" / "sessions.jsonl")}
out = {}


def r1(rec, agent):
    """1 for a REJECT vote, 0 for APPROVE, None if the agent did not vote (timed out)."""
    v = next((v for v in rec["votes"] if v["agent"] == agent), None)
    return None if v is None else int(v["vote"] == -1)


def final(rec, agent):
    d = next((v for v in (rec.get("debate") or {}).get("votes", []) if v["agent"] == agent), None)
    return int(d["vote"] == -1) if d is not None else r1(rec, agent)


def share(rec, position):
    """Share of REJECT among the agents that voted: an agent that timed out has no vote, and in
    WaRF it sits out the debate too."""
    v = [x for x in (position(rec, a) for a in AGENTS) if x is not None]
    return sum(v) / len(v)


def show(name, score, items):
    """AUC (DeLong SE) of `score` (dict id -> value) on `items`; matched pairs won where both rows are in."""
    y = [label[i] for i in items]
    if min(sum(y), len(y) - sum(y)) < 2:
        print(f"  {name:<46} too few commits of one label so far")
        return None
    a, se = delong_single([score[i] for i in items], y)
    pairs = [(sel[2 * k]["id"], sel[2 * k + 1]["id"]) for k in range(len(sel) // 2)]
    pairs = [(p, q) for p, q in pairs if p in score and q in score and p in items and q in items]
    won = sum((score[p] > score[q]) + 0.5 * (score[p] == score[q]) for p, q in pairs)
    print(f"  {name:<46} {a:.3f} ±{se:.3f}   {won:>5.1f} of {len(pairs)}")
    out.setdefault("auc", {})[name] = [a, se, len(items)]
    return a


def diff(n1, s1, n2, s2, items):
    y = [label[i] for i in items]
    if min(sum(y), len(y) - sum(y)) < 2:
        return
    d, se, z, p, _ = delong_paired([s1[i] for i in items], [s2[i] for i in items], y)
    print(f"  {n1 + '  minus  ' + n2:<78} {d:+.3f} [{d - 1.96 * se:+.3f}, {d + 1.96 * se:+.3f}]  p {p:.3f}")
    out.setdefault("diff", {})[f"{n1} - {n2}"] = [d, se, p, len(items)]


def kappa(a, b):
    n = len(a)
    po = sum(x == z for x, z in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


# ── coverage and parsing ────────────────────────────────────────────────────
done = [i for i in ids if i in five]
print(f"\n  {len(sel)} commits, {sum(label.values())} later fixed; standard panel reviewed {len(done)}, "
      f"AUDITOR five times on {sum(len(v) == 5 for v in aud.values())}")
calls = [c for r in five.values() for c in r["std"]["calls"]] + \
        [c for d in aud.values() for r in d.values() for c in r["std"]["calls"]]
models = {(v["provider"], v["model"]) for r in five.values() for v in r["votes"]}
inexact = [c for c in calls if "error" not in c and c["first_line"].split()[0].upper().rstrip(".,:") not in ("APPROVE", "REJECT")]
print(f"  {len(calls)} agent calls, answered by {sorted(models)}; {sum('error' in c for c in calls)} failed; "
      f"mean {sum(c['seconds'] for c in calls) / max(1, len(calls)):.0f} s per call")
print(f"  first word not APPROVE or REJECT (WaRF falls back to searching the text): {len(inexact)}")
for c in inexact[:10]:
    print(f"    {c['agent']} {c['round']}: vote {c.get('vote')}, first line {c['first_line'][:100]!r}")
short = [i for i in done if len(five[i]["votes"]) < 5]
print(f"  reviews with fewer than five Round-1 votes (an agent timed out): {len(short)} {short[:10]}")
errs = jl(HERE / "errors.jsonl")
print(f"  failed reviews logged in errors.jsonl: {len(errs)}")

if not done:
    sys.exit()

# ── scores ──────────────────────────────────────────────────────────────────
S = {}
for a in AGENTS:
    S[f"Haiku {a}, Round 1"] = {i: r1(five[i], a) for i in done if r1(five[i], a) is not None}
S["standard panel, REJECT share, Round 1"] = {i: share(five[i], r1) for i in done}
S["standard panel, REJECT share, final"] = {i: share(five[i], final) for i in done}
S["standard panel, WaRF's decision"] = {i: int(five[i]["decision"] == "REJECT") for i in done}
full = [i for i in ids if len(aud.get(i, {})) == 5]
S["AUDITOR alone, first ask"] = {i: int(aud[i][0]["votes"][0]["vote"] == -1) for i in full}
S["AUDITOR asked five times, REJECT votes"] = {i: sum(aud[i][k]["votes"][0]["vote"] == -1 for k in range(5)) for i in full}
S["Jev, one question (p)"] = {i: jone[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids if i in jone}
S["Jev panel, mean p, Round 1"] = {i: sum(jfive[i]["jev"]["round1"][a]["p_reject"] for a in AGENTS) / 5 for i in ids if i in jfive}
S["Laya, one question (p)"] = {s["id"]: s["p_single_laya"] for s in sel}
S["Laya panel, mean p, Round 1"] = {i: sum(lfive[i]["five"]["round1"][a]["p_reject"] for a in AGENTS) / 5 for i in ids if i in lfive}
S["Claude Opus 5.5, blinded (p)"] = {s["id"]: s["p_claude"] for s in sel}
S["number of added lines"] = {i: feat[i]["added"] for i in ids if i in feat}

print(f"\n  AUC against the labels, on the {len(done)} reviewed commits (DeLong SE); matched pairs won")
for name in [k for k in S if not k.startswith("AUDITOR")]:
    show(name, S[name], [i for i in done if i in S[name]])
if full:
    print(f"\n  on the {len(full)} commits with five AUDITOR asks")
    for name in ("AUDITOR alone, first ask", "AUDITOR asked five times, REJECT votes",
                 "Haiku AUDITOR, Round 1", "standard panel, REJECT share, Round 1"):
        show(name, S[name], [i for i in full if i in S[name]])

print("\n  paired differences, same commits (DeLong, 95 %)")
both = [i for i in full if i in five]
if both:
    diff("standard panel, REJECT share, Round 1", S["standard panel, REJECT share, Round 1"],
         "AUDITOR asked five times, REJECT votes", S["AUDITOR asked five times, REJECT votes"], both)
for other in ("standard panel, REJECT share, Round 1", "Jev, one question (p)", "Jev panel, mean p, Round 1",
              "Laya, one question (p)", "Laya panel, mean p, Round 1", "Claude Opus 5.5, blinded (p)",
              "number of added lines"):
    first = "standard panel, REJECT share, final" if other == "standard panel, REJECT share, Round 1" else "standard panel, REJECT share, Round 1"
    items = [i for i in done if i in S[other]]
    diff(first, S[first], other, S[other], items)

# ── how alike the agents are ────────────────────────────────────────────────
print("\n  how alike the votes are (Round 1): share of commits with the same vote, Cohen's kappa")
for name, cols in (("five personas", {a: S[f"Haiku {a}, Round 1"] for a in AGENTS}),
                   ("AUDITOR's five asks", {k: {i: int(aud[i][k]["votes"][0]["vote"] == -1) for i in full} for k in range(5)} if full else {})):
    keys = list(cols)
    pairs = [(p, q) for n, p in enumerate(keys) for q in keys[n + 1:]]
    vals = []
    for p, q in pairs:
        common = [i for i in cols[p] if i in cols[q]]
        if common:
            vals.append(kappa([cols[p][i] for i in common], [cols[q][i] for i in common]))
    if vals:
        print(f"    {name:<20} agreement {sum(v[0] for v in vals) / len(vals):.2f}, kappa {sum(v[1] for v in vals) / len(vals):.2f} "
              f"(mean of {len(vals)} pairs; kappa from {min(v[1] for v in vals):.2f} to {max(v[1] for v in vals):.2f})")
        out.setdefault("alike", {})[name] = vals
print("    REJECT votes per persona, Round 1: " + ", ".join(f"{a} {sum(S[f'Haiku {a}, Round 1'].values())}" for a in AGENTS))
if full:
    print("    AUDITOR's REJECT votes per ask: " + ", ".join(str(sum(aud[i][k]["votes"][0]["vote"] == -1 for i in full)) for k in range(5)))

# ── debate and decisions ────────────────────────────────────────────────────
D = [i for i in done if five[i].get("debate")]
toward = changed = 0
for i in D:
    for v in five[i]["debate"]["votes"]:
        if v["changed"]:
            changed += 1
            toward += (v["vote"] == -1) == label[i]
print(f"\n  debate: {len(D)} of {len(done)} reviews went to Round 2 (the SPRT ended the others in Round 1); "
      f"{changed} votes changed, {toward} toward the label (sign test p {binom_two_sided(toward, changed) if changed else 1:.2f})")
cells = {}
for i in done:
    cells.setdefault((five[i]["decision"], five[i]["confidence"]), []).append(label[i])
print("  WaRF's decision: " + "; ".join(f"{d} {c} {len(v)} ({sum(v)} later fixed)" for (d, c), v in sorted(cells.items())))
by_k = {}
for i in done:
    v = [x for x in (r1(five[i], a) for a in AGENTS) if x is not None]
    by_k.setdefault(f"{sum(v)} of {len(v)}", []).append(label[i])
print("  later fixed, by Round-1 REJECT votes: " + ", ".join(f"{k}: {sum(v)}/{len(v)}" for k, v in sorted(by_k.items())))

# ── beyond the number of added lines (pair-matched conditional logistic) ────
pairs = [k for k in range(len(sel) // 2) if sel[2 * k]["id"] in five and sel[2 * k + 1]["id"] in five]


def clogit(cols, ridge=0.1, iters=100):
    """P(row 2k is the later-fixed one) = sigma(beta . (x_2k - x_2k+1)); columns scaled by their SD."""
    sd = []
    for c in cols:
        v = [c[s["id"]] for s in sel if s["id"] in c]
        m = sum(v) / len(v)
        sd.append(math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1)) or 1.0)
    D_ = [[(c[sel[2 * k]["id"]] - c[sel[2 * k + 1]["id"]]) / s for c, s in zip(cols, sd)] for k in pairs]
    beta = [0.0] * len(cols)
    for _ in range(iters):
        mu = [1 / (1 + math.exp(-sum(b * v for b, v in zip(beta, r)))) for r in D_]
        g = [sum((1 - m) * r[j] for r, m in zip(D_, mu)) - ridge * beta[j] for j in range(len(cols))]
        H = [[sum(m * (1 - m) * r[j] * r[l] for r, m in zip(D_, mu)) + (ridge if j == l else 0) for l in range(len(cols))]
             for j in range(len(cols))]
        st = solve(H, g)
        beta = [b + s for b, s in zip(beta, st)]
        if max(abs(s) for s in st) < 1e-10:
            break
    return beta, sum(-math.log1p(math.exp(-sum(b * v for b, v in zip(beta, r)))) for r in D_)


if len(pairs) >= 10:
    added = {i: math.log1p(f["added"]) for i, f in feat.items()}
    print(f"\n  beyond the number of added lines: pair-matched conditional logistic, {len(pairs)} pairs, ridge 0.1")
    _, ll_a = clogit([added])
    for name in ("standard panel, REJECT share, Round 1", "standard panel, REJECT share, final",
                 "Claude Opus 5.5, blinded (p)", "Jev, one question (p)"):
        sc = S[name]
        if name.endswith("(p)"):
            sc = {i: math.log(max(1e-4, min(1 - 1e-4, v)) / (1 - max(1e-4, min(1 - 1e-4, v)))) for i, v in sc.items()}
        b0, ll0 = clogit([sc])
        b1, ll1 = clogit([added, sc])
        lr0, lr1 = 2 * (ll0 - len(pairs) * math.log(0.5)), 2 * (ll1 - ll_a)
        print(f"    {name:<42} alone LR {lr0:5.2f} p {chi2_sf_1(lr0):.4f};  after log added lines LR {lr1:5.2f} p {chi2_sf_1(lr1):.4f}")
        out.setdefault("beyond_added", {})[name] = [lr0, chi2_sf_1(lr0), lr1, chi2_sf_1(lr1), len(pairs)]

(HERE / "score.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
