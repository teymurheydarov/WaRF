"""Pooled development of LO over three projects (README.md): leave one project out, offline.

    python pooled.py        # writes pooled.log, pooled.json"""
import json
import math
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP.parent)); sys.path.insert(0, str(EXP / "kpx-set"))
from freeze import SIZE_TEXT, size_p  # noqa: E402
from warf.calibration import Calibrator, p_reject_from_text  # noqa: E402
from warf.engine import LOGODDS_MARGIN, logodds_boundary, logodds_decision, logodds_tau, pool_evidence  # noqa: E402
from warf.orchestrator import _group_key  # noqa: E402
from warf.state import AgentProfile, default_profiles, persona_hash  # noqa: E402

sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
from run_narrow import DEFAULT_PERSONA  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


PROJ, ITEMS = {}, {}
for proj, files in (("G+Smo", ("real-set/items.jsonl", "confirm-set/items.jsonl")), ("MFEM", ("mfem-set/items.jsonl",)),
                    ("KeePassXC", ("kpx-set/items.jsonl",))):
    for f in files:
        for l in (EXP / f).open(encoding="utf-8"):
            r = json.loads(l); ITEMS[r["id"]] = r; PROJ[r["id"]] = proj
Y = {i: (-1 if it["kind"] == "defective" else 1) for i, it in ITEMS.items()}
TEXT = {p.persona_hash: p.persona for p in default_profiles()}


def seat(agent, persona, provider, model, p):
    return {"agent": agent, "persona": persona_hash(persona), "persona_text": persona, "provider": provider,
            "model": model, "evidence_source": "", "vote": -1 if p >= 0.5 else 1, "p_reject": p}


PERS = {}
for f in ("confirm-set/jev-learned/dev_sessions.jsonl", "confirm-set/jev-learned/sessions_LO.jsonl",
          "mfem-set/sessions_LO.jsonl", "kpx-set/sessions_LO.jsonl"):
    for l in (EXP / f).open(encoding="utf-8"):
        r = json.loads(l)
        PERS[r["artifact"]] = [seat(v["agent"], TEXT[v["persona"]], "jev", v["model"], p_reject_from_text(v["reasoning"]))
                               for v in r["votes"]]
V1 = {}
for f in ("real-set/jev-narrow/answers.jsonl", "confirm-set/jev-narrow/answers.jsonl", "mfem-set/answers_narrow.jsonl",
          "kpx-set/answers_V1.jsonl"):
    for l in (EXP / f).open(encoding="utf-8"):
        r = json.loads(l)
        if r["state"] == "whole" and "jev-1.14" in r["model"]:
            p = min(0.99, max(0.01, round((r["answers"]["verdict"]["p"] or {}).get("REJECT", 0.0), 2)))
            V1[r["id"]] = [seat("JEV", DEFAULT_PERSONA, "jev", "jev-1.14", p)]
SIZE = {i: [seat("SIZE", SIZE_TEXT, "size", "", size_p(it["code"]))] for i, it in ITEMS.items()}
assert set(PERS) == set(ITEMS) == set(V1), "seats missing"


def calibrator(train, config):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for i in train:
            votes = [{k: v for k, v in s.items() if k != "persona_text"} for s in config(i)]
            f.write(json.dumps({"oracle": {"type": "DEVELOPER", "x_star": Y[i]}, "votes": votes}) + "\n")
        name = f.name
    cal = Calibrator(Path(name)); Path(name).unlink()
    return cal


def decide(seats, domain, cal, early=True):
    """run_review's log-odds path on stored answers; early=False checks the boundary only after the last group.
    Returns (decision, Lambda, stopped_early)."""
    order, by = [], {}
    for s in seats:
        g = _group_key(s["provider"], s["model"], None)
        if g not in by:
            order.append(g); by[g] = []
        by[g].append(s)
    ev = []
    for n, g in enumerate(order, 1):
        for s in by[g]:
            prof = AgentProfile(name=s["agent"], persona=s["persona_text"], persona_hash=s["persona"],
                                provider=s["provider"], model=s["model"], evidence=None)
            ev.append((g, cal.evidence(prof, s["vote"], s["p_reject"], 0.5, s["provider"], s["model"])[0]))
        lam, means = pool_evidence(ev)
        if early or n == len(order):
            b = logodds_boundary(lam, means)
            if b is not None:
                return b.value, lam, n < len(order)
    lam, means = pool_evidence(ev)
    return logodds_decision(lam, means, domain)[0].value, lam, False


ARMS = {"V1, one Jev seat": (lambda i: V1[i], True), "SIZE alone": (lambda i: SIZE[i], True),
        "LO, as tested": (lambda i: PERS[i], True), "LO-full, no early stop": (lambda i: PERS[i], False),
        "LO+SIZE": (lambda i: PERS[i] + SIZE[i], True), "LO+SIZE-full": (lambda i: PERS[i] + SIZE[i], False)}
projects = ["G+Smo", "MFEM", "KeePassXC"]
pred, lam, early_stop = {k: {} for k in ARMS}, {}, {}
for P in projects:
    test = [i for i in ITEMS if PROJ[i] == P]; train = [i for i in ITEMS if PROJ[i] != P]
    for name, (cfg, early) in ARMS.items():
        cal = calibrator(train, cfg)
        for i in test:
            d, l, st = decide(cfg(i), ITEMS[i]["domain"], cal, early)
            pred[name][i] = d
            if name == "LO, as tested":
                lam[i], early_stop[i] = l, st


def ba(p, ids):
    pos = [i for i in ids if Y[i] == -1]; neg = [i for i in ids if Y[i] == 1]
    return (sum(p[i] == "REJECT" for i in pos) / len(pos) + sum(p[i] == "APPROVE" for i in neg) / len(neg)) / 2


def right(p, i):
    return (p[i] == "REJECT") == (Y[i] == -1)


def mcnemar(a, b, ids):
    k1 = sum(right(a, i) and not right(b, i) for i in ids); k2 = sum(right(b, i) and not right(a, i) for i in ids)
    n = k1 + k2
    return k1, k2, (1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k1, k2) + 1)) / 2 ** n))


ids = list(ITEMS)
say(f"{len(ids)} changes; leave one project out (calibrate on the other two)")
say(f"  {'arm':<26}" + "".join(f"{P:>11}" for P in projects) + f"{'mean':>9}{'all 844':>10}")
res = {}
for name in ARMS:
    per = [ba(pred[name], [i for i in ids if PROJ[i] == P]) for P in projects]
    res[name] = {"per_project": dict(zip(projects, per)), "mean": sum(per) / 3, "all": ba(pred[name], ids)}
    say(f"  {name:<26}" + "".join(f"{100 * x:10.1f}%" for x in per) + f"{100 * sum(per) / 3:8.1f}%{100 * ba(pred[name], ids):9.1f}%")
say("\nagainst LO over all 844 (only this arm right / only LO right / exact McNemar p), and per project")
for name in ARMS:
    if name == "LO, as tested":
        continue
    k1, k2, p = mcnemar(pred[name], pred["LO, as tested"], ids)
    perp = []
    for P in projects:
        a, b, q = mcnemar(pred[name], pred["LO, as tested"], [i for i in ids if PROJ[i] == P])
        perp.append(f"{P} {a}/{b} p {q:.2f}")
    say(f"  {name:<26} {k1:3d} / {k2:3d}  p {p:.4f}   ({'; '.join(perp)})")
    res[name]["vs_LO"] = {"k1": k1, "k2": k2, "p": p}

k1, k2, p = mcnemar(pred["LO+SIZE"], pred["SIZE alone"], ids)
say(f"  LO+SIZE against SIZE alone: {k1} / {k2}  p {p:.4f}")
res["LO+SIZE vs SIZE"] = {"k1": k1, "k2": k2, "p": p}
low = [i for i in ids if abs(lam[i] - logodds_tau(ITEMS[i]["domain"])) < LOGODDS_MARGIN]
say(f"  LO on the {len(ids) - len(low)} changes WaRF does not mark LOW: right "
    f"{100 * ba(pred['LO, as tested'], [i for i in ids if i not in low]):.1f}% (balanced)")

say("\nLO's boundary after the first group (jev-1.14 seats)")
st = [i for i in ids if early_stop[i]]
chg = [i for i in st if pred["LO, as tested"][i] != pred["LO-full, no early stop"][i]]
say(f"  stopped early on {len(st)}/{len(ids)}; the full pool decides differently on {len(chg)} of them; "
    f"of those LO is right on {sum(right(pred['LO, as tested'], i) for i in chg)}, LO-full on "
    f"{sum(right(pred['LO-full, no early stop'], i) for i in chg)}")

say("\nLO's errors by distance from the threshold |Lambda - tau| (leave-one-project-out decisions)")
wrong = [i for i in ids if not right(pred["LO, as tested"], i)]
for lo_, hi, label in ((0, LOGODDS_MARGIN, "< ln 2 (WaRF says LOW)"), (LOGODDS_MARGIN, 2.0, "ln 2 .. 2"),
                       (2.0, 99, ">= 2 (confidently wrong)")):
    inb = [i for i in ids if lo_ <= abs(lam[i] - logodds_tau(ITEMS[i]["domain"])) < hi]
    w = [i for i in inb if i in wrong]
    say(f"  {label:<26} {len(inb):4d} changes, {len(w):3d} wrong ({100 * len(w) / max(1, len(inb)):4.1f}%): "
        f"{sum(Y[i] == -1 for i in w)} missed defects, {sum(Y[i] == 1 for i in w)} false alarms")
res["errors"] = {"wrong": len(wrong)}
(HERE / "pooled.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "pooled.json").write_text(json.dumps(res, indent=1))
