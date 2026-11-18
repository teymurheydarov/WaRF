"""Development on the RocksDB matched set (offline, stored answers only; README.md, 2026-11-14 section).

Two levers, both inside WaRF's own calibration:
  T  test files get their own calibration history: a seat reviewing a file under a test directory or
     named *test* is another reviewer (AgentProfile.evidence = "testfile"), so its Platt fit, and with it
     its operating point, is learned from test-file reviews only.
  L  learning on the project's own labels: RocksDB decided by 10-fold cross-validation (5 repeats) with the
     calibration from the other three projects plus the RocksDB training folds, or from the folds only.

    python rdb_dev.py        # writes rdb_dev.log"""
import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP.parent))
from warf.calibration import Calibrator, p_reject_from_text  # noqa: E402
from warf.engine import logodds_boundary, logodds_decision, pool_evidence  # noqa: E402
from warf.orchestrator import _group_key  # noqa: E402
from warf.state import AgentProfile, default_profiles, persona_hash  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


PROJ, ITEMS = {}, {}
for proj, files in (("G+Smo", ("real-set/items.jsonl", "confirm-set/items.jsonl")), ("MFEM", ("mfem-set/items.jsonl",)),
                    ("KeePassXC", ("kpx-set/items.jsonl",)), ("RocksDB", ("rdb-set/items.jsonl",))):
    for f in files:
        for l in (EXP / f).open(encoding="utf-8"):
            r = json.loads(l); ITEMS[r["id"]] = r; PROJ[r["id"]] = proj
Y = {i: (-1 if it["kind"] == "defective" else 1) for i, it in ITEMS.items()}
TEXT = {p.persona_hash: p.persona for p in default_profiles()}


def is_test(path):
    p = path.lower()
    return "/test" in p or p.startswith("test") or "test" in Path(p).name


PERS = {}
for f in ("confirm-set/jev-learned/dev_sessions.jsonl", "confirm-set/jev-learned/sessions_LO.jsonl",
          "mfem-set/sessions_LO.jsonl", "kpx-set/sessions_LO.jsonl", "rdb-set/sessions_LO.jsonl"):
    for l in (EXP / f).open(encoding="utf-8"):
        r = json.loads(l)
        PERS[r["artifact"]] = [(v["agent"], TEXT[v["persona"]], v["model"], p_reject_from_text(v["reasoning"])) for v in r["votes"]]
assert set(PERS) == set(ITEMS)


def seats(i, testfile_split):
    src = "testfile" if testfile_split and is_test(ITEMS[i]["file"]) else ""
    return [{"agent": a, "persona": persona_hash(t), "persona_text": t, "provider": "jev", "model": m,
             "evidence_source": src, "vote": -1 if p >= 0.5 else 1, "p_reject": p} for a, t, m, p in PERS[i]]


def calibrator(train, split):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for i in train:
            votes = [{k: v for k, v in s.items() if k != "persona_text"} for s in seats(i, split)]
            f.write(json.dumps({"oracle": {"type": "DEVELOPER", "x_star": Y[i]}, "votes": votes}) + "\n")
        name = f.name
    cal = Calibrator(Path(name)); Path(name).unlink()
    return cal


def decide(ss, domain, cal):
    order, by = [], {}
    for s in ss:
        g = _group_key(s["provider"], s["model"], None)        # one group per Jev version, as LO
        if g not in by:
            order.append(g); by[g] = []
        by[g].append(s)
    ev = []
    for g in order:
        for s in by[g]:
            prof = AgentProfile(name=s["agent"], persona=s["persona_text"], persona_hash=s["persona"], provider="jev",
                                model=s["model"], evidence=s["evidence_source"] or None)
            ev.append((g, cal.evidence(prof, s["vote"], s["p_reject"], 0.5, "jev", s["model"])[0]))
        lam, means = pool_evidence(ev)
        b = logodds_boundary(lam, means)
        if b is not None:
            return b.value
    lam, means = pool_evidence(ev)
    return logodds_decision(lam, means, domain)[0].value


def run(train, test, split):
    cal = calibrator(train, split)
    return {i: decide(seats(i, split), ITEMS[i]["domain"], cal) for i in test}


def ba(p, ids):
    pos = [i for i in ids if Y[i] == -1]; neg = [i for i in ids if Y[i] == 1]
    return (sum(p[i] == "REJECT" for i in pos) / len(pos) + sum(p[i] == "APPROVE" for i in neg) / len(neg)) / 2


rdb = [i for i in ITEMS if PROJ[i] == "RocksDB"]; other = [i for i in ITEMS if PROJ[i] != "RocksDB"]
say("RocksDB matched set, 800 changes (balanced accuracy)")
for split in (False, True):
    p = run(other, rdb, split)
    tf = [i for i in rdb if is_test(ITEMS[i]["file"])]
    say(f"  calibrated on the other three projects{' + T' if split else '':<5} {100 * ba(p, rdb):5.1f}%"
        f"   (test files {100 * ba(p, tf):.1f}%, others {100 * ba(p, [i for i in rdb if i not in tf]):.1f}%)")
for split in (False, True):
    for with_other in (True, False):
        res = []
        for rep in range(5):
            rng = random.Random(300 + rep)
            P = [i for i in rdb if Y[i] == -1]; Q = [i for i in rdb if Y[i] == 1]; rng.shuffle(P); rng.shuffle(Q)
            F = [P[k::10] + Q[k::10] for k in range(10)]
            pred = {}
            for k in range(10):
                train = [i for f in F[:k] + F[k + 1:] for i in f]
                pred.update(run((other if with_other else []) + train, F[k], split))
            res.append(ba(pred, rdb))
        say(f"  learned on RocksDB folds{' + other projects' if with_other else ' only':<17}{' + T' if split else '':<5}"
            f" {100 * sum(res) / 5:5.1f}%   (repeats {100 * min(res):.1f}-{100 * max(res):.1f})")
(HERE / "rdb_dev.log").write_text("\n".join(out) + "\n", encoding="utf-8")
