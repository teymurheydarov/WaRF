"""Develop WaRF's log-odds Jev panel (LO, ../confirm-set/README.md fifth test) offline, with no new calls.

WaRF's log-odds decision depends only on each seat's p(REJECT) and the labelled history, so it is
rebuilt here from stored answers with WaRF's own code: warf.calibration.Calibrator (Platt per seat,
read from a session log), warf.orchestrator._group_key / warf.engine.pool_evidence (seats of one
model and input form one group; groups are summed), warf.engine.logodds_boundary (checked after
each complete group, in the order of the groups' first seats) and logodds_decision (domain tau).

  1. Reproduction: calibrate on ../confirm-set/jev-learned/dev_sessions.jsonl and decide the 220
     confirm items from sessions_LO.jsonl's stored answers; must equal WaRF's logged decisions.
  2. Variants, judged by stratified 10-fold cross-validation repeated 5 times over all 352 judged
     items (dev 132 + confirm 220); calibration always from the training folds only.

    python lo_offline.py        # writes lo_offline.log"""
import json
import math
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
from warf.state import AgentProfile, persona_hash  # noqa: E402

sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
from run_narrow import CHECKS, DEFAULT_PERSONA  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


def items_of(path):
    return {json.loads(l)["id"]: json.loads(l) for l in Path(path).open(encoding="utf-8")}


DEV = items_of(EXP / "real-set" / "items.jsonl")
CONF = items_of(EXP / "confirm-set" / "items.jsonl")
ITEMS = {**DEV, **CONF}
Y = {i: (-1 if it["kind"] == "defective" else 1) for i, it in ITEMS.items()}   # x_star: REJECT -1, APPROVE +1


def seat(name, persona, model, source, p):
    p = min(0.99, max(0.01, round(p, 2)))          # WaRF's readout has two decimals
    return {"agent": name, "persona": persona_hash(persona), "persona_text": persona, "provider": "jev",
            "model": model, "evidence_source": source, "vote": -1 if p >= 0.5 else 1, "p_reject": p}


# --- seats from stored answers -------------------------------------------------------------------
def persona_seats():
    """The five persona seats as WaRF logged them: dev from the learning log, confirm from LO's run."""
    from warf.state import default_profiles
    text = {p.persona_hash: p.persona for p in default_profiles()}
    S = {}
    for path, key in ((EXP / "confirm-set" / "jev-learned" / "dev_sessions.jsonl", "artifact"),
                      (EXP / "confirm-set" / "jev-learned" / "sessions_LO.jsonl", "artifact")):
        for l in path.open(encoding="utf-8"):
            r = json.loads(l)
            S[r[key]] = [seat(v["agent"], text[v["persona"]], v["model"], "", p_reject_from_text(v["reasoning"]))
                         for v in r["votes"]]
    return S


def narrow_seats():
    """Per item and version: the usual question on the whole change (seat JEV, same input as the
    personas) and the seven checks, each at its highest p(YES) over the hunks (source 'hunks')."""
    files = {("dev", "jev-1.14"): EXP / "real-set" / "jev-narrow" / "answers.jsonl",
             ("dev", "jev-1.13"): EXP / "real-set" / "jev-narrow" / "versions" / "answers_jev-1.13.jsonl",
             ("conf", "jev-1.14"): EXP / "confirm-set" / "jev-narrow" / "answers.jsonl",
             ("conf", "jev-1.13"): EXP / "confirm-set" / "jev-narrow" / "answers_jev-1.13.jsonl"}
    verdict, checks = {}, {}
    for (_, model), path in files.items():
        whole, hunk = {}, {}
        for l in path.open(encoding="utf-8"):
            r = json.loads(l)
            p = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
            (whole.__setitem__(r["id"], p) if r["state"] == "whole" else hunk.setdefault(r["id"], []).append(p))
        for i in whole:
            verdict.setdefault(i, []).append(seat("JEV", DEFAULT_PERSONA, model, "", whole[i]["verdict"]))
            checks.setdefault(i, []).extend(
                seat(f"CHK-{q}", t, model, "hunks", max((h[q] for h in hunk.get(i, [])), default=whole[i][q]))
                for q, t in CHECKS.items())
    return verdict, checks


PERS = persona_seats()
VERD, CHKS = narrow_seats()
assert set(PERS) == set(ITEMS) == set(VERD) == set(CHKS), "seats missing for some items"


# --- WaRF's log-odds decision ---------------------------------------------------------------------
def profile_of(s):
    return AgentProfile(name=s["agent"], persona=s["persona_text"], persona_hash=s["persona"],
                        provider="jev", model=s["model"], evidence=s["evidence_source"] or None)


def decide(seats, domain, cal, profiles):
    """run_review's log-odds path on stored answers: groups in order of first seat, boundary after
    each complete group, else the domain tau rule."""
    order, by = [], {}
    for s in seats:
        g = _group_key("jev", s["model"], s["evidence_source"] or None)
        if g not in by:
            order.append(g); by[g] = []
        by[g].append(s)
    items = []
    for g in order:
        for s in by[g]:
            e, _ = cal.evidence(profiles[(s["agent"], s["model"], s["evidence_source"])], s["vote"], s["p_reject"],
                                0.5, "jev", s["model"])
            items.append((g, e))
        lam, means = pool_evidence(items)
        b = logodds_boundary(lam, means)
        if b is not None:
            return b.value
    lam, means = pool_evidence(items)
    return logodds_decision(lam, means, domain)[0].value


def calibrator(train_ids, config):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for i in train_ids:
            votes = [{k: v for k, v in s.items() if k != "persona_text"} for s in config(i)]
            f.write(json.dumps({"oracle": {"type": "DEVELOPER", "x_star": Y[i]}, "votes": votes}) + "\n")
        name = f.name
    cal = Calibrator(Path(name))
    Path(name).unlink()
    return cal


def run(config, train_ids, test_ids):
    cal = calibrator(train_ids, config)
    profiles = {}
    for i in test_ids:
        for s in config(i):
            profiles.setdefault((s["agent"], s["model"], s["evidence_source"]), profile_of(s))
    return {i: decide(config(i), ITEMS[i]["domain"], cal, profiles) for i in test_ids}


def ba(pred, ids):
    pos = [i for i in ids if Y[i] == -1]; neg = [i for i in ids if Y[i] == 1]
    return (sum(pred[i] == "REJECT" for i in pos) / len(pos) + sum(pred[i] == "APPROVE" for i in neg) / len(neg)) / 2


# --- 1. reproduction ------------------------------------------------------------------------------
lo_logged = {json.loads(l)["artifact"]: json.loads(l)["decision"]
             for l in (EXP / "confirm-set" / "jev-learned" / "sessions_LO.jsonl").open(encoding="utf-8")}
cal = Calibrator(EXP / "confirm-set" / "jev-learned" / "dev_sessions.jsonl")
profiles = {(s["agent"], s["model"], ""): profile_of(s) for s in PERS[next(iter(CONF))]}
mine = {i: decide(PERS[i], CONF[i]["domain"], cal, profiles) for i in CONF}
same = sum(mine[i] == lo_logged[i] for i in CONF)
say(f"reproduction of LO on the 220 confirm items: {same}/220 decisions equal WaRF's; BA {100 * ba(mine, list(CONF)):.1f}%")
if same != 220:
    raise SystemExit("the offline rebuild does not match WaRF; stop")

# --- 2. variants under cross-validation ------------------------------------------------------------
V14 = lambda i: [s for s in VERD[i] if s["model"] == "jev-1.14"]
CONFIGS = {
    "LO: 5 personas (as tested)":                      lambda i: PERS[i],
    "LO + usual question on both versions":            lambda i: PERS[i] + VERD[i],
    "LO + narrow checks of both versions (own source)": lambda i: PERS[i] + CHKS[i],
    "LO + usual question + narrow checks":             lambda i: PERS[i] + VERD[i] + CHKS[i],
    "narrow checks of both versions only":             lambda i: CHKS[i],
    "one Jev seat (usual question, jev-1.14)":         V14,
}
ids = list(ITEMS)
pos = [i for i in ids if Y[i] == -1]; neg = [i for i in ids if Y[i] == 1]
res = {k: [] for k in CONFIGS}
for rep in range(5):
    rng = random.Random(100 + rep)
    P, Q = pos[:], neg[:]; rng.shuffle(P); rng.shuffle(Q)
    folds = [P[k::10] + Q[k::10] for k in range(10)]
    pred = {k: {} for k in CONFIGS}
    for k in range(10):
        test = folds[k]; train = [i for f in folds[:k] + folds[k + 1:] for i in f]
        for name, cfg in CONFIGS.items():
            pred[name].update(run(cfg, train, test))
    for name in CONFIGS:
        res[name].append(ba(pred[name], ids))
say("\ncross-validated balanced accuracy, 352 items (10 folds x 5 repeats; calibration from training folds only)")
for name, r in res.items():
    say(f"  {name:<50} {100 * sum(r) / len(r):5.1f}%   (repeats {min(r) * 100:.1f}-{max(r) * 100:.1f})")
say("\nfor information only (another look at the confirm set): calibrate on dev, decide confirm")
for name, cfg in CONFIGS.items():
    say(f"  {name:<50} {100 * ba(run(cfg, list(DEV), list(CONF)), list(CONF)):5.1f}%")
(HERE / "lo_offline.log").write_text("\n".join(out) + "\n", encoding="utf-8")
