"""
Commit context test (docs/spec/commit-context.md): the rest of a commit shown to every seat that reviews one of
its files.

commit_context() is checked on hand-made patches; the agent call, run_review and the debate prompt with a fake
backend or a stubbed agent; review-commit on a real two-commit git repository in a temporary directory, with
run_review stubbed. No model, no network, no credentials.

Usage:  python tools/test_commit_context.py
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_HOME = tempfile.mkdtemp(prefix="warf-commitctx-")
os.environ["WARF_HOME"] = _HOME
os.environ["WARF_NO_BROWSER"] = "1"
for _var in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "WARF_PROVIDER", "WARF_MODEL"):
    os.environ.pop(_var, None)

from warf import cli, orchestrator  # noqa: E402
from warf.commit_context import COMMIT_CONTEXT_CHARS, MIN_CUT, NAMES_MAX, commit_context  # noqa: E402
from warf.state import AgentProfile, persona_hash, save_profiles  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


def patch(path, body):
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n{body}\n"


print("\ncommit_context(): which patches, in which order, within which budget")
pa, pb, pc = patch("a.cc", "+int a;"), patch("b.h", "+int b;"), patch("c.cc", "+int c;")
check(commit_context([("a.cc", pa)], "a.cc") is None, "a commit of one file has no context")
check(commit_context([], "a.cc") is None, "nor has an empty diff")
got = commit_context([("a.cc", pa), ("b.h", pb), ("c.cc", pc)], "b.h")
check(got == (pa + pc).rstrip("\n"), f"every other file, in diff order, the reviewed one left out: {got!r}")
check(commit_context([("a.cc", pa), ("b.h", pb)], "x.cc") == (pa + pb).rstrip("\n"),
      "a path not in the diff leaves every patch in")

big = patch("big.cc", "\n".join("+" + "x" * 99 for _ in range(COMMIT_CONTEXT_CHARS // 90)))  # > the budget
after = patch("after.cc", "+int z;")
got = commit_context([("r.cc", pa), ("small.cc", pb), ("big.cc", big), ("after.cc", after), ("last.cc", pc)], "r.cc")
shown = got.split("Also changed (diff not shown):")[0]
check(got.startswith(pb) and "diff --git a/big.cc" in got, "patches that fit come whole, in order")
check("[... rest of this file's diff cut ...]" in got and "x" * 99 in got, "the first patch that does not fit is cut")
check(shown.split("diff --git a/big.cc", 1)[1].split("[... rest")[0].endswith("x" * 99 + "\n"),
      "after its last whole line")
check(len(got) <= COMMIT_CONTEXT_CHARS, f"the whole context stays within the budget: {len(got)} characters")
check(got.rstrip().endswith("Also changed (diff not shown): after.cc, last.cc"),
      f"the files after it are named, not shown: {got[-80:]!r}")
many = [("r.cc", pa), ("big.cc", big)] + [(f"src/module_{k:04d}/file_{k:04d}.cc", patch(f"f{k}.cc", "+x;"))
                                          for k in range(1500)]
got = commit_context(many, "r.cc")
check(len(got) <= COMMIT_CONTEXT_CHARS, f"a commit of 1,500 files stays within the budget too: {len(got)} characters")
check(got.endswith(" more") and "src/module_0000/file_0000.cc" in got and "file_1499.cc" not in got,
      f"the names that fit, in diff order, then how many more: {got[-70:]!r}")
closing = got[got.index("Also changed (diff not shown): "):]
check(len(closing) <= NAMES_MAX and len(closing) > NAMES_MAX - 40,
      f"the closing line takes at most NAMES_MAX, and nearly all of it: {len(closing)}")
check(int(got.rsplit(" ", 2)[1]) + closing.count(".cc") == 1500, "named plus counted is every file not shown")
short_lines = patch("short.cc", "\n".join("+x" for _ in range(COMMIT_CONTEXT_CHARS)))   # a cut close to the room
got = commit_context([("r.cc", pa), ("short.cc", short_lines)] + many[2:], "r.cc")
check(len(got) <= COMMIT_CONTEXT_CHARS, f"a cut that fills its room leaves room for its mark: {len(got)} characters")
got = commit_context(many, "r.cc", budget=300)
check(len(got) <= 300 and got.endswith(" more"), f"a budget below NAMES_MAX holds the names line too: {len(got)}")

tight = patch("t.cc", "+" + "y" * (COMMIT_CONTEXT_CHARS - MIN_CUT + 10))
got = commit_context([("r.cc", pa), ("t.cc", tight), ("big.cc", big)], "r.cc")
check("[... rest" not in got and got.rstrip().endswith("Also changed (diff not shown): big.cc"),
      f"with less than {MIN_CUT} characters left the next patch is named, not cut: {got[-60:]!r}")
got = commit_context([("r.cc", pa), ("big.cc", big + big)], "r.cc", budget=1000)
check(len(got) <= 1000 and got.startswith("diff --git a/big.cc"), "a smaller budget is respected")
check(len(commit_context([("r.cc", pa), ("big.cc", big)], "r.cc", budget=300) or "") <= 300,
      "even one smaller than the room kept for names")


print("\n_call_agent(): where the section goes")
sent = []


class Backend:
    kind = "decision"

    def complete(self, system, user, model, timeout=None, question=None, lines=None):
        sent.append({"user": user, "lines": lines, "question": question})

        class C:
            text = "REJECT\np(APPROVE)=0.30  p(REJECT)=0.70  [model: decision model, no reasoning]"
            tokens_in, tokens_out = 1, 1
        return C()


orchestrator.get_provider = lambda name: Backend()
code = "diff --git a/r.cc b/r.cc\n--- a/r.cc\n+++ b/r.cc\n@@ -1,1 +1,2 @@\n int a;\n+int r;\n"
other = patch("o.cc", "+int other_line;")
orchestrator._call_agent("persona", code, "LOGIC", context="PROJECT FACTS", commit_context=other,
                         provider="jev", model="jev-1.14")
u = sent[-1]["user"]
check(u.index("PROJECT FACTS") < u.index("Other files changed in this commit") < u.index("int r;"),
      "project context, then the rest of the commit, then the input under review")
check(f"Other files changed in this commit (unified diff):\n```\n{other}\n```" in u,
      "the other files' diff is shown whole, in its own fenced block")
orchestrator._call_agent("persona", code, "LOGIC", context="PROJECT FACTS", provider="jev", model="jev-1.14")
check("Other files changed" not in sent[-1]["user"], "no section without a commit context")
check(sent[-1]["user"] == u.replace(f"Other files changed in this commit (unified diff):\n```\n{other}\n```\n\n", ""),
      "and otherwise the same message")
orchestrator._call_agent("persona", code, "LOGIC", commit_context=other, provider="jev", model="jev-1.14",
                         question="locate")
u = sent[-1]["user"]
check(sent[-1]["lines"] == ["int r;"], f"a locate seat's options are the reviewed file's added lines only: {sent[-1]['lines']}")
check("+[L1] int r;" in u and "+int other_line;" in u and "[L2]" not in u,
      "only the reviewed file is tagged; the rest of the commit is not")


print("\nrun_review(): every seat gets it")
calls = []


def stub(persona, code, domain, **kw):
    calls.append(kw)
    return -1, "REJECT\np(APPROVE)=0.30  p(REJECT)=0.70", 1, 1, kw.get("provider") or "jev", kw.get("model") or "m"


orchestrator._call_agent = stub
prof = Path(tempfile.mkdtemp()) / "panel.json"
save_profiles(prof, [AgentProfile(name=n, persona=f"{n} persona", provider="jev", model="jev-1.14",
                                  persona_hash=persona_hash(f"{n} persona")) for n in ("ONE", "TWO")])
orchestrator.run_review(code, "LOGIC", prof, verbose=False, commit_context=other, no_early_stop=True)
check(len(calls) == 2 and all(c.get("commit_context") == other for c in calls),
      f"both seats were sent the commit context: {[c.get('commit_context') == other for c in calls]}")
calls.clear()
orchestrator.run_review(code, "LOGIC", prof, verbose=False, no_early_stop=True)
check(len(calls) == 2 and all(c.get("commit_context") is None for c in calls), "and none without it")
msg = orchestrator._build_debate_prompt(code, "LOGIC", [orchestrator.VoteRecord(
    agent_name="ONE", vote=-1, omega=0.5, reasoning="r")],
    agent_name="ONE", context="PROJECT FACTS", commit_context=other)
check(msg.index("PROJECT FACTS") < msg.index(other) < msg.index("int r;"), "the debate prompt shows it in the same place")
calls.clear()
orchestrator.run_review(code, "LOGIC", prof, verbose=False, commit_context=other, no_early_stop=True, debate=True)
round2 = [c for c in calls if c.get("user_message")]
check(len(round2) == 2 and all(other in c["user_message"] for c in round2),
      f"and a debate round sends it to every seat: {len(round2)} round-2 calls")


print("\nreview-commit --commit-context: each file sees the others")
repo = Path(tempfile.mkdtemp(prefix="warf-commitctx-repo-"))
git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout  # noqa: E731
git("init", "-q"); git("config", "user.email", "t@example.invalid"); git("config", "user.name", "t")
base_a = [f"int a{k};" for k in range(40)]
(repo / "a.cc").write_text("\n".join(base_a) + "\n", encoding="utf-8")
(repo / "b.h").write_text("int b;\n", encoding="utf-8")
git("add", "."); git("commit", "-qm", "base")
(repo / "a.cc").write_text("\n".join(base_a[:20] + ["int a2 = b2;"] + base_a[20:]) + "\n", encoding="utf-8")
(repo / "b.h").write_text("int b;\nextern int b2;\n", encoding="utf-8")
(repo / "notes.txt").write_text("why\n", encoding="utf-8")
git("add", "."); git("commit", "-qm", "change")
sha = git("rev-parse", "HEAD").strip()
seen = {}


def fake_run_review(code, domain, profiles_path, **kw):
    seen[code.split("diff --git a/", 1)[1].split(" ", 1)[0] if "diff --git a/" in code else code[:20]] = kw
    raise RuntimeError("stop after recording")      # review-commit reports it as an ERROR row and goes on


cli.run_review = fake_run_review
for flag in (["--commit-context"], []):
    seen.clear()
    sys.argv = ["warf", "review-commit", sha, "--repo", str(repo), "--force", *flag]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(SystemExit):
        cli.main()
    if flag:
        check(set(seen) == {"a.cc", "b.h"}, f"both source files were reviewed: {sorted(seen)}")
        ca, cb = seen["a.cc"].get("commit_context") or "", seen["b.h"].get("commit_context") or ""
        check("+extern int b2;" in ca and "+int a2 = b2;" not in ca, "a.cc is shown b.h's change, not its own")
        check("+int a2 = b2;" in cb and "+extern int b2;" not in cb, "b.h is shown a.cc's change, not its own")
        check("notes.txt" in ca and "notes.txt" in cb, "files WaRF does not review are part of the commit too")
        check("@@ -18,6 +18,7 @@" in cb and "int a10;" not in cb,
              f"the other files come as a compact diff (3 lines of context): {cb[cb.find('@@'):][:30]!r}")
    else:
        check(all(kw.get("commit_context") is None for kw in seen.values()) and len(seen) == 2,
              "without the flag no file gets a commit context")

print("\nall commit-context checks passed")
