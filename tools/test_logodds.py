"""
Log-odds aggregation test (docs/spec/logodds-aggregation.md, section 9).

Pure checks of the evidence, pooling and calibration rules, then one review
through run_review with the agent call stubbed out. No model, no network, no
credentials; the profiles and the session log live in a temporary directory.

Usage:  python tools/test_logodds.py
"""
import json
import math
import os
import random
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_HOME = tempfile.mkdtemp(prefix="warf-logodds-")
os.environ["WARF_HOME"] = _HOME
os.environ["WARF_NO_BROWSER"] = "1"

from warf import orchestrator  # noqa: E402
from warf.engine import (  # noqa: E402
    A, B, LLR_APPROVE, LLR_REJECT, Decision, Confidence,
    logodds_tau, pool_evidence, logodds_decision, capped_evidence,
)
from warf.calibration import (  # noqa: E402
    Calibrator, fit_platt, p_reject_from_text,
)
from warf.logger import session_dict  # noqa: E402
from warf.state import AgentProfile, load_profiles, persona_hash, save_profiles  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


def close(x, y, tol=1e-9):
    return abs(x - y) <= tol


def logit(q):
    return math.log(q / (1 - q))


def readout(p_reject):
    """WaRF's own rendering of a decision-model answer (providers.SystemOneProvider)."""
    choice = "REJECT" if p_reject > 0.5 else "APPROVE"
    return (f"{choice}\np(APPROVE)={1 - p_reject:.2f}  p(REJECT)={p_reject:.2f}  "
            f"confidence=0.50  [jev-test: decision model, no reasoning]")


# Which model each test agent runs on; calibration only uses votes cast by the same model.
MODEL_OF = {"AUDITOR": ("claude_cli", "haiku"), "JEV": ("jev", "jev-latest"), "LAYA": ("laya", "multilingual")}


def labelled_session(agent, persona, vote, y, reasoning=""):
    provider, model = MODEL_OF.get(agent, ("", ""))
    return {
        "session_id": f"s-{random.random()}", "domain": "LOGIC",
        "votes": [{"agent": agent, "vote": vote, "persona": persona, "reasoning": reasoning,
                   "provider": provider, "model": model}],
        "oracle": {"type": "DEVELOPER", "x_star": y},
    }


def write_log(path, sessions):
    path.write_text("".join(json.dumps(s) + "\n" for s in sessions), encoding="utf-8")


print("\n=== evidence, pooling and decision ===")

# 1. Seats of one model count once.
one_model = [("claude_cli/haiku", 0.5 * LLR_REJECT)] * 5
lam, groups = pool_evidence(one_model)
check(close(lam, 0.5 * LLR_REJECT), f"five REJECTs of one model pool to {lam:.3f} (one vote's worth)")
decision, confidence, _ = logodds_decision(lam, groups, "LOGIC")
check(decision is Decision.REJECT and confidence is Confidence.LOW,
      f"-> {decision.value} [{confidence.value}]: 0.627 nats is under the ln 2 margin")

# 2. Different models add up.
lam, _ = pool_evidence([("jev/jev-latest", 0.5 * LLR_REJECT), ("laya/multilingual", 0.5 * LLR_REJECT)])
check(close(lam, LLR_REJECT), f"one REJECT from each of two models sums to {lam:.3f}")

# 3. An uncalibrated decision agent is capped at its vote-mode step.
check(close(capped_evidence(logit(0.01), 0.5), 0.5 * LLR_REJECT), "p(REJECT)=0.99 is capped at ω·LLR_REJECT")
check(close(capped_evidence(logit(0.99), 0.5), 0.5 * LLR_APPROVE), "p(REJECT)=0.01 is capped at ω·LLR_APPROVE")
check(close(capped_evidence(logit(0.4), 0.5), logit(0.4)), "p(REJECT)=0.6 stays at logit(0.4) inside the cap")

# 8. The domain threshold.
check(close(logodds_tau("SECURITY"), logit(0.6)) and logodds_tau("LOGIC") == 0.0
      and close(logodds_tau("PERFORMANCE"), logit(0.45)), "τ = logit((1 + θ)/2) per domain")

# 9. Models that disagree send the change to a human.
lam, groups = pool_evidence([("a/x", 1.0), ("b/y", -1.2)])
decision, confidence, norm = logodds_decision(lam, groups, "LOGIC")
check(confidence is Confidence.LOW, f"means +1.0 and -1.2 -> {decision.value} [{confidence.value}]")
check(close(norm, 2 / (1 + math.exp(-lam)) - 1), "normalised score is 2σ(Λ−τ)−1")

lam, groups = pool_evidence([("a/x", -1.5), ("b/y", -1.2)])
check(logodds_decision(lam, groups, "LOGIC")[1] is Confidence.MEDIUM, "agreeing models with a clear margin -> MEDIUM")
check(logodds_decision(0.5, {"a/x": 0.5}, "LOGIC")[1] is Confidence.LOW, "a margin under ln 2 -> LOW")

print("\n=== reading a decision model's probability ===")
check(p_reject_from_text(readout(0.88)) == 0.88, "p(REJECT) is read from the decision readout")
check(p_reject_from_text("REJECT\nI estimate p(REJECT)=0.88 here.") is None, "never from a text agent's prose")
check(p_reject_from_text(readout(1.0)) == 0.99 and p_reject_from_text(readout(0.0)) == 0.01,
      "clamped to [0.01, 0.99]")

print("\n=== calibration ===")
rng = random.Random(7)

# 5. The fit recovers the slope of a reviewer that is informative but overconfident.
rs = [rng.uniform(-4, 4) for _ in range(600)]
ys = [1 if rng.random() < 1 / (1 + math.exp(-0.5 * r)) else -1 for r in rs]
fit = fit_platt(rs, ys)
check(fit is not None and abs(fit.b - 0.5) < 0.15, f"fitted slope {fit.b:.3f} ≈ 0.5")

# 4. An uninformative reviewer on an 80 % clean history gives no evidence.
rs = [rng.uniform(-4, 4) for _ in range(300)]
ys = [1 if rng.random() < 0.8 else -1 for _ in rs]
fit = fit_platt(rs, ys)
worst = max(abs(fit.evidence(r)) for r in (-4.0, 0.0, 4.0))
check(worst < 0.3, f"base rate removed: |evidence| ≤ {worst:.3f} for any p")

persona = "Should this change be merged?"
ph = persona_hash(persona)
jev = AgentProfile(name="JEV", persona=persona, provider="jev", model="jev-latest", persona_hash=ph)
text_persona = "Review strictly."
th = persona_hash(text_persona)
auditor = AgentProfile(name="AUDITOR", persona=text_persona, provider="claude_cli", model="haiku",
                       persona_hash=th)

# 6. Text-agent rates; 7. retired persona votes are ignored.
log = Path(_HOME) / "calib.jsonl"
sessions = []
sessions += [labelled_session("AUDITOR", th, -1, -1) for _ in range(9)]
sessions += [labelled_session("AUDITOR", th, +1, -1) for _ in range(1)]
sessions += [labelled_session("AUDITOR", th, -1, +1) for _ in range(1)]
sessions += [labelled_session("AUDITOR", th, +1, +1) for _ in range(9)]
sessions += [labelled_session("AUDITOR", "retired0000", +1, -1) for _ in range(50)]
write_log(log, sessions)
cal = Calibrator(log)
e, tag = cal.evidence(auditor, -1, None, 0.5, "claude_cli", "haiku")
expected = math.log(((1 + 1) / (10 + 2)) / ((9 + 1) / (10 + 2)))
check(tag == "rates" and close(e, expected), f"REJECT evidence {e:.3f} = ln 0.2 from the measured rates")
check(cal.history_size(auditor, "claude_cli", "haiku") == 20, "the 50 votes of a retired persona are not used")

# A decision agent needs 10 labelled votes of each class before its p is trusted.
sessions = [labelled_session("JEV", ph, -1, -1, readout(0.9)) for _ in range(9)]
sessions += [labelled_session("JEV", ph, +1, +1, readout(0.1)) for _ in range(10)]
write_log(log, sessions)
e, tag = Calibrator(log).evidence(jev, -1, 0.99, 0.5, "jev", "jev-latest")
check(tag == "capped" and close(e, 0.5 * LLR_REJECT), "9 defective labels: still capped")
sessions.append(labelled_session("JEV", ph, -1, -1, readout(0.9)))
write_log(log, sessions)
e, tag = Calibrator(log).evidence(jev, -1, 0.9, 0.5, "jev", "jev-latest")
check(tag == "platt" and e < 0, f"10 of each: calibrated, p(REJECT)=0.9 -> evidence {e:.3f}")

e, tag = Calibrator(Path(_HOME) / "missing.jsonl").evidence(jev, -1, 0.9, 0.5, "jev", "jev-latest")
check(tag == "capped", "a missing log leaves every agent uncalibrated")

print("\n=== run_review ===")
profiles_path = Path(_HOME) / "panel.json"
panel = [AgentProfile(name=f"S{i}", persona=f"Persona {i}.", provider="claude_cli", model="haiku",
                      persona_hash=persona_hash(f"Persona {i}.")) for i in range(5)]
save_profiles(profiles_path, panel)

calls = []


def stub_reject(persona, code, domain, **kw):
    calls.append(persona)
    return -1, "looks wrong", 10, 5, kw.get("provider") or "claude_cli", kw.get("model") or "haiku"


orchestrator._call_agent = stub_reject
empty_log = Path(_HOME) / "empty.jsonl"

# 12. vote mode is unchanged: five REJECTs at ω 0.5 cross B at the fourth vote.
r = orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False)
check(r.decision is Decision.REJECT and r.confidence is Confidence.HIGH and len(r.votes) == 4
      and close(r.sprt_lambda, 4 * 0.5 * LLR_REJECT, 1e-12), "vote mode: REJECT [HIGH] after 4 votes, as before")

# 11. logodds mode: the same five seats are one model -> one vote's worth.
calls.clear()
r = orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False,
                            aggregate="logodds", log_path=empty_log)
check(len(calls) == 5 and r.decision is Decision.REJECT and r.confidence is Confidence.LOW,
      f"logodds: all 5 asked, {r.decision.value} [{r.confidence.value}]")
check(close(r.sprt_lambda, 0.5 * LLR_REJECT, 1e-12), f"Λ = {r.sprt_lambda:.3f}")
rec = session_dict(r, "x.py")
check(rec.get("aggregate") == "logodds"
      and all(v.get("calibration") == "omega" and "evidence" in v and "p_reject" in v for v in rec["votes"]),
      "the session record carries aggregate, evidence, calibration and p_reject")
check("aggregate" not in session_dict(orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False),
                                      "x.py"), "a vote-mode record is unchanged")

# Two models reach HIGH together when their calibrated evidence is strong.
mixed = [AgentProfile(name="JEV", persona=persona, provider="jev", model="jev-latest", persona_hash=ph),
         AgentProfile(name="LAYA", persona=persona, provider="laya", model="multilingual", persona_hash=ph)]
save_profiles(profiles_path, mixed)
history = []
for name in ("JEV", "LAYA"):
    history += [labelled_session(name, ph, -1, -1, readout(0.95)) for _ in range(20)]
    history += [labelled_session(name, ph, +1, +1, readout(0.05)) for _ in range(20)]
write_log(log, history)


def stub_decision(persona, code, domain, **kw):
    text = readout(0.95)
    return -1, text.split("\n", 1)[1], 10, 0, kw["provider"], kw["model"]


orchestrator._call_agent = stub_decision
r = orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False, aggregate="logodds", log_path=log)
check(r.decision is Decision.REJECT and r.confidence is Confidence.HIGH and r.sprt_lambda <= B,
      f"two calibrated models: REJECT [HIGH], Λ = {r.sprt_lambda:.2f}")
check(all(v.calibration == "platt" and v.p_reject == 0.95 for v in r.votes), "both votes calibrated from p")

# 12. Errors.
for kwargs, what in (({"aggregate": "logodds", "debate": True}, "logodds with debate"),
                     ({"aggregate": "average"}, "an unknown mode")):
    try:
        orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False, **kwargs)
    except ValueError:
        check(True, f"{what} raises ValueError")
    else:
        check(False, f"{what} raises ValueError")

check(A > 0 > B, "boundaries unchanged")

print("\n=== review findings (2026-11-03) ===")

# Calibration belongs to one model: a persona's labelled votes on Jev must not calibrate the
# same persona text on another model.
skeptic_text = "Find the defect."
sh = persona_hash(skeptic_text)
history = []
for _ in range(10):
    for y_, v_ in ((-1, -1), (1, 1)):
        s = labelled_session("SKEPTIC", sh, v_, y_)
        s["votes"][0].update(provider="jev", model="jev-latest")
        history.append(s)
write_log(log, history)
skeptic = AgentProfile(name="SKEPTIC", persona=skeptic_text, persona_hash=sh)
cal = Calibrator(log)
check(cal.evidence(skeptic, -1, None, 0.5, "jev", "jev-latest")[1] == "rates",
      "the model that earned the labels is calibrated")
e, tag = cal.evidence(skeptic, -1, None, 0.5, "claude_cli", "haiku")
check(tag == "omega" and close(e, 0.5 * LLR_REJECT), "another model with the same persona text is not")

# Only developer labels count, and p_reject in the field is used (and clamped).
history = [labelled_session("JEV", ph, -1, -1) for _ in range(10)] + \
          [labelled_session("JEV", ph, 1, 1) for _ in range(10)]
for s, p in zip(history, [0.0] * 10 + [0.2] * 10):
    s["votes"][0].update(provider="jev", model="jev-latest", p_reject=p)
write_log(log, history)
check(Calibrator(log).evidence(jev, -1, 0.9, 0.5, "jev", "jev-latest")[1] == "platt",
      "p_reject from the vote field calibrates (0.0 clamped, no crash)")
for s in history:
    s["oracle"]["type"] = "TEST"
write_log(log, history)
check(Calibrator(log).evidence(jev, -1, 0.9, 0.5, "jev", "jev-latest")[1] == "capped",
      "TEST-oracle labels are ignored")

# A readout without probabilities is not a probability; a p on the wrong side of the vote is not used.
check(p_reject_from_text("p(APPROVE)=0.00  p(REJECT)=0.00  [jev: decision model, no reasoning]") is None,
      "a readout whose probabilities are missing is not read")
e, tag = Calibrator(Path(_HOME) / "missing.jsonl").evidence(jev, -1, 0.01, 0.5, "jev", "jev-latest")
check(e < 0 and tag == "omega", "a REJECT whose p says APPROVE falls back to the vote's own step")

# An unreadable log does not stop the review.
bad = Path(_HOME) / "bad.jsonl"
bad.write_bytes(b'\xff\xfe not utf-8\n[1, 2]\n{"oracle": "x", "votes": "y"}\n')
check(Calibrator(bad).evidence(jev, -1, 0.9, 0.5, "jev", "jev-latest")[1] == "capped",
      "invalid bytes and odd JSON shapes leave the agent uncalibrated")

# Disagreement with a clear margin is still LOW; agreement is MEDIUM.
lam, groups = pool_evidence([("a/x", 1.0), ("b/y", -2.5)])
check(logodds_decision(lam, groups, "LOGIC")[1] is Confidence.LOW, "+1.0 / -2.5: margin 1.5 but models disagree -> LOW")
lam, groups = pool_evidence([("a/x", 1.0), ("b/y", 1.5)])
check(logodds_decision(lam, groups, "LOGIC")[:2] == (Decision.APPROVE, Confidence.MEDIUM), "+1.0 / +1.5 -> APPROVE [MEDIUM]")

# Domains with τ ≠ 0 (documented behaviour of uncalibrated evidence against τ).
check(logodds_decision(0.49, {"a/x": 0.49}, "SECURITY")[:2] == (Decision.APPROVE, Confidence.LOW),
      "SECURITY: an uncalibrated APPROVE at ω 0.5 approves only at LOW")
check(logodds_decision(0.39, {"a/x": 0.39}, "SECURITY")[0] is Decision.REJECT,
      "SECURITY: an APPROVE worth less than τ = 0.405 does not approve")
check(logodds_decision(-0.15, {"a/x": -0.15}, "PERFORMANCE")[0] is Decision.APPROVE,
      "PERFORMANCE: τ = -0.201 tolerates weak REJECT evidence")
check(close(logodds_decision(1.0, {"a/x": 1.0}, "SECURITY")[2], 2 / (1 + math.exp(-(1.0 - logit(0.6)))) - 1),
      "normalised score is measured from τ")


class FakeCalibrator:
    """Preset evidence per agent name, to test how run_review pools and stops."""
    def __init__(self, preset):
        self.preset = preset

    def evidence(self, profile, vote, p_reject, omega, provider, model):
        return self.preset[profile.name], "platt"


def run_with(preset, profiles, **kw):
    real = orchestrator.Calibrator
    orchestrator.Calibrator = lambda path: FakeCalibrator(preset)
    try:
        save_profiles(profiles_path, profiles)
        return orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False,
                                       aggregate="logodds", log_path=log, **kw)
    finally:
        orchestrator.Calibrator = real


def stub_any(persona, code, domain, **kw):
    calls.append(persona)
    return -1, "x", 1, 1, kw["provider"], kw["model"]


orchestrator._call_agent = stub_any
seats = [AgentProfile(name=n, persona=f"P {n}", provider="jev", model="jev-latest", persona_hash=persona_hash(f"P {n}"))
         for n in ("S1", "S2", "S3")]

# One strong seat cannot end the review for its model: the boundary is tested on whole models.
calls.clear()
r = run_with({"S1": 3.0, "S2": -1.0, "S3": -1.0}, seats)
check(len(calls) == 3 and r.confidence is not Confidence.HIGH and close(r.sprt_lambda, 1 / 3),
      f"seats +3, -1, -1 of one model: all asked, Λ = {r.sprt_lambda:.3f}, {r.decision.value} [{r.confidence.value}]")

# Seat order must not matter.
r2 = run_with({"S1": -1.0, "S2": -1.0, "S3": 3.0}, seats)
check((r2.decision, r2.confidence) == (r.decision, r.confidence), "the same seats in another order give the same verdict")

# A crossing with models that disagree is not HIGH.
two = [AgentProfile(name="J", persona="P J", provider="jev", model="jev-latest", persona_hash=persona_hash("P J")),
       AgentProfile(name="L", persona="P L", provider="laya", model="multilingual", persona_hash=persona_hash("P L"))]
r = run_with({"J": 4.0, "L": -1.0}, list(reversed(two)))
check(r.confidence is Confidence.LOW, f"Laya -1.0 first, then Jev +4.0 (Λ = 3.0 ≥ A): "
                                      f"{r.decision.value} [{r.confidence.value}], not HIGH")
calls.clear()
r = run_with({"J": 4.0, "L": -1.0}, two)
check(r.confidence is Confidence.HIGH and len(calls) == 1,
      "Jev +4.0 first: one calibrated model beyond A stops alone (by design)")

# Two agreeing models that cross a boundary stop as HIGH, and the record carries τ.
r = run_with({"J": -1.5, "L": -1.5}, two)
check(r.confidence is Confidence.HIGH and r.decision is Decision.REJECT, "two models at -1.5 each: REJECT [HIGH]")
check(session_dict(r, "x.py").get("tau") == 0.0, "the logodds record carries τ")

# ADR 0002: seats of one model that are shown different evidence count as separate sources (summed);
# seats of one model shown the same input still count once (averaged).
ev = [AgentProfile(name="F", persona="P F", provider="jev", model="jev-latest", persona_hash=persona_hash("P F")),
      AgentProfile(name="W", persona="P W", provider="jev", model="jev-latest", persona_hash=persona_hash("P W"))]
ev[1].evidence = "whole-commit"
WHOLE = {"whole-commit": "the whole commit"}
r = run_with({"F": -1.0, "W": -1.0}, ev, seat_inputs=WHOLE)
check(close(r.sprt_lambda, -2.0), f"one model, file seat -1.0 and whole-commit seat -1.0: Λ = {r.sprt_lambda:.3f}, want -2.0")
save_profiles(profiles_path, ev)
check(getattr(load_profiles(profiles_path)[1], "evidence", None) == "whole-commit", "a seat's evidence source survives save/load")
r = run_with({"F": -1.0, "W": -1.0}, [ev[0], AgentProfile(name="W", persona="P W", provider="jev", model="jev-latest",
                                                             persona_hash=persona_hash("P W"))])
check(close(r.sprt_lambda, -1.0), f"the same two seats with no evidence tag: Λ = {r.sprt_lambda:.3f}, want -1.0")

# A tagged seat must be shown its own evidence: without an input for it, run_review refuses instead of
# counting the common input twice; with one, that seat (and only it) receives it.
try:
    run_with({"F": -1.0, "W": -1.0}, ev)
    check(False, "a whole-commit seat without a whole-commit input is refused")
except ValueError as exc:
    check("whole-commit" in str(exc), "a whole-commit seat without a whole-commit input is refused")
seen = {}


def stub_seen(persona, code, domain, **kw):
    seen[persona] = code
    return -1, "x", 1, 1, kw["provider"], kw["model"]


orchestrator._call_agent = stub_seen
r = run_with({"F": -1.0, "W": -1.0}, ev, seat_inputs=WHOLE)
check(seen == {"P F": "x = 1", "P W": "the whole commit"}, f"each seat is shown its own input: {seen}")
rec = session_dict(r, "x.py")     # the logodds review just above, before the vote-mode runs below

# The same holds in vote mode: a tagged seat is refused without its input and shown it with one.
save_profiles(profiles_path, ev)
try:
    orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False)
    check(False, "vote mode refuses a whole-commit seat without a whole-commit input")
except ValueError as exc:
    check("whole-commit" in str(exc), "vote mode refuses a whole-commit seat without a whole-commit input")
seen.clear()
orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False, seat_inputs=WHOLE)
check(seen == {"P F": "x = 1", "P W": "the whole commit"}, f"vote mode shows each seat its own input: {seen}")
orchestrator._call_agent = stub_any

# The debate round shows every seat one input, so it refuses tagged seats, and only those.
try:
    orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False, debate=True, seat_inputs=WHOLE)
    check(False, "the debate round refuses tagged seats")
except ValueError as exc:
    check("W" in str(exc) and "whole-commit" in str(exc) and "debate" in str(exc), "the debate round refuses tagged seats")
save_profiles(profiles_path, [ev[0], untagged := AgentProfile(name="W", persona="P W", provider="jev", model="jev-latest",
                                                              persona_hash=persona_hash("P W"))])
r_debate = orchestrator.run_review("x = 1", "LOGIC", profiles_path, verbose=False, debate=True)
check(r_debate is not None and len(r_debate.votes) == 2, "the debate round still runs for seats without a tag")

# The evidence source is logged with each tagged vote; votes on the common input keep their shape.
check("evidence_source" not in rec["votes"][0] and rec["votes"][1].get("evidence_source") == "whole-commit",
      "the log records the evidence source of tagged seats only")

# Calibration is per evidence source too: a tagged seat does not learn from the untagged seat's history.
tagged_log = Path(_HOME) / "tagged.jsonl"
sess = lambda src, y: {"votes": [{"agent": "W", "vote": -1 if y < 0 else 1, "persona": persona_hash("P W"),  # noqa: E731
                                  "provider": "jev", "model": "jev-latest", "reasoning": "x",
                                  **({"evidence_source": src} if src else {})}],
                       "oracle": {"type": "DEVELOPER", "x_star": y}}
write_log(tagged_log, [sess("", 1), sess("", -1), sess("whole-commit", 1)])
cal = Calibrator(tagged_log)
check(cal.history_size(ev[1], "jev", "jev-latest") == 1, "a whole-commit seat counts only whole-commit votes")
check(cal.history_size(untagged, "jev", "jev-latest") == 2, "an untagged seat of the same name counts only untagged votes")

# The early stop tests whole sources: a file seat beyond B ends the review before the whole-commit seat.
calls.clear()
r = run_with({"F": -3.0, "W": 1.0}, ev, seat_inputs=WHOLE)
check(len(calls) == 1 and r.confidence is Confidence.HIGH, f"file seat -3.0 stops alone: {len(calls)} call(s), {r.confidence.value}")

# The CLI refuses --debate with --aggregate logodds before reviewing anything.
import subprocess  # noqa: E402
target = Path(_HOME) / "x.py"
target.write_text("x = 1\n", encoding="utf-8")
proc = subprocess.run([sys.executable, "-B", "-m", "warf", "review", str(target), "--aggregate", "logodds", "--debate"],
                      capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
                      env={**os.environ, "PYTHONIOENCODING": "utf-8"})
check(proc.returncode == 2 and "--debate" in proc.stderr, "CLI: --aggregate logodds --debate exits 2 with a message")

print("\nAll log-odds checks passed.")
