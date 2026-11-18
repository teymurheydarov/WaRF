"""
Reading a text model's vote (orchestrator._parse_vote). The verdict is the first word of the first non-empty line,
after markdown emphasis, a heading, a bullet or a "Decision:" / "Verdict:" label; APPROVED and REJECTED count as
the verdict too. A reply that does not start with one is no vote: _call_agent raises, the file's review errors
(exit 2), as for an empty reply or a provider error.

Before the fix a first word other than exactly APPROVE or REJECT sent the parser to the whole text, where any
"approve" meant APPROVE: "**REJECT**" over "I would not approve this" was an APPROVE vote, "APPROVED" a REJECT one,
and a reply with no verdict at all a REJECT.

No model, no network.  Usage:  python tools/test_votes.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-votes-home-")

from warf import orchestrator  # noqa: E402
from warf.orchestrator import _parse_vote  # noqa: E402
from warf.providers import Completion  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


def vote_of(text):
    try:
        return _parse_vote(text)[0]
    except ValueError:
        return None


print("\nthe verdict line")
for text, want in [
    ("APPROVE\nLooks fine.", 1),
    ("REJECT\nOff by one in the loop bound.", -1),
    ("approve", 1),
    ("**REJECT**\nI would not approve this as it stands.", -1),
    ("## REJECT\nI cannot approve it.", -1),
    ("Decision: REJECT\nDo not approve.", -1),
    ("**Verdict:** REJECT\nwould approve after a fix", -1),
    ("`REJECT`\nwould approve after a fix", -1),
    ("- REJECT: the guard is gone\nnot something to approve", -1),
    ("REJECTED\nI'd approve after a fix.", -1),
    ("APPROVED\nLooks correct.", 1),
    ("\n\nREJECT\nreason", -1),
]:
    got = vote_of(text)
    check(got == want, f"{next(line for line in text.splitlines() if line.strip()):<32} -> {got}")
check(_parse_vote("\n\nREJECT\nthe reason")[1] == "the reason", "the reasoning is what follows the verdict line")

print("\nno verdict: no vote")
for text in ["I would not approve this.", "Do not approve.", "After review I reject it.",
             "REJECTION of the premise", "", "   \n  "]:
    got = vote_of(text)
    check(got is None, f"{text.strip()[:32] or repr(text)!s:<32} -> {got}")


class _Backend:
    kind = "text"

    def __init__(self, text):
        self.text = text

    def complete(self, system, user, model, timeout=None, **kw):
        return Completion(self.text, 10, 5)


print("\nthrough _call_agent")
orchestrator.get_provider = lambda name: _Backend("**REJECT**\nI would not approve this.")
check(orchestrator._call_agent("p", "int x;", "LOGIC", provider="ollama", model="m")[0] == -1,
      "a markdown REJECT is a REJECT vote")
orchestrator.get_provider = lambda name: _Backend("I would not approve this.")
try:
    orchestrator._call_agent("p", "int x;", "LOGIC", provider="ollama", model="m")
    raised = None
except RuntimeError as exc:
    raised = str(exc)
check(raised is not None and "[ollama/m]" in raised, f"a reply with no verdict fails the seat loudly: {raised}")
print("\nall vote-parsing checks passed")
