"""Sequential (early-stop) vs all-seats log-odds verdicts on the stored 100 commits.
Copies replay.py's data handling; writes nothing into the repo."""
import json, random, sys, tempfile
from pathlib import Path
ROOT = Path(r"C:/workdir/warf/WaRF"); EXP = ROOT / ".warf-experiments"
sys.path.insert(0, str(ROOT))
from warf.calibration import Calibrator
from warf.engine import A, B, Confidence, Decision, logodds_decision, pool_evidence, sprt_boundary
from warf.state import AgentProfile, persona_hash
AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
jl = lambda p: [json.loads(x) for x in Path(p).open(encoding="utf-8")]
sel = jl(EXP / "laya-five" / "selection.jsonl")
one = {r["jev"]["id"]: r["jev"]["round1"]["JEV"]["p_reject"] for r in jl(EXP / "jev-five" / "sessions_one.jsonl")}
five = {r["jev"]["id"]: {a: r["jev"]["round1"][a]["p_reject"] for a in AGENTS} for r in jl(EXP / "jev-five" / "sessions_five.jsonl")}
y = {s["id"]: (-1 if s["label"] == "REJECT" else 1) for s in sel}
dom = {s["id"]: s["domain"] for s in sel}
ids = [s["id"] for s in sel]
SEATS = {"JEV": ("jev", "jev-latest", lambda i: one[i]),
         "LAYA": ("laya", "multilingual", lambda i: next(s["p_single_laya"] for s in sel if s["id"] == i)),
         "CLAUDE": ("claude", "opus-blinded", lambda i: next(s["p_claude"] for s in sel if s["id"] == i))}
for a in AGENTS:
    SEATS[f"JEV-{a}"] = ("jev", "jev-latest", lambda i, a=a: five[i][a])
PROFILE = {n: AgentProfile(name=n, persona=f"seat {n}", persona_hash=persona_hash(f"seat {n}")) for n in SEATS}
rng = random.Random(11); folds = {}
for label in (1, -1):
    m = [i for i in ids if y[i] == label]; rng.shuffle(m)
    for k, i in enumerate(m): folds[i] = k % 5
clamp = lambda p: min(0.99, max(0.01, round(p, 2)))
tmp = Path(tempfile.mkdtemp()) / "log.jsonl"; ev = {}
for k in range(5):
    with tmp.open("w", encoding="utf-8") as f:
        for i in ids:
            if folds[i] == k: continue
            f.write(json.dumps({"session_id": i, "votes": [{"agent": n, "vote": -1 if clamp(p(i)) > .5 else 1, "persona": PROFILE[n].persona_hash, "p_reject": clamp(p(i))} for n, (_, _, p) in SEATS.items()], "oracle": {"type": "DEVELOPER", "x_star": y[i]}}) + "\n")
    cal = Calibrator(tmp)
    for i in ids:
        if folds[i] == k:
            for n, (_, _, p) in SEATS.items():
                ev[i, n] = cal.evidence(PROFILE[n], -1 if clamp(p(i)) > .5 else 1, clamp(p(i)), 0.5)[0]
def verdicts(seats, i):
    items = [(f"{SEATS[n][0]}/{SEATS[n][1]}", ev[i, n]) for n in seats]
    # all seats (replay)
    lam, means = pool_evidence(items)
    d, c, _ = logodds_decision(lam, means, dom[i])
    if lam <= B or lam >= A: d, c = sprt_boundary(lam), Confidence.HIGH
    # sequential, as run_review does
    sd = None; k = 0
    for k in range(1, len(items) + 1):
        l, m = pool_evidence(items[:k])
        b = sprt_boundary(l)
        if b is not None: sd = (b, Confidence.HIGH, k, l); break
    if sd is None:
        l, m = pool_evidence(items); dd, cc, _ = logodds_decision(l, m, dom[i]); sd = (dd, cc, len(items), l)
    return (d, c, lam), sd
for name, seats in (("five Jev personas", [f"JEV-{a}" for a in AGENTS]), ("Jev+Laya+Claude", ["JEV", "LAYA", "CLAUDE"]), ("Claude+Jev+Laya", ["CLAUDE", "JEV", "LAYA"])):
    diff = 0; flips = 0; right_all = right_seq = 0; ex = []
    for i in ids:
        (d, c, lam), (sd, sc, k, sl) = verdicts(seats, i)
        right_all += (d is Decision.REJECT) == (y[i] == -1); right_seq += (sd is Decision.REJECT) == (y[i] == -1)
        if (d, c) != (sd, sc):
            diff += 1; flips += d != sd
            if len(ex) < 3: ex.append((i, d.value, c.value, round(lam, 3), sd.value, sc.value, k, round(sl, 3)))
    print(f"{name}: verdict/confidence differs on {diff}/100 (decision flips {flips}); accuracy all-seats {right_all}, sequential {right_seq}")
    for e in ex: print("   ", e)
