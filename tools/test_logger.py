"""
Session log (warf/logger.py, sessions.jsonl): a review killed while writing its line leaves a last line without
its newline. The next append_session used to write straight onto it, so the two merged into one line that no JSON
parser reads: the new session vanished from `warf label`, the calibrator and the already-reviewed list.

A temporary log file, no model, no network.  Usage:  python tools/test_logger.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-logger-home-")

from warf.engine import Confidence, Decision  # noqa: E402
from warf.logger import SessionNotFound, append_session, find_session, load_lines  # noqa: E402
from warf.orchestrator import ReviewResult, VoteRecord  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


def artifact_of(session_id: str) -> str | None:
    try:
        return find_session(load_lines(log), id_prefix=session_id)[1]["artifact"]
    except SessionNotFound:
        return None


log = Path(tempfile.mkdtemp(prefix="warf-logger-")) / "sessions.jsonl"
result = ReviewResult(Decision.APPROVE, Confidence.HIGH, "LOGIC",
                      [VoteRecord(agent_name="SKEPTIC", vote=1, omega=0.8, reasoning="ok")], 1.2)

print("\nsession log")
first = append_session(result, "a.cc", log_path=log)
second = append_session(result, "b.cc", log_path=log)
check(artifact_of(first["session_id"]) == "a.cc" and artifact_of(second["session_id"]) == "b.cc",
      "two appended sessions are found")
with open(log, "a", encoding="utf-8") as f:                       # a review killed while writing its line
    f.write('{"session_id": "cut-short", "artifact": "c.cc", "deci')
third = append_session(result, "d.cc", log_path=log)
check(artifact_of(third["session_id"]) == "d.cc", f"the session after a line cut short is found: "
      f"{artifact_of(third['session_id'])}")
parsed = []
for line in load_lines(log):
    try:
        parsed.append(json.loads(line)["artifact"])
    except json.JSONDecodeError:
        pass
check(parsed == ["a.cc", "b.cc", "d.cc"], f"only the cut line is lost: {parsed}")
check("" not in log.read_text(encoding="utf-8").splitlines(), "and no blank line is written for it")
print("\nall session-log checks passed")
