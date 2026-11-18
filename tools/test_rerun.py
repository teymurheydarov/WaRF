"""
Exit codes and reruns of `warf review DIR` and `warf review-commit` (warf/policy.md §2).

Errors: a file that errored, or that a stopped run never reached, was not reviewed, so the run exits 2, never 0
("one that conflates it with 0 will silently skip review entirely"). Before the fix both modes exited 0 whenever no
file was rejected, even with the provider down for every file.

Reruns: a file is skipped only when an earlier session reviewed the same input (its input_sha256: the file's bytes,
or its patch) with the same profile and aggregation, and the skipped file counts with that
earlier verdict. Before the fix the skip matched the path as typed (`HEAD:p.cc`) and dropped the file from the
result: a rerun of a gate that had just failed exited 0, and `review-commit HEAD` after a new commit, another
--profile or an edited file in a directory were not reviewed.

run_review is stubbed; temporary repositories and WARF_HOME. No model, no network.  Usage:  python tools/test_rerun.py
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["WARF_HOME"] = tempfile.mkdtemp(prefix="warf-rerun-home-")
os.environ["WARF_NO_BROWSER"] = "1"
for _var in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "WARF_PROVIDER", "WARF_MODEL"):
    os.environ.pop(_var, None)

from warf import cli  # noqa: E402
from warf.engine import Confidence, Decision  # noqa: E402
from warf.orchestrator import ReviewResult, VoteRecord  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


verdict: dict[str, str] = {}     # file name -> APPROVE | REJECT | ERROR, what the stubbed panel says
calls: list[str] = []            # the files run_review was called for


def fake_run_review(code, domain, profiles_path, **kw):
    name = (code[len("diff --git a/"):].split(" ", 1)[0] if code.startswith("diff --git a/")
            else code.split("\n", 1)[0][3:])                 # a patch, or a file whose first line is "// name"
    calls.append(name)
    if verdict[name] == "ERROR":
        raise RuntimeError("provider down")
    vote = 1 if verdict[name] == "APPROVE" else -1
    return ReviewResult(Decision.APPROVE if vote == 1 else Decision.REJECT, Confidence.HIGH, domain,
                        [VoteRecord(agent_name="SKEPTIC", vote=vote, omega=0.8, reasoning="stub")], 2.0 * vote,
                        aggregate=kw.get("aggregate", "vote"))


cli.run_review = fake_run_review


def warf(*argv):
    """Run the CLI with --json: (exit code, the JSON summary)."""
    calls.clear()
    sys.argv = ["warf", *argv, "--json"]
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            cli.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    return code, json.loads(out.getvalue())["summary"]


def warf_text(*argv):
    """Run the CLI for a human: (exit code, its output)."""
    calls.clear()
    sys.argv = ["warf", *argv]
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            cli.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue()


def new_repo():
    repo = Path(tempfile.mkdtemp(prefix="warf-rerun-repo-"))
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout  # noqa: E731
    git("init", "-q"); git("config", "user.email", "t@example.invalid"); git("config", "user.name", "t")
    return repo, git


def commit(repo, git, files: dict[str, str]):
    for name, text in files.items():
        (repo / name).write_text(text, encoding="utf-8")
    git("add", "."); git("commit", "-qm", "c")
    return git("rev-parse", "HEAD").strip()


print("\nerrors: exit 2")
repo, git = new_repo()
names = [f"e{k}.cc" for k in range(cli._QUOTA_STOP + 1)]
commit(repo, git, {n: "int x;\n" for n in names})
sha = commit(repo, git, {n: f"int x = {k};\n" for k, n in enumerate(names)})
verdict.update({n: "APPROVE" for n in names})
code, s = warf("review-commit", sha, "--repo", str(repo), "--force")
check(code == 0 and s["approve"] == len(names), f"all approved: exit 0 ({code}, {s})")
verdict["e0.cc"] = "REJECT"
code, s = warf("review-commit", sha, "--repo", str(repo), "--force")
check(code == 1 and s["failing"] == 1, f"one rejected: exit 1 ({code}, {s})")
verdict["e1.cc"] = "ERROR"
code, s = warf("review-commit", sha, "--repo", str(repo), "--force")
check(code == 2 and s["error"] == 1 and s["failing"] == 1,
      f"one rejected, one errored: exit 2, the review is incomplete ({code}, {s})")
verdict.update({n: "ERROR" for n in names})
code, s = warf("review-commit", sha, "--repo", str(repo), "--force")
check(len(calls) == cli._QUOTA_STOP, f"the run stops after {cli._QUOTA_STOP} errors in a row: {calls}")
check(code == 2 and s["error"] == len(names) and s["total"] == len(names),
      f"provider down: exit 2, and the file never reached counts as not reviewed ({code}, {s})")
code, text = warf_text("review-commit", sha, "--repo", str(repo), "--force")
check(code == 2 and f"ERROR   : {len(names)}" in text, f"the same for a human: exit 2, ERROR {len(names)} ({code})")
folder = Path(tempfile.mkdtemp(prefix="warf-rerun-dir-"))
(folder / "r.cc").write_text("// r.cc\nint r;\n", encoding="utf-8")
verdict["r.cc"] = "ERROR"
code, s = warf("review", str(folder))
check(code == 2 and s["error"] == 1, f"directory with an errored file: exit 2 ({code}, {s})")
for n in names:
    (folder / n).write_text(f"// {n}\nint x;\n", encoding="utf-8")
code, s = warf("review", str(folder))
check(code == 2 and len(calls) == cli._QUOTA_STOP and s["error"] == len(names) + 1 == s["total"],
      f"a directory run stopped by errors counts the files it never reached ({code}, {calls}, {s})")

print("\nreruns of review-commit")
repo, git = new_repo()
commit(repo, git, {"p.cc": "int p;\n"})
commit(repo, git, {"p.cc": "int p = 1;\n"})
verdict["p.cc"] = "REJECT"
code, s = warf("review-commit", "HEAD", "--repo", str(repo), "--fail-on", "HIGH")
check(code == 1 and calls == ["p.cc"], f"REJECT HIGH: the gate fails ({code}, {calls})")
code, s = warf("review-commit", "HEAD", "--repo", str(repo), "--fail-on", "HIGH")
check(calls == [] and s.get("reused") == 1, f"the rerun reuses the earlier review ({calls}, {s})")
check(code == 1 and s["failing"] == 1, f"and fails again with its verdict ({code}, {s})")
code, text = warf_text("review-commit", "HEAD", "--repo", str(repo), "--fail-on", "HIGH")
check(code == 1 and "[already reviewed: REJECT HIGH]" in text and "REUSED  : 1" in text and "p.cc" in text,
      f"the same for a human, the reused verdict shown and flagged (exit {code})")
code, s = warf("review-commit", "HEAD", "--repo", str(repo), "--profile", "other")
check(calls == ["p.cc"], f"another profile reviews it again: {calls}")
code, s = warf("review-commit", "HEAD", "--repo", str(repo), "--aggregate", "logodds")
check(calls == ["p.cc"], f"another aggregation reviews it again: {calls}")
code, s = warf("review-commit", "HEAD", "--repo", str(repo), "--force")
check(calls == ["p.cc"], f"--force reviews it again: {calls}")
commit(repo, git, {"p.cc": "int p = 2;\n"})
verdict["p.cc"] = "APPROVE"
code, s = warf("review-commit", "HEAD", "--repo", str(repo), "--fail-on", "HIGH")
check(calls == ["p.cc"] and code == 0, f"HEAD after a new commit is the new commit, reviewed ({code}, {calls})")

print("\nreruns of review DIR")
folder = Path(tempfile.mkdtemp(prefix="warf-rerun-dir-"))
(folder / "q.cc").write_text("// q.cc\nint q;\n", encoding="utf-8")
verdict["q.cc"] = "REJECT"
code, s = warf("review", str(folder), "--fail-on", "HIGH")
check(code == 1 and calls == ["q.cc"], f"REJECT HIGH: the gate fails ({code}, {calls})")
code, s = warf("review", str(folder), "--fail-on", "HIGH")
check(calls == [] and code == 1 and s.get("reused") == 1,
      f"the rerun reuses the earlier review and fails again ({code}, {calls}, {s})")
code, text = warf_text("review", str(folder), "--fail-on", "HIGH")
check(code == 1 and "already reviewed; their earlier verdicts count" in text, f"the same for a human (exit {code})")
(folder / "q.cc").write_text("// q.cc\nint q = 0;\n", encoding="utf-8")
verdict["q.cc"] = "APPROVE"
code, s = warf("review", str(folder), "--fail-on", "HIGH")
check(calls == ["q.cc"] and code == 0, f"the edited file is reviewed again ({code}, {calls})")
folder = Path(tempfile.mkdtemp(prefix="warf-rerun-dir-"))
for sub in ("a", "b"):
    (folder / sub).mkdir()
(folder / "a" / "twin.cc").write_text("// twin.cc\nint t;\n", encoding="utf-8")
verdict["twin.cc"] = "APPROVE"
code, s = warf("review", str(folder))
(folder / "b" / "twin.cc").write_text("// twin.cc\nint t;\n", encoding="utf-8")       # the same bytes, another file
code, s = warf("review", str(folder))
check(calls == ["twin.cc"] and s.get("reused") == 1,
      f"a new file with an already reviewed file's bytes is reviewed, the old one reused ({calls}, {s})")

print("\na directory of more than 20 files (the 'Continue? (y/N)' prompt)")


class _Terminal(io.StringIO):
    """stdin of someone at a terminal, with the answer they type."""

    def isatty(self):
        return True


def big_folder():
    folder = Path(tempfile.mkdtemp(prefix="warf-rerun-big-"))
    for k in range(21):
        (folder / f"f{k}.cc").write_text(f"// f{k}.cc\nint f{k} = {folder.name!r};\n", encoding="utf-8")
        verdict[f"f{k}.cc"] = "APPROVE"
    return folder


sys.stdin = io.StringIO("")                       # a script or CI job: nobody can answer
code, text = warf_text("review", str(big_folder()), "--fail-on", "HIGH")
check(len(calls) == 21 and code == 0 and "Continue?" not in text,
      f"without a terminal there is no prompt, all 21 files are reviewed ({code}, {len(calls)})")
folder = big_folder()
sys.stdin = _Terminal("n\n")
code, text = warf_text("review", str(folder), "--fail-on", "HIGH")
check("Continue?" in text and calls == [] and code == 2,
      f"at a terminal it asks; declining reviews nothing and exits 2, not 0 ({code}, {len(calls)})")
sys.stdin = _Terminal("")                         # no answer: stdin from NUL, which Windows calls a terminal
code, text = warf_text("review", str(folder), "--fail-on", "HIGH")
check(calls == [] and code == 2 and "--json reviews without asking" in text,
      f"no answer is no review either: exit 2, saying how to skip the prompt ({code}, {len(calls)})")
sys.stdin = _Terminal("y\n")
code, text = warf_text("review", str(folder), "--fail-on", "HIGH")
check(len(calls) == 21 and code == 0, f"answering y reviews them ({code}, {len(calls)})")
sys.stdin = sys.__stdin__
print("\nall rerun checks passed")
