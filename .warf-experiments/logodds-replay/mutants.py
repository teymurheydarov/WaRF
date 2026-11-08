"""Mutation check for tools/test_logodds.py: break the log-odds code one way at a time, in a copy
of the package, and confirm the test script fails each time. Nothing in the repository changes.

    python .warf-experiments/logodds-replay/mutants.py"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MUTANTS = [
    ("calibration ignores the model", "warf/calibration.py",
     'v.get("provider") or "", v.get("model") or "",', 'key[2], key[3],'),
    ("boundary tested on incomplete models", "warf/orchestrator.py",
     "complete = all(unasked.get(g, 0) == 0 for g in means)", "complete = True"),
    ("HIGH despite disagreeing models", "warf/engine.py",
     "return None if models_disagree(group_means) else sprt_boundary(lambda_)", "return sprt_boundary(lambda_)"),
    ("readout without the sum check", "warf/calibration.py",
     "if abs(float(m_rej.group(1)) + float(m_app.group(1)) - 1.0) > 0.05:", "if False:"),
    ("p that contradicts the vote is used", "warf/calibration.py",
     "if p_reject is not None and (p_reject - 0.5) * vote > 0:", "if False:"),
    ("strict UTF-8 log reading", "warf/calibration.py",
     'decode("utf-8", errors="replace")', 'decode("utf-8")'),
    ("sum instead of mean within a model", "warf/engine.py",
     "means = {g: sum(es) / len(es) for g, es in by_group.items()}", "means = {g: sum(es) for g, es in by_group.items()}"),
    ("base rate not removed", "warf/calibration.py",
     "return self.a + self.b * r - self.prior_logodds", "return self.a + self.b * r"),
    ("tau always 0", "warf/engine.py",
     "q = (1.0 + THETA[domain]) / 2.0", "q = 0.5"),
    ("persona filter dropped", "warf/calibration.py",
     'v.get("persona"), v.get("provider")', 'key[1], v.get("provider")'),
    ("CLI allows --debate with logodds", "warf/cli.py",
     'if getattr(args, "aggregate", "vote") == "logodds" and getattr(args, "debate", False):', "if False:"),
]


def run_tests(tree: Path) -> int:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-B", str(tree / "tools" / "test_logodds.py")],
                          cwd=str(tree), env=env, capture_output=True, text=True).returncode


def main():
    base = Path(tempfile.mkdtemp(prefix="warf-mutants-"))
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
