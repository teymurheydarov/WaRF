"""
`warf label` (logger.label_session, shared by the CLI and the MCP server) updates the weights of the profile the
session was reviewed with, its "profile" field. Before the fix --profile defaulted to "default": a session reviewed
with --profile jev and labelled without --profile moved the default profile's weights with jev's votes, and jev
learned nothing. The persona-hash guard cannot catch it, since WaRF's standard personas on another model hash the
same. An explicit --profile that names another profile is refused (exit 2): the votes are not that profile's. A
session logged without a profile still takes --profile, "default" when it is omitted, as before.

The CLI is run as `warf label`, the MCP tool warf_label called with a stand-in for the MCP SDK's server class.
Temporary WARF_HOME, no model, no network.  Usage:  python tools/test_label.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-label-home-")
os.environ["WARF_NO_BROWSER"] = "1"

from warf import cli  # noqa: E402
from warf.engine import Confidence, Decision  # noqa: E402
from warf.logger import append_session  # noqa: E402
from warf.orchestrator import ReviewResult, VoteRecord  # noqa: E402
from warf.state import load_profiles, profile_path  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


with contextlib.redirect_stderr(io.StringIO()):                  # "[profile] Created ..."
    agents = [p.name for p in load_profiles(profile_path("default"))][:2]
    profile_path("jev")


def weights() -> dict[str, dict]:
    """LOGIC (alpha, beta) of the two agents, per profile."""
    return {name: {p.name: (p.weights["LOGIC"].alpha, p.weights["LOGIC"].beta)
                   for p in load_profiles(profile_path(name)) if p.name in agents}
            for name in ("default", "jev")}


def session(profile: str | None) -> str:
    """Log a review by the two agents (both REJECT) as made with this profile; its session id."""
    result = ReviewResult(Decision.REJECT, Confidence.HIGH, "LOGIC",
                          [VoteRecord(agent_name=a, vote=-1, omega=0.5, reasoning="stub") for a in agents], -1.0)
    return append_session(result, "x.cc", profile_name=profile)["session_id"]


def label(session_id: str, *extra, verdict: str = "REJECT"):
    """`warf label <id> --verdict <verdict> --json [extra]`: (exit code, JSON, profiles that changed)."""
    before = weights()
    sys.argv = ["warf", "label", session_id, "--verdict", verdict, "--json", *extra]
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            cli.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    after = weights()
    return code, json.loads(out.getvalue()), sorted(n for n in before if before[n] != after[n])


print("\nwarf label updates the session's profile")
code, out, moved = label(session("default"))
check(code == 0 and moved == ["default"], f"a session reviewed with the default profile updates it ({code}, {moved})")
code, out, moved = label(session("jev"))
check(code == 0 and moved == ["jev"], f"a session reviewed with --profile jev updates jev, not default ({code}, {moved})")
check(out.get("profile") == "jev", f"and says so: profile {out.get('profile')!r}")
code, out, moved = label(session("jev"), "--profile", "jev")
check(code == 0 and moved == ["jev"], f"naming the session's own profile is the same ({code}, {moved})")
code, out, moved = label(session("jev"), "--profile", "default")
check(code == 2 and out.get("error") == "profile_mismatch" and moved == [],
      f"another profile is refused, nothing updated ({code}, {out.get('error')}, {moved})")

print("\na session logged without a profile")
code, out, moved = label(session(None), "--profile", "jev")
check(code == 0 and moved == ["jev"], f"takes --profile ({code}, {moved})")
code, out, moved = label(session(None))
check(code == 0 and moved == ["default"], f"and the default profile without it ({code}, {moved})")

print("\nlabel --force repairs, it does not change the verdict (policy.md §7)")
sid = session("default")
label(sid, verdict="APPROVE")
code, out, moved = label(sid, "--force", verdict="APPROVE")
check(code == 0 and out.get("relabelled") and moved == ["default"],
      f"the same label again: a second update, as for a failed profile write ({code}, {moved})")
code, out, moved = label(sid, "--force", verdict="REJECT")
check(code == 2 and out.get("error") == "label_conflict" and moved == [],
      f"another verdict is refused, nothing updated ({code}, {out.get('error')}, {moved})")
logged = next(json.loads(line) for line in cli.SESSIONS_PATH.read_text(encoding="utf-8").splitlines()
              if json.loads(line)["session_id"] == sid)
check(logged["oracle"]["x_star_label"] == "APPROVE", "the log keeps the label the weights were updated with")
code, out, moved = label(sid, "--force", "--oracle", "TEST", verdict="APPROVE")
check(code == 2 and out.get("error") == "label_conflict" and moved == [],
      f"so is another oracle, whose gamma the log does not record ({code}, {out.get('error')}, {moved})")

print("\na profile named by a relative file path, labelled from another directory")
# The log keeps the path as typed ("snap/team.json"), which means something only from the directory the review ran
# in. From elsewhere it must not be resolved into a new, empty profile that takes the update.
here = Path.cwd()
project = Path(tempfile.mkdtemp(prefix="warf-label-project-")).resolve()
(project / "src").mkdir()
os.chdir(project)
with contextlib.redirect_stderr(io.StringIO()):
    team = profile_path("snap/team.json").resolve()            # the snapshot, created where the review runs
team_weights = lambda: [(p.weights["LOGIC"].alpha, p.weights["LOGIC"].beta) for p in load_profiles(team)]  # noqa: E731
before = team_weights()
code, out, moved = label(session("snap/team.json"))
check(code == 0 and team_weights() != before, f"from the review's directory it updates that file ({code})")
sid = session("snap/team.json")
os.chdir(project / "src")
before = team_weights()
code, out, moved = label(sid)
check(code == 2 and out.get("error") == "profile_not_found" and not (project / "src" / "snap").exists()
      and team_weights() == before, f"from elsewhere it is not found, and no profile is made ({code}, {out.get('error')})")
code, out, moved = label(sid, "--profile", "../snap/team.json")
check(code == 0 and team_weights() != before, f"naming the file from there updates it ({code}, {out.get('error')})")
os.chdir(here)


class _Server:
    """Stands in for the MCP SDK's server class (not needed installed): keeps the tool functions."""

    def __init__(self, name, instructions=None, version=None):
        self.tools = {}

    def tool(self):
        return lambda f: self.tools.setdefault(f.__name__, f)

    def prompt(self):
        return lambda f: f

    def resource(self, uri):
        return lambda f: f


for _name in ("mcp", "mcp.server", "mcp.server.mcpserver"):
    sys.modules[_name] = types.ModuleType(_name)
sys.modules["mcp.server.mcpserver"].MCPServer = _Server
from warf import mcp_server  # noqa: E402

warf_label = mcp_server.build_server().tools["warf_label"]
print("\nthe MCP tool warf_label")
before = weights()
with contextlib.redirect_stderr(io.StringIO()):
    out = warf_label(verdict="REJECT", session_id=session("jev"))
moved = sorted(n for n, w in weights().items() if w != before[n])
check(out.get("ok") and out.get("profile") == "jev" and moved == ["jev"], f"updates the session's profile ({moved})")
before = weights()
with contextlib.redirect_stderr(io.StringIO()):
    out = warf_label(verdict="REJECT", session_id=session("jev"), profile="default")
check(out.get("error") == "profile_mismatch" and weights() == before, f"refuses another one: {out.get('error')}")
sid = session("jev")
with contextlib.redirect_stderr(io.StringIO()):
    warf_label(verdict="APPROVE", session_id=sid)
    before = weights()
    out = warf_label(verdict="REJECT", session_id=sid, force=True)
check(out.get("error") == "label_conflict" and weights() == before, f"and force=True with another verdict: {out.get('error')}")
print("\nall label checks passed")
