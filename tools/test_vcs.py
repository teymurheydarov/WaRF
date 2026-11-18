"""
Git output that is not UTF-8 (a source file in Latin-1) must still reach the reviewers: warf.vcs.get_diff and
warf.context_extractor.enrich_patch decode it leniently instead of losing it. Before the fix both returned or
used None on Windows, where subprocess decodes in a reader thread: review-commit then failed on such a commit.

A temporary git repository, no network.  Usage:  python tools/test_vcs.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warf.cli import _parse_diff  # noqa: E402
from warf.context_extractor import _SEPARATOR, enrich_patch  # noqa: E402
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
print("\nall vcs checks passed")
