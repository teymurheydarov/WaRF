"""
Git output that is not UTF-8 (a source file in Latin-1) must still reach the reviewers: warf.vcs.get_diff and
warf.context_extractor.enrich_patch decode it leniently instead of losing it. Before the fix both returned or
used None on Windows, where subprocess decodes in a reader thread: review-commit then failed on such a commit.
A file name that is not ASCII must reach them too: git writes it quoted, in C-style escapes ("b/caf\\303\\251.cc"),
and cli._parse_diff once matched only the unquoted form, so review-commit dropped such files without a word.

A temporary git repository, no network.  Usage:  python tools/test_vcs.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warf.cli import _parse_diff  # noqa: E402
from warf.context_extractor import _SEPARATOR, enrich_patch, extract_changed_lines  # noqa: E402
from warf.vcs import get_diff  # noqa: E402


def check(cond, what):
    print(f"  {'ok  ' if cond else 'FAIL'}  {what}")
    if not cond:
        raise SystemExit(1)


repo = Path(tempfile.mkdtemp(prefix="warf-vcs-"))
git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True).stdout  # noqa: E731
git("init", "-q"); git("config", "user.email", "t@example.invalid"); git("config", "user.name", "t")
src = repo / "latin.cc"
src.write_bytes(b"// caf\xe9\nint f() {\n    return 1;\n}\n")          # \xe9 is Latin-1, invalid as UTF-8
git("add", "."); git("commit", "-qm", "base")
src.write_bytes(b"// caf\xe9\nint f() {\n    return 2;\n}\n")
git("commit", "-qam", "change")
sha = git("rev-parse", "HEAD").decode().strip()

print("\nnon-UTF-8 git output")
diff = get_diff(str(repo), sha, 3)
check(isinstance(diff, str), f"get_diff returns the diff as text: {type(diff).__name__}")
check("+    return 2;" in diff and "caf�" in diff, "with the change, and the undecodable byte replaced")
patches = _parse_diff(diff)
check([f for f, _ in patches] == ["latin.cc"], "review-commit can split it into files")
enriched = enrich_patch(str(repo), sha, "latin.cc", patches[0][1])
check(isinstance(enriched, str) and enriched.startswith(patches[0][1]) and _SEPARATOR in enriched
      and "return 2;" in enriched.split(_SEPARATOR, 1)[1],
      "enrich_patch adds the function context (not its fallback: the patch alone)")

print("\nnon-ASCII file name")
named = repo / "café.cc"
named.write_text("int g() {\n    return 1;\n}\n", encoding="utf-8")
git("add", "."); git("commit", "-qm", "named base")
named.write_text("int g() {\n    return 3;\n}\n", encoding="utf-8")
git("commit", "-qam", "named change")
sha = git("rev-parse", "HEAD").decode().strip()
os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.quotePath", GIT_CONFIG_VALUE_0="false")
files = [f for f, _ in _parse_diff(get_diff(str(repo), sha, 3))]
check(files == ["café.cc"], f"with core.quotePath=false git writes the name as it is, and it is found: {files}")
os.environ["GIT_CONFIG_VALUE_0"] = "true"         # git's default, set here whatever the user's config says
diff = get_diff(str(repo), sha, 3)
check('diff --git "a/caf\\303\\251.cc" "b/caf\\303\\251.cc"' in diff, "by default git quotes the name, its bytes in octal")
patches = _parse_diff(diff)
check([f for f, _ in patches] == ["café.cc"], f"review-commit finds the file under its real name: {[f for f, _ in patches]}")
enriched = enrich_patch(str(repo), sha, patches[0][0], patches[0][1])
check(_SEPARATOR in enriched and "return 3;" in enriched.split(_SEPARATOR, 1)[1],
      "and that name opens the file in git (enrich_patch adds the function context)")
git("mv", "café.cc", "plain.cc"); git("commit", "-qm", "rename")
diff = get_diff(str(repo), git("rev-parse", "HEAD").decode().strip(), 3)
check('diff --git "a/caf\\303\\251.cc" b/plain.cc' in diff, "a rename mixes a quoted and an unquoted name")
check([f for f, _ in _parse_diff(diff)] == ["plain.cc"], f"the new name is the file's: {[f for f, _ in _parse_diff(diff)]}")
for var in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
    del os.environ[var]
# Escapes a Windows file name cannot hold (git writes them on Linux): \" \\ \t
header = 'diff --git "a/x\\"y\\\\z\\t.cc" "b/x\\"y\\\\z\\t.cc"\nindex 1..2 100644\n'
check([f for f, _ in _parse_diff(header)] == ['x"y\\z\t.cc'], f"C escapes undone: {[f for f, _ in _parse_diff(header)]}")

print("\nfile without a final newline")
tail = repo / "tail.cc"
tail.write_bytes(b"int f() {\n    return 1;\n}")                                    # no newline at the end
git("add", "."); git("commit", "-qm", "tail base")
tail.write_bytes(b"int f() {\n    return 1;\n}\nint g() {\n    return 2;\n}\n")     # lines 3-6 new
git("commit", "-qam", "tail change")
sha = git("rev-parse", "HEAD").decode().strip()
patch = _parse_diff(get_diff(str(repo), sha, 3))[0][1]
check("\n\\ No newline at end of file\n" in patch, "git marks the old last line")
check(extract_changed_lines(patch) == [3, 4, 5, 6],
      f"the marker is no line of the file: added lines {extract_changed_lines(patch)}")
enriched = enrich_patch(str(repo), sha, "tail.cc", patch)
check(_SEPARATOR in enriched and "return 2;" in enriched.split(_SEPARATOR, 1)[1],
      "enrich_patch gives the new function's context (it raised IndexError past the file's end)")

print("\nthe user's git config")
for key, value, shows in [("diff.noprefix", "true", "diff --git tail.cc tail.cc"), ("color.ui", "always", "\x1b[")]:
    os.environ.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0=key, GIT_CONFIG_VALUE_0=value)
    check(shows in git("show", sha).decode("utf-8", "replace"), f"{key}={value} changes plain `git show`")
    files = [f for f, _ in _parse_diff(get_diff(str(repo), sha, 3))]
    check(files == ["tail.cc"], f"but not the diff WaRF reads: {files}")
for var in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
    del os.environ[var]

print("\nmerge commit")
main = git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()
git("checkout", "-qb", "side")
(repo / "side.cc").write_text("int side() {\n    return 1;\n}\n", encoding="utf-8")
git("add", "."); git("commit", "-qm", "side work")
git("checkout", "-q", main)
(repo / "main.cc").write_text("int main_work() {\n    return 2;\n}\n", encoding="utf-8")
git("add", "."); git("commit", "-qm", "main work")
git("merge", "-q", "--no-ff", "-m", "merge side", "side")
merge = git("rev-parse", "HEAD").decode().strip()
check("diff --git" not in git("show", merge).decode("utf-8", "replace"),
      "plain `git show` of a clean merge prints no diff of its files")
files = [f for f, _ in _parse_diff(get_diff(str(repo), merge, 3))]
check(files == ["side.cc"], f"review-commit reviews it against its first parent, what it brings in: {files}")
print("\nall vcs checks passed")
