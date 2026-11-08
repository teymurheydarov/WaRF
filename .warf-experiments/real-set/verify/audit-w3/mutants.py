"""Break the ADR 0002 change five ways in copies of warf/ under mut/, run tools/test_logodds.py on each."""
import os, shutil, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[3]
M = {
 "group key ignores source": ("orchestrator.py", 'return f"{provider}/{model}" + (f"#{source}" if source else "")', 'return f"{provider}/{model}"'),
 "save drops evidence": ("state.py", '    if p.evidence:\n        out["evidence"] = p.evidence\n', ''),
 "load drops evidence": ("state.py", '        evidence=d.get("evidence"),\n', ''),
 "vote record without source": ("orchestrator.py", 'evidence_source=profile.evidence or "",', 'evidence_source="",'),
 "stop accounting ignores source": ("orchestrator.py", 'resolve_model(prov, p.model), p.evidence)', 'resolve_model(prov, p.model), None)'),
}
for name, (f, old, new) in M.items():
    d = HERE / "mut"; shutil.rmtree(d, ignore_errors=True); d.mkdir()
    shutil.copytree(ROOT / "warf", d / "warf", ignore=shutil.ignore_patterns("__pycache__"))
    (d / "tools").mkdir(); shutil.copy(ROOT / "tools" / "test_logodds.py", d / "tools")
    p = d / "warf" / f; s = p.read_text(encoding="utf-8"); assert s.count(old) == 1, name
    p.write_text(s.replace(old, new), encoding="utf-8")
    r = subprocess.run([sys.executable, "-B", str(d / "tools" / "test_logodds.py")], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    fails = [l.strip() for l in (r.stdout + r.stderr).splitlines() if "FAIL" in l or "Error" in l][:2]
    print(f"{name}: rc {r.returncode} {'CAUGHT' if r.returncode else 'SURVIVES'} {fails}")
shutil.rmtree(HERE / "mut", ignore_errors=True)
