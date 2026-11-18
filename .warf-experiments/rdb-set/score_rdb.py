"""Score the preregistered RocksDB test (README.md), written before any Jev call on this set.

    python score_rdb.py      # writes score.log, score.json"""
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
from warf.engine import logodds_boundary, logodds_decision, pool_evidence  # noqa: E402
from warf.orchestrator import _group_key  # noqa: E402
from warf.state import AgentProfile, default_profiles, persona_hash  # noqa: E402

sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
from run_narrow import DEFAULT_PERSONA  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


items = {json.loads(l)["id"]: json.loads(l) for l in (HERE / "items.jsonl").open(encoding="utf-8")}
ids = list(items)
D = {i: items[i]["kind"] == "defective" for i in ids}
pos = [i for i in ids if D[i]]; neg = [i for i in ids if not D[i]]
TEXT = {p.persona_hash: p.persona for p in default_profiles()}

lo = {}
for l in (HERE / "sessions_LO.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    if r["jev"]["id"] in lo:
        raise SystemExit(f"LO {r['jev']['id']} twice")
    lo[r["jev"]["id"]] = r
if set(lo) != set(ids):
    raise SystemExit(f"{len(set(ids) - set(lo))} LO reviews missing")
v1p = {}
for l in (HERE / "answers_V1.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    if r["state"] == "whole":
        if r["id"] in v1p:
            raise SystemExit(f"V1 {r['id']} twice")
        v1p[r["id"]] = min(0.99, max(0.01, round((r["answers"]["verdict"]["p"] or {}).get("REJECT", 0.0), 2)))
if set(v1p) != set(ids):
    raise SystemExit(f"{len(set(ids) - set(v1p))} one-Jev answers missing")


def seat(agent, persona, provider, model, p):
    return {"agent": agent, "persona": persona_hash(persona), "persona_text": persona, "provider": provider,
            "model": model, "vote": -1 if p >= 0.5 else 1, "p_reject": p}


PERS = {i: [seat(v["agent"], TEXT[v["persona"]], "jev", v["model"], p_reject_from_text(v["reasoning"]))
            for v in lo[i]["votes"]] for i in ids}
SIZE = {i: [seat("SIZE", SIZE_TEXT, "size", "", size_p(items[i]["code"]))] for i in ids}


def decide(seats, domain, cal):
    """run_review's log-odds path on stored answers (as ../lo-dev/lo_offline.py)."""
    order, by = [], {}
    for s in seats:
        g = _group_key(s["provider"], s["model"], None)
        if g not in by:
            order.append(g); by[g] = []
        by[g].append(s)
    ev = []
    for g in order:
        for s in by[g]:
            prof = AgentProfile(name=s["agent"], persona=s["persona_text"], persona_hash=s["persona"],
                                provider=s["provider"], model=s["model"], evidence=None)
            ev.append((g, cal.evidence(prof, s["vote"], s["p_reject"], 0.5, s["provider"], s["model"])[0]))
        lam, means = pool_evidence(ev)
        b = logodds_boundary(lam, means)
        if b is not None:
            return b.value
    lam, means = pool_evidence(ev)
    return logodds_decision(lam, means, domain)[0].value


def merged_calibrator(*paths):
    """One session log holding, per training change, the persona seats' and the size seat's votes."""
    rows = {}
    for p in paths:
        for l in Path(p).open(encoding="utf-8"):
            r = json.loads(l)
            rows.setdefault(r["artifact"], {"oracle": r["oracle"], "votes": []})["votes"].extend(r["votes"])
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for r in rows.values():
            f.write(json.dumps(r) + "\n")
        name = f.name
    cal = Calibrator(Path(name)); Path(name).unlink()
    return cal


cal_lo = Calibrator(HERE / "calib_sessions.jsonl")
same = sum(decide(PERS[i], items[i]["domain"], cal_lo) == lo[i]["decision"] for i in ids)
cal_los = merged_calibrator(HERE / "calib_sessions.jsonl", HERE / "calib_size.jsonl")
cal_size = Calibrator(HERE / "calib_size.jsonl")
cal_v1 = Calibrator(HERE / "calib_V1.jsonl")
pred = {"V1": {i: decide([seat("JEV", DEFAULT_PERSONA, "jev", "jev-1.14", v1p[i])], items[i]["domain"], cal_v1) == "REJECT"
               for i in ids},
        "SIZE": {i: decide(SIZE[i], items[i]["domain"], cal_size) == "REJECT" for i in ids},
        "LO": {i: lo[i]["decision"] == "REJECT" for i in ids},
        "LO+SIZE": {i: decide(PERS[i] + SIZE[i], items[i]["domain"], cal_los) == "REJECT" for i in ids}}


def ba(p):
    return (sum(p[i] for i in pos) / len(pos) + sum(not p[i] for i in neg) / len(neg)) / 2


def vs(a, b):
    k1 = sum(pred[a][i] == D[i] and pred[b][i] != D[i] for i in ids)
    k2 = sum(pred[b][i] == D[i] and pred[a][i] != D[i] for i in ids)
    n = k1 + k2
    p = 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, j) for j in range(min(k1, k2) + 1)) / 2 ** n)
    return ba(pred[a]) - ba(pred[b]), k1, k2, p


cost = sum(r["jev"]["cost"] for r in lo.values()) + sum(
    float((json.loads(l).get("usage") or {}).get("cost") or 0) for l in (HERE / "answers_V1.jsonl").open(encoding="utf-8"))
say(f"{len(ids)} RocksDB items ({len(pos)} defective, {len(neg)} clean); Jev cost ${cost:.3f}")
say(f"offline rebuild of LO: {same}/{len(ids)} decisions equal WaRF's logged ones")
if same != len(ids):
    raise SystemExit("the offline rebuild does not match WaRF; stop")
for name in ("V1", "SIZE", "LO", "LO+SIZE"):
    p = pred[name]
    say(f"  {name:<8} right {100 * ba(p):5.1f}%  caught {sum(p[i] for i in pos)}/{len(pos)}  false alarms {sum(p[i] for i in neg)}/{len(neg)}")
d, k1, k2, p = vs("LO+SIZE", "LO")
verdict = "LO+SIZE WINS" if d > 0 and p < 0.05 else "not shown" if d > 0 else "no case"
say(f"\nPRIMARY  LO+SIZE - LO: {100 * d:+.1f} points; only LO+SIZE right {k1}, only LO right {k2}; exact McNemar p {p:.4f} -> {verdict}")
res = {"primary": {"d": d, "only_LO+SIZE": k1, "only_LO": k2, "p": p, "verdict": verdict},
       "ba": {k: ba(v) for k, v in pred.items()}, "rebuild_same": same}
for a, b in (("LO+SIZE", "SIZE"), ("LO", "V1"), ("LO+SIZE", "V1")):
    d2, j1, j2, p2 = vs(a, b)
    say(f"secondary {a} - {b}: {100 * d2:+.1f} points; {j1} vs {j2}; McNemar p {p2:.4f}")
    res[f"{a} - {b}"] = {"d": d2, "a": j1, "b": j2, "p": p2}
vis = [i for i in pos if items[i].get("visible") == "diff"]
say(f"secondary, the {len(vis)} defects visible from the diff (with all clean items):")
for name in ("V1", "LO", "LO+SIZE"):
    pp = pred[name]
    r = (sum(pp[i] for i in vis) / len(vis) + sum(not pp[i] for i in neg) / len(neg)) / 2
    say(f"  {name:<8} right {100 * r:5.1f}%  caught {sum(pp[i] for i in vis)}/{len(vis)}")
(HERE / "score.log").write_text("\n".join(out) + "\n", encoding="utf-8")
(HERE / "score.json").write_text(json.dumps(res, indent=1))
