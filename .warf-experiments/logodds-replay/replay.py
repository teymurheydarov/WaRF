"""Replay the 100 gismo6 commits through WaRF's log-odds mode (warf.calibration, warf.engine).

Stored answers only; no model is asked. Calibration is out of fold: each commit is scored with
calibrators fitted on the labels of the other folds (5 folds, stratified, seeded), written as a
temporary session log in exactly the format WaRF reads. Claude's stored p (a blinded batch review)
stands in for a decision-style seat; a live Claude seat would be a text agent.

    python .warf-experiments/logodds-replay/replay.py"""
import json
import math
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from warf.calibration import Calibrator  # noqa: E402
from warf.engine import A, B, Confidence, Decision, logodds_decision, pool_evidence, vote_evidence  # noqa: E402
from warf.state import AgentProfile, persona_hash  # noqa: E402

AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
out = []


def say(s=""):
    out.append(s)
    print(s)


def jl(p):
    return [json.loads(x) for x in Path(p).open(encoding="utf-8")]


sel = jl(HERE.parent / "laya-five" / "selection.jsonl")
one = {r["jev"]["id"]: r["jev"]["round1"]["JEV"]["p_reject"] for r in jl(HERE.parent / "jev-five" / "sessions_one.jsonl")}
five = {r["jev"]["id"]: {a: r["jev"]["round1"][a]["p_reject"] for a in AGENTS}
        for r in jl(HERE.parent / "jev-five" / "sessions_five.jsonl")}
y = {s["id"]: (-1 if s["label"] == "REJECT" else 1) for s in sel}      # +1 never fixed (clean)
dom = {s["id"]: s["domain"] for s in sel}
ids = [s["id"] for s in sel]

# Seats: name -> (provider/model group, p(REJECT) per commit)
SEATS = {
    "JEV":    ("jev", "jev-latest", lambda i: one[i]),
    "LAYA":   ("laya", "multilingual", lambda i: next(s["p_single_laya"] for s in sel if s["id"] == i)),
    "CLAUDE": ("claude", "opus-blinded", lambda i: next(s["p_claude"] for s in sel if s["id"] == i)),
}
for a in AGENTS:
    SEATS[f"JEV-{a}"] = ("jev", "jev-latest", lambda i, a=a: five[i][a])
PROFILE = {n: AgentProfile(name=n, persona=f"seat {n}", persona_hash=persona_hash(f"seat {n}")) for n in SEATS}

rng = random.Random(11)
folds = {}
for label in (1, -1):
    members = [i for i in ids if y[i] == label]
    rng.shuffle(members)
    for k, i in enumerate(members):
        folds[i] = k % 5


def clamp(p):
    return min(0.99, max(0.01, round(p, 2)))    # what WaRF reads from the two-decimal readout


def write_log(train_ids, path):
    with path.open("w", encoding="utf-8") as f:
        for i in train_ids:
            votes = []
            for n, (_, _, p) in SEATS.items():
                pr = clamp(p(i))
                votes.append({"agent": n, "vote": -1 if pr > 0.5 else 1, "persona": PROFILE[n].persona_hash, "provider": SEATS[n][0], "model": SEATS[n][1],
                              "p_reject": pr})
            f.write(json.dumps({"session_id": i, "votes": votes,
                                "oracle": {"type": "DEVELOPER", "x_star": y[i]}}) + "\n")


def evidence_table():
    """Out-of-fold evidence and calibration tag for every seat on every commit."""
    tmp = Path(tempfile.mkdtemp(prefix="warf-replay-")) / "log.jsonl"
    ev = {}
    for k in range(5):
        write_log([i for i in ids if folds[i] != k], tmp)
        cal = Calibrator(tmp)
        for i in (i for i in ids if folds[i] == k):
            for n, (prov, model, p) in SEATS.items():
                pr = clamp(p(i))
                ev[i, n] = cal.evidence(PROFILE[n], -1 if pr > 0.5 else 1, pr, 0.5, prov, model)
    return ev


def auc(score, pos):
    pairs = [(s, t) for s, t in zip(score, pos)]
    P = [s for s, t in pairs if t]
    N = [s for s, t in pairs if not t]
    return sum((p > n) + 0.5 * (p == n) for p in P for n in N) / (len(P) * len(N))


def evaluate(name, seats, ev):
    lam, dec, conf = {}, {}, {}
    for i in ids:
        items = [(f"{SEATS[n][0]}/{SEATS[n][1]}", ev[i, n][0]) for n in seats]
        lam[i], means = pool_evidence(items)
        d, c, _ = logodds_decision(lam[i], means, dom[i])
        if lam[i] <= B or lam[i] >= A:      # all seats voted; a sequential review may stop earlier
            d, c = (Decision.REJECT if lam[i] <= B else Decision.APPROVE), Confidence.HIGH
        dec[i], conf[i] = d, c
    pos = [y[i] == -1 for i in ids]
    a = auc([-lam[i] for i in ids], pos)
    rec_def = sum(dec[i] is Decision.REJECT for i in ids if y[i] == -1) / 50
    rec_cln = sum(dec[i] is Decision.APPROVE for i in ids if y[i] == 1) / 50
    bands = {}
    for i in ids:
        right = (dec[i] is Decision.REJECT) == (y[i] == -1)
        n, k = bands.get(conf[i].value, (0, 0))
        bands[conf[i].value] = (n + 1, k + right)
    tags = sorted({ev[i, n][1] for i in ids for n in seats})
    say(f"  {name:<34} AUC {a:.3f}   BA {(rec_def + rec_cln) / 2:.3f}   "
        + "  ".join(f"{b} {k}/{n}" for b, (n, k) in sorted(bands.items())) + f"   [{', '.join(tags)}]")
    return a


ev = evidence_table()
say("Out-of-fold log-odds mode on the 100 commits (later fixed = REJECT); AUC of -Λ, balanced accuracy")
say("of the verdict, right/total per confidence band, calibration tags used.\n")
evaluate("Jev alone", ["JEV"], ev)
evaluate("Laya alone", ["LAYA"], ev)
evaluate("Claude alone", ["CLAUDE"], ev)
evaluate("five Jev personas (one model)", [f"JEV-{a}" for a in AGENTS], ev)
evaluate("Jev + Laya", ["JEV", "LAYA"], ev)
evaluate("Jev + Claude", ["JEV", "CLAUDE"], ev)
evaluate("Jev + Laya + Claude", ["JEV", "LAYA", "CLAUDE"], ev)

say("\nFor reference, vote mode (uniform ω, every seat votes at p > 0.5):")
for name, seats in (("Jev + Laya + Claude, votes", ["JEV", "LAYA", "CLAUDE"]),):
    lam = {i: sum(vote_evidence(-1 if clamp(SEATS[n][2](i)) > 0.5 else 1, 0.5) for n in seats) for i in ids}
    say(f"  {name:<34} AUC {auc([-lam[i] for i in ids], [y[i] == -1 for i in ids]):.3f}")

(HERE / "replay.log").write_text("\n".join(out) + "\n", encoding="utf-8")
