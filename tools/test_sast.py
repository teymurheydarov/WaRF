"""
SAST seat (warf/sast.py): bandit runs as `python -m bandit -f json -q FILE` and writes its JSON report also for a
clean file (exit 0, "results": []). Empty stdout therefore means bandit did not run: not installed ("No module named
bandit") or failed before its report. Before the fix sast.py read that as a clean scan, and with --sast the SAST
seat voted APPROVE, "No security findings detected.", omega 0.75, wherever bandit was missing. A report that lists
the file under "errors" is no scan either: bandit parses every file it is given as Python, so a .cpp under --sast
comes back as "syntax error while parsing AST from file" with "results": [], which was read as clean too.

A stand-in `bandit` package on PYTHONPATH (it shadows a real install) plays each case, so the test does not depend
on whether bandit is installed; the real not-installed case runs too when this Python has no bandit.
No model, no network.  Usage:  python tools/test_sast.py
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-sast-home-")

from warf.sast import bandit_vote  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


work = Path(tempfile.mkdtemp(prefix="warf-sast-"))
target = work / "app.py"
target.write_text("import os\n", encoding="utf-8")
own_pythonpath = os.environ.get("PYTHONPATH")


def with_stand_in(name: str, main_py: str | None):
    """Put a `bandit` package first on the child's path; without __main__.py `python -m bandit` cannot run."""
    pkg = work / name / "bandit"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    if main_py is not None:
        (pkg / "__main__.py").write_text(main_py, encoding="utf-8")
    os.environ["PYTHONPATH"] = str(pkg.parent)


REPORT = ('import json, sys\n'
          'sys.stdout.write(json.dumps({{"errors": [], "metrics": {{}}, "results": {results}}}, indent=2))\n'
          'sys.exit({rc})\n')

print("\nbandit's report is read")
with_stand_in("clean", REPORT.format(results="[]", rc=0))
check(bandit_vote(target) == (1, "No security findings detected.", 0, 0), "a clean report: APPROVE, no findings")
with_stand_in("finding", REPORT.format(rc=1, results='[{"issue_severity": "HIGH", "issue_text": "Use of exec '
                                                     'detected.", "line_number": 1}]'))
vote = bandit_vote(target)
check(vote is not None and vote[0] == -1 and vote[2:] == (1, 1), f"a HIGH finding: REJECT, 1 of 1: {vote}")

print("\nno report: no vote")
with_stand_in("cannot_run", None)
vote = bandit_vote(target)
check(vote is None, f"bandit cannot be run (no __main__, exit 1, empty stdout): {vote}")
with_stand_in("crash", "raise RuntimeError('bandit failed before its report')\n")
vote = bandit_vote(target)
check(vote is None, f"bandit fails before its report (traceback, exit 1): {vote}")
cpp = work / "app.cpp"
cpp.write_text("int main() { return system(argv[1]); }\n", encoding="utf-8")
with_stand_in("unparsed", 'import json, sys\n'     # bandit's report for a file its Python parser rejects (exit 0)
              'sys.stdout.write(json.dumps({"errors": [{"filename": sys.argv[-1], "reason": "syntax error while '
              'parsing AST from file"}], "metrics": {}, "results": []}, indent=2))\n')
vote = bandit_vote(cpp)
check(vote is None, f"bandit cannot parse the file (a .cpp; its report lists it under errors): {vote}")
if own_pythonpath is None:
    os.environ.pop("PYTHONPATH", None)
else:
    os.environ["PYTHONPATH"] = own_pythonpath
if importlib.util.find_spec("bandit") is None:
    vote = bandit_vote(target)
    check(vote is None, f"bandit not installed in this Python: {vote}")
else:
    print("  --    bandit is installed in this Python: the real not-installed case is not run")
print("\nall sast checks passed")
