"""Mutation check for the evidence-source change (ADR 0002, AgentProfile.evidence): break it one way at
a time in a copy of the package and confirm tools/test_logodds.py fails each time. Nothing in the
repository changes.

    python .warf-experiments/logodds-replay/mutants_evidence.py"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MUTANTS = [
    ("pooling ignores the evidence source", "warf/orchestrator.py",
     "return _group_key(v.provider, v.model, v.evidence_source) if v.provider else v.agent_name",
     "return _group_key(v.provider, v.model, None) if v.provider else v.agent_name"),
    ("early stop ignores the evidence source", "warf/orchestrator.py",
     "group_of[p.name] = _group_key(prov, resolve_model(prov, p.model), p.evidence)",
     "group_of[p.name] = _group_key(prov, resolve_model(prov, p.model), None)"),
    ("a tagged seat without an input is not refused", "warf/orchestrator.py",
     "if p.evidence and p.evidence not in (seat_inputs or {}):", "if False:"),
    ("a tagged seat is shown the common input", "warf/orchestrator.py",
     "seat_inputs[profile.evidence] if profile.evidence else code", "code"),
    ("the refusal only in log-odds mode", "warf/orchestrator.py",
     "if p.evidence and p.evidence not in (seat_inputs or {}):",
     "if aggregate == 'logodds' and p.evidence and p.evidence not in (seat_inputs or {}):"),
    ("the seat input only in log-odds mode", "warf/orchestrator.py",
     "seat_inputs[profile.evidence] if profile.evidence else code",
     "seat_inputs[profile.evidence] if profile.evidence and calibrator is not None else code"),
    ("the debate round refuses every seat", "warf/orchestrator.py",
     "if p.evidence and debate:", "if debate:"),
    ("the log drops the evidence source", "warf/logger.py",
     'rec["evidence_source"] = v.evidence_source', "pass"),
    ("untagged votes get an evidence_source key", "warf/logger.py",
     "if v.evidence_source:          # ADR 0002", "if True:          # ADR 0002"),
    ("calibration ignores the evidence source", "warf/calibration.py",
     'v.get("evidence_source") or "") != key:', 'profile.evidence or "") != key:'),
]


def run_tests(tree: Path) -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "WARF_HOME": tempfile.mkdtemp(prefix="warf-mut-home-")}
    return subprocess.run([sys.executable, "-B", str(tree / "tools" / "test_logodds.py")],
                          cwd=str(tree), env=env, capture_output=True, text=True).returncode


def main():
    base = Path(tempfile.mkdtemp(prefix="warf-mutants-ev-"))
    clean = base / "clean"
    shutil.copytree(ROOT / "warf", clean / "warf", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "tools", clean / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    print(f"unmutated copy: tests rc={run_tests(clean)} (expect 0)")
    caught = 0
    for name, rel, old, new in MUTANTS:
        tree = base / name.replace(" ", "_")
        shutil.copytree(clean, tree)
        path = tree / rel
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            print(f"  SKIP  {name}: pattern found {text.count(old)} times")
            continue
        path.write_text(text.replace(old, new), encoding="utf-8")
        rc = run_tests(tree)
        caught += rc != 0
        print(f"  {'caught ' if rc else 'MISSED '} {name}")
    print(f"{caught} of {len(MUTANTS)} mutants caught")


main()
