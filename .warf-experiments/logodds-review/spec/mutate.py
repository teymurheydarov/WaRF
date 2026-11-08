"""Mutation audit of tools/test_logodds.py. Copies warf/ + the test into a scratch dir per
mutant, applies one textual change, runs the test, reports whether the test still passes."""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PY = sys.executable

MUTANTS = {
    "pool sums within group": ("warf/engine.py",
        "means = {g: sum(es) / len(es) for g, es in by_group.items()}",
        "means = {g: sum(es) for g, es in by_group.items()}"),
    "calibrator ignores persona filter": ("warf/calibration.py",
        'if v.get("agent") != profile.name or v.get("persona") != profile.persona_hash:',
        'if v.get("agent") != profile.name:'),
    "calibrator ignores agent-name filter": ("warf/calibration.py",
        'if v.get("agent") != profile.name or v.get("persona") != profile.persona_hash:',
        'if v.get("persona") != profile.persona_hash:'),
    "calibrator ignores oracle type": ("warf/calibration.py",
        'if oracle.get("type") == "DEVELOPER" and oracle.get("x_star") in (1, -1):',
        'if oracle.get("x_star") in (1, -1):'),
    "platt skips base-rate subtraction": ("warf/calibration.py",
        "return self.a + self.b * r - self.prior_logodds",
        "return self.a + self.b * r"),
    "platt base rate unsmoothed": ("warf/calibration.py",
        "_logit((n_clean + 1) / (len(ys) + 2))",
        "_logit(n_clean / len(ys))"),
    "approve_logodds wrong sign": ("warf/calibration.py",
        "return math.log((1.0 - p_reject) / p_reject)",
        "return math.log(p_reject / (1.0 - p_reject))"),
    "capped not clipped": ("warf/engine.py",
        "return max(omega * LLR_REJECT, min(omega * LLR_APPROVE, r))",
        "return r"),
    "decision ignores tau": ("warf/engine.py",
        "decision = Decision.APPROVE if lambda_ >= tau else Decision.REJECT",
        "decision = Decision.APPROVE if lambda_ >= 0 else Decision.REJECT"),
    "margin ignores tau": ("warf/engine.py",
        "low = abs(lambda_ - tau) < LOGODDS_MARGIN or disagree",
        "low = abs(lambda_) < LOGODDS_MARGIN or disagree"),
    "normalised ignores tau": ("warf/engine.py",
        "normalised = 2.0 / (1.0 + math.exp(-(lambda_ - tau))) - 1.0",
        "normalised = 2.0 / (1.0 + math.exp(-(lambda_))) - 1.0"),
    "no disagreement rule": ("warf/engine.py",
        "low = abs(lambda_ - tau) < LOGODDS_MARGIN or disagree",
        "low = abs(lambda_ - tau) < LOGODDS_MARGIN"),
    "text min per class 1": ("warf/calibration.py",
        "MIN_PER_CLASS_TEXT     = 5", "MIN_PER_CLASS_TEXT     = 1"),
    "decision min only checks defective": ("warf/calibration.py",
        "enough = (sum(1 for _, y in pairs if y == 1) >= MIN_PER_CLASS_DECISION\n                      and",
        "enough = (True\n                      and"),
    "history ignores logged p_reject field": ("warf/calibration.py",
        'p = v.get("p_reject")\n', 'p = None\n'),
    "logger evidence always None": ("warf/logger.py",
        'rec["evidence"]    = round(v.evidence, 4) if v.evidence is not None else None',
        'rec["evidence"]    = None'),
    "logger p_reject always None": ("warf/logger.py",
        'rec["p_reject"]    = v.p_reject', 'rec["p_reject"]    = None'),
    "SAST evidence wrong sign": ("warf/orchestrator.py",
        'vote_evidence(sast_v, SAST_OMEGA), "fixed"', 'vote_evidence(-sast_v, SAST_OMEGA), "fixed"'),
    "logodds ignores no_early_stop (always continue)": ("warf/orchestrator.py",
        "            if no_early_stop:\n                # Experiment mode",
        "            if no_early_stop or calibrator is not None:\n                # Experiment mode"),
    "logodds result lambda from vote-mode": ("warf/orchestrator.py",
        "            sprt_lambda=lam,\n            normalised_score=norm,\n            aggregate=aggregate,",
        "            sprt_lambda=lam,\n            normalised_score=None,\n            aggregate=aggregate,"),
    "group by agent name": ("warf/orchestrator.py",
        'return f"{v.provider}/{v.model}" if v.provider else v.agent_name',
        'return v.agent_name'),
    "text rates unsmoothed": ("warf/calibration.py",
        "p_clean = (sum(1 for v in clean if v == vote) + 1) / (len(clean) + 2)",
        "p_clean = (sum(1 for v in clean if v == vote) + 0.5) / (len(clean) + 1)"),
}

base = HERE / "mutants"
if base.exists():
    shutil.rmtree(base)
for name, (rel, old, new) in MUTANTS.items():
    d = base / name.replace(" ", "_").replace("(", "").replace(")", "")
    shutil.copytree(ROOT / "warf", d / "warf", ignore=shutil.ignore_patterns("__pycache__"))
    (d / "tools").mkdir(parents=True)
    shutil.copy(ROOT / "tools" / "test_logodds.py", d / "tools" / "test_logodds.py")
    f = d / rel
    src = f.read_text(encoding="utf-8")
    if src.count(old) != 1:
        print(f"!! {name}: pattern count {src.count(old)}")
        continue
    f.write_text(src.replace(old, new), encoding="utf-8")
    p = subprocess.run([PY, "-B", str(d / "tools" / "test_logodds.py")], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    status = "SURVIVES (test passes)" if p.returncode == 0 else "killed"
    fail = [l for l in p.stdout.splitlines() if "FAIL" in l]
    print(f"{status:<24} {name:<48} {fail[0].strip() if fail else (p.stderr.strip().splitlines() or [''])[-1][:100]}")
