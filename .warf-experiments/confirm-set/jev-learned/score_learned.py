"""Score the preregistered fifth test (../README.md, 2026-11-11): the mixed-version panel after WaRF learned on dev.

    python score_panels.py      # writes score.log, score.json"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
JN = HERE.parents[1] / "real-set" / "jev-narrow"
FROZEN = json.loads((JN / "frozen.json").read_text())
items = {json.loads(l)["id"]: json.loads(l) for l in (HERE.parent / "items.jsonl").open(encoding="utf-8")}
ids = list(items)
D = {i: items[i]["kind"] == "defective" for i in ids}
pos = [i for i in ids if D[i]]; neg = [i for i in ids if not D[i]]
CH = ["offbyone", "condition", "wrongvar", "missing", "memory", "interface", "compile"]
out = []


def say(s=""):
    out.append(s); print(s)


def lg(p):
    p = min(0.99, max(0.01, p)); return math.log(p / (1 - p))


whole, hunk = {}, {}
for l in (HERE.parent / "jev-narrow" / "answers.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
    (whole.__setitem__(r["id"], p) if r["state"] == "whole" else hunk.setdefault(r["id"], []).append(p))
N = {i: sum(lg(max((h[q] for h in hunk.get(i, [])), default=whole[i][q])) for q in CH) / len(CH) for i in ids}
pv = {i: whole[i]["verdict"] >= FROZEN["verdict"]["threshold"] for i in ids}
pn = {i: N[i] >= FROZEN["narrow"]["threshold"] for i in ids}


def panel(arm):
    rec = {}
    for l in (HERE / (arm.replace("P5", "sessions_P5") + ".jsonl") if "/" in arm else HERE / f"sessions_{arm}.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        if r["jev"]["id"] in rec: raise SystemExit(f"{arm}: {r['jev']['id']} twice")
        rec[r["jev"]["id"]] = r
    if set(rec) != set(ids): raise SystemExit(f"{arm}: {len(set(ids) - set(rec))} reviews missing")
    return rec


def ba(p):
    return (sum(p[i] for i in pos) / len(pos) + sum(not p[i] for i in neg) / len(neg)) / 2


def auc(s):
    P = [s[i] for i in pos]; Q = [s[i] for i in neg]
    return sum((a > b) + 0.5 * (a == b) for a in P for b in Q) / (len(P) * len(Q))


def mcnemar(k, n):
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k, n - k) + 1)) / 2 ** n)


def vs(pa, pr):
    k1 = sum(pa[i] == D[i] and pr[i] != D[i] for i in ids); k2 = sum(pr[i] == D[i] and pa[i] != D[i] for i in ids)
    return ba(pa) - ba(pr), k1, k2, mcnemar(k1, k1 + k2)


def line(name, p):
    say(f"  {name:<34} right {100 * ba(p):5.1f}%  caught {sum(p[i] for i in pos)}/110  false alarms {sum(p[i] for i in neg)}/110")


res, prim = {}, []
say("220 items (110 defective, 110 clean)")
line("V one Jev (dev threshold)", pv)
line("N WaRF Jev narrow checks", pn)
P5 = {i: r["decision"] == "REJECT" for i, r in panel("../jev-panels/P5").items()}
line("P5 untrained (fourth test)", P5)
SEATS = {"SKEPTIC": "jev-1.14", "ADVOCATE": "jev-1.14", "AUDITOR": "jev-1.14", "TEST-FOCUSED": "jev-1.13", "BOUNDARY": "jev-1.13"}
for arm in ("LV", "LO"):
    rec = panel(arm)
    seats = SEATS
    models = sorted({m for r in rec.values() for m in r["jev"]["models"]})
    pa = {i: rec[i]["decision"] == "REJECT" for i in ids}
    mp = {i: sum(v["p_reject"] for v in rec[i]["jev"]["round1"].values()) / len(seats) for i in ids}
    cost = sum(r["jev"]["cost"] for r in rec.values())
    say(f"\n{arm}: seats {seats}; models answering {models}; cost ${cost:.4f}")
    line(f"{arm} WaRF decision", pa)
    for name in seats:
        line(f"  seat {name} ({seats[name]}) alone, p>=0.5", {i: rec[i]["jev"]["round1"][name]["choice"] == "REJECT" for i in ids})
    names = list(seats)
    for x in range(len(names)):
        for y in range(x + 1, len(names)):
            a, b = names[x], names[y]
            agree = sum(rec[i]["jev"]["round1"][a]["choice"] == rec[i]["jev"]["round1"][b]["choice"] for i in ids) / len(ids)
            same = "same version" if seats[a] == seats[b] else "different versions"
            say(f"    agreement {a} / {b} ({same}): {100 * agree:.1f}%")
    say(f"  AUC of mean seat p(REJECT): {auc(mp):.3f}  (N {auc(N):.3f}, V {auc({i: whole[i]['verdict'] for i in ids}):.3f})")
    d, k1, k2, p = vs(pa, pv); prim.append((arm, d, k1, k2, p))
    d2, j1, j2, p2 = vs(pa, pn)
    d3, q1, q2, p3 = vs(pa, P5)
    say(f"  secondary vs untrained P5: {100 * d3:+.1f} points, only {arm} right {q1}, only P5 right {q2}, McNemar p {p3:.3f}")
    say(f"  secondary vs N: {100 * d2:+.1f} points, only {arm} right {j1}, only N right {j2}, McNemar p {p2:.3f}")
    res[arm] = {"ba": ba(pa), "vs_V": {"d": d, "only_panel": k1, "only_V": k2, "p": p},
                "vs_N": {"d": d2, "only_panel": j1, "only_N": j2, "p": p2}, "auc_mean_p": auc(mp), "cost": cost}
say("\nPRIMARY: each panel's WaRF decision vs V (one Jev), exact McNemar, Holm over the two panels")
order = sorted(prim, key=lambda t: t[4])
adj, run = {}, 0.0
for k, (arm, d, k1, k2, p) in enumerate(order):
    run = max(run, min(1.0, (len(order) - k) * p)); adj[arm] = run
for arm, d, k1, k2, p in prim:
    verdict = "WINS" if d > 0 and adj[arm] < 0.05 else "not shown" if d > 0 else "no case"
    say(f"  {arm} - V: {100 * d:+.1f} points; only {arm} right {k1}, only V right {k2}; p {p:.3f}, Holm {adj[arm]:.3f} -> {verdict}")
    res[arm]["verdict"] = verdict; res[arm]["vs_V"]["p_holm"] = adj[arm]
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score.json").write_text(json.dumps(res, indent=1))
