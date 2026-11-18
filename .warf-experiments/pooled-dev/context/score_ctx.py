"""Score run_ctx.py's states on the RocksDB matched set (development).

  1. Ranking: AUC of the verdict p and of the compile p per state; paired stratified bootstrap of the
     difference to `plain` (2000 resamples).
  2. One seat in WaRF: the verdict as a calibrated WaRF seat, 10-fold x 5 cross-validation within RocksDB.
  3. Added to LO: LO's five seats plus the new seat as its own group (evidence source = the state),
     WaRF's Calibrator / pool_evidence / boundary / tau, calibration from the RocksDB training folds plus
     the other three projects' LO seats.

    python score_ctx.py      # writes score_ctx.log"""
import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
from warf.calibration import Calibrator, p_reject_from_text  # noqa: E402
from warf.engine import logodds_boundary, logodds_decision, pool_evidence  # noqa: E402
from warf.orchestrator import _group_key  # noqa: E402
from warf.state import AgentProfile, default_profiles, persona_hash  # noqa: E402

sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
from run_narrow import DEFAULT_PERSONA  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


ITEMS, PROJ = {}, {}
for proj, files in (("G+Smo", ("real-set/items.jsonl", "confirm-set/items.jsonl")), ("MFEM", ("mfem-set/items.jsonl",)),
                    ("KeePassXC", ("kpx-set/items.jsonl",)), ("RocksDB", ("rdb-set/items.jsonl",))):
    for f in files:
        for l in (EXP / f).open(encoding="utf-8"):
            r = json.loads(l); ITEMS[r["id"]] = r; PROJ[r["id"]] = proj
Y = {i: (-1 if it["kind"] == "defective" else 1) for i, it in ITEMS.items()}
rdb = [i for i in ITEMS if PROJ[i] == "RocksDB"]; other = [i for i in ITEMS if PROJ[i] != "RocksDB"]
pos = [i for i in rdb if Y[i] == -1]; neg = [i for i in rdb if Y[i] == 1]

S = {}
ANSWERS = [HERE / "answers.jsonl"] + [Path(x) for x in sys.argv[1:]]     # more answer files: extra states
for l in (l for f in ANSWERS for l in f.open(encoding="utf-8")):
    r = json.loads(l)
    S.setdefault(r["state"], {})[r["id"]] = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0)
                                             for q, v in r["answers"].items()}
states = [s for s in ("plain", "ctx", "commit", "both", "prof", "prof_ctx") if s in S]
for s in states:
    if set(S[s]) != set(rdb):
        raise SystemExit(f"state {s}: {len(set(rdb) - set(S[s]))} answers missing")


def auc(sc, P=pos, N=neg):
    """Mann-Whitney AUC from mid-ranks (ties count one half); P and N may repeat items."""
    vals = sorted([(sc[i], 1) for i in P] + [(sc[i], 0) for i in N])
    rank_sum, k = 0.0, 0
    while k < len(vals):
        j = k
        while j < len(vals) and vals[j][0] == vals[k][0]:
            j += 1
        mid = (k + 1 + j) / 2
        rank_sum += mid * sum(v[1] for v in vals[k:j])
        k = j
    return (rank_sum - len(P) * (len(P) + 1) / 2) / (len(P) * len(N))


say("1. Ranking on 800 RocksDB changes (AUC; difference to plain with a 95% bootstrap interval)")
rng = random.Random(7)
boots = [([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]) for _ in range(2000)]
for q in ("verdict", "compile"):
    base = {i: S["plain"][i][q] for i in rdb}
    for s in states:
        sc = {i: S[s][i][q] for i in rdb}
        line = f"  {q:<8} {s:<7} AUC {auc(sc):.3f}"
        if s != "plain":
            d = sorted(auc(sc, P, N) - auc(base, P, N) for P, N in boots)
            line += f"   vs plain {auc(sc) - auc(base):+.3f} [{d[50]:+.3f}, {d[1949]:+.3f}]"
        say(line)

TEXT = {p.persona_hash: p.persona for p in default_profiles()}
PERS = {}
for f in ("confirm-set/jev-learned/dev_sessions.jsonl", "confirm-set/jev-learned/sessions_LO.jsonl",
          "mfem-set/sessions_LO.jsonl", "kpx-set/sessions_LO.jsonl", "rdb-set/sessions_LO.jsonl"):
    for l in (EXP / f).open(encoding="utf-8"):
        r = json.loads(l)
        PERS[r["artifact"]] = [{"agent": v["agent"], "persona": v["persona"], "persona_text": TEXT[v["persona"]],
                                "provider": "jev", "model": v["model"], "evidence_source": "",
                                "p_reject": p_reject_from_text(v["reasoning"])} for v in r["votes"]]


def seat_new(i, s):
    p = min(0.99, max(0.01, round(S[s][i]["verdict"], 2)))
    return {"agent": "JEV", "persona": persona_hash(DEFAULT_PERSONA), "persona_text": DEFAULT_PERSONA, "provider": "jev",
            "model": "jev-1.14", "evidence_source": s, "p_reject": p}


def with_vote(ss):
    return [{**x, "vote": -1 if x["p_reject"] >= 0.5 else 1} for x in ss]


def calibrator(train, cfg):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for i in train:
            votes = [{k: v for k, v in x.items() if k != "persona_text"} for x in with_vote(cfg(i))]
            f.write(json.dumps({"oracle": {"type": "DEVELOPER", "x_star": Y[i]}, "votes": votes}) + "\n")
        name = f.name
    cal = Calibrator(Path(name)); Path(name).unlink()
    return cal


def decide(ss, domain, cal):
    order, by = [], {}
    for x in with_vote(ss):
        g = _group_key(x["provider"], x["model"], x["evidence_source"] or None)
        if g not in by:
            order.append(g); by[g] = []
        by[g].append(x)
    ev = []
    for g in order:
        for x in by[g]:
            prof = AgentProfile(name=x["agent"], persona=x["persona_text"], persona_hash=x["persona"], provider="jev",
                                model=x["model"], evidence=x["evidence_source"] or None)
            ev.append((g, cal.evidence(prof, x["vote"], x["p_reject"], 0.5, "jev", x["model"])[0]))
        lam, means = pool_evidence(ev)
        b = logodds_boundary(lam, means)
        if b is not None:
            return b.value
    lam, means = pool_evidence(ev)
    return logodds_decision(lam, means, domain)[0].value


def ba(p, ids):
    P = [i for i in ids if Y[i] == -1]; N = [i for i in ids if Y[i] == 1]
    return (sum(p[i] == "REJECT" for i in P) / len(P) + sum(p[i] == "APPROVE" for i in N) / len(N)) / 2


def cv(cfg, extra_train=()):
    res = []
    for rep in range(5):
        r = random.Random(300 + rep)
        P, N = pos[:], neg[:]; r.shuffle(P); r.shuffle(N)
        F = [P[k::10] + N[k::10] for k in range(10)]
        pred = {}
        for k in range(10):
            train = [i for f in F[:k] + F[k + 1:] for i in f]
            cal = calibrator(list(extra_train) + train, cfg)
            pred.update({i: decide(cfg(i), ITEMS[i]["domain"], cal) for i in F[k]})
        res.append(ba(pred, rdb))
    return sum(res) / 5, min(res), max(res)


say("\n2. One Jev seat in WaRF, calibrated on RocksDB folds (10-fold x 5)")
for s in states:
    m, a, b = cv(lambda i, s=s: [seat_new(i, s)])
    say(f"  {s:<7} {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
say("\n3. LO's five seats + the new seat as its own group; calibration: other projects' LO seats + RocksDB folds")
m, a, b = cv(lambda i: PERS[i], other)
say(f"  LO alone        {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
for s in states:
    m, a, b = cv(lambda i, s=s: PERS[i] + ([seat_new(i, s)] if i in S[s] else []), other)
    say(f"  LO + {s:<10} {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})")
(HERE / ("score_ctx.log" if len(ANSWERS) == 1 else "score_ctx_more.log")).write_text("\n".join(out) + "\n", encoding="utf-8")
