import shutil, subprocess, sys, os
from pathlib import Path
SRC = Path(r"C:/workdir/warf/WaRF")
OUT = Path(r"C:/workdir/warf/WaRF/.warf-experiments/logodds-review/verify-spec/m")
PY = r"C:/workdir/claudeVersuch/gs/cf/python.exe"
M = [
 ("CONTROL none", None, None, None),
 ("CONTROL pool sums within group", "warf/engine.py", "means = {g: sum(es) / len(es) for", "means = {g: sum(es) for"),
 ("CONTROL cap removed", "warf/engine.py", "return max(omega * LLR_REJECT, min(omega * LLR_APPROVE, r))", "return r"),
 ("no disagreement rule", "warf/engine.py", "low = abs(lambda_ - tau) < LOGODDS_MARGIN or disagree", "low = abs(lambda_ - tau) < LOGODDS_MARGIN"),
 ("decision tau=0", "warf/engine.py", "decision = Decision.APPROVE if lambda_ >= tau else", "decision = Decision.APPROVE if lambda_ >= 0 else"),
 ("agent-name filter removed", "warf/calibration.py", 'if v.get("agent") != profile.name or v.get("persona")', 'if v.get("persona")'),
 ("oracle type filter removed", "warf/calibration.py", 'if oracle.get("type") == "DEVELOPER" and oracle', 'if oracle'),
 ("logged p_reject ignored", "warf/calibration.py", 'p = v.get("p_reject")\n', 'p = None\n'),
 ("logger evidence None", "warf/logger.py", 'rec["evidence"]    = round(v.evidence, 4) if v.evidence is not None else None', 'rec["evidence"]    = None'),
 ("text min 1", "warf/calibration.py", "MIN_PER_CLASS_TEXT     = 5", "MIN_PER_CLASS_TEXT     = 1"),
 ("SAST sign flipped", "warf/orchestrator.py", 'vote_evidence(sast_v, SAST_OMEGA), "fixed"', 'vote_evidence(-sast_v, SAST_OMEGA), "fixed"'),
 ("logodds normalised None", "warf/orchestrator.py", "            sprt_lambda=lam,\n            normalised_score=norm,", "            sprt_lambda=lam,\n            normalised_score=None,"),
 ("decision min only defective", "warf/calibration.py", "enough = (sum(1 for _, y in pairs if y == 1) >= MIN_PER_CLASS_DECISION\n                      and", "enough = ("),
]
for name, f, old, new in M:
    d = OUT / name.replace(" ", "_").replace("=", "")
    if d.exists(): shutil.rmtree(d)
    shutil.copytree(SRC / "warf", d / "warf", ignore=shutil.ignore_patterns("__pycache__"))
    (d / "tools").mkdir()
    shutil.copy(SRC / "tools/test_logodds.py", d / "tools/test_logodds.py")
    if f:
        p = d / f; t = p.read_text(encoding="utf-8")
        assert t.count(old) == 1, (name, t.count(old))
        p.write_text(t.replace(old, new), encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([PY, "-B", str(d / "tools/test_logodds.py")], capture_output=True, text=True, encoding="utf-8", env=env, cwd=str(d))
    last = [l for l in (r.stdout + r.stderr).splitlines() if "FAIL" in l or "Error" in l][:1]
    print(f"{'SURVIVES' if r.returncode == 0 else 'killed  '}  {name}  {last}")
