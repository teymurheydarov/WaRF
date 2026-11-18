"""
VCS abstraction — git and SVN backends.

Auto-detection:
  - repo path contains .git/  → git
  - repo path contains .svn/  → svn working copy
  - repo path starts with a URL scheme → svn remote
  - fallback                  → svn (for bare URLs without scheme check)

Public API:
  detect_vcs(repo)            → 'git' | 'svn'
  get_diff(repo, revision, context) → unified diff string
  get_message(repo, revision) → commit message string
"""
import re
import subprocess
from pathlib import Path

_URL_SCHEMES = ("svn://", "svn+ssh://", "http://", "https://")


def detect_vcs(repo: str) -> str:
    p = Path(repo)
    if (p / ".svn").exists():
        return "svn"
    if (p / ".git").exists():
        return "git"
    if any(repo.startswith(s) for s in _URL_SCHEMES):
        return "svn"
    return "git"  # default; will fail loudly if wrong


def _run(args: list[str], cwd: str | None = None) -> str:
    # errors="replace": a diff can carry any file's bytes (a Latin-1 comment); strict UTF-8
    # decoding loses the whole output (stdout None on Windows) instead of one character.
    result = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {' '.join(args)}")
    return result.stdout


def get_diff(repo: str, revision: str, context: int = 30) -> str:
    if detect_vcs(repo) == "git":
        # The format cli._parse_diff reads, whatever the user's config: diff.noprefix or color.ui=always
        # would otherwise leave no "diff --git a/... b/..." header, and every file of the commit unreviewed.
        # -m --first-parent: a merge is diffed against its first parent, what it brings into the branch; plain
        # `git show` prints a combined diff for it (`diff --cc`, nothing at all for a clean merge). No effect on
        # other commits. (--diff-merges=first-parent says the same but needs git 2.31.)
        return _run(["git", "show", "--no-color", "--src-prefix=a/", "--dst-prefix=b/", "-m", "--first-parent",
                     f"-U{context}", revision], cwd=repo)
    # SVN: -c N means diff of r(N-1)→rN; -x passes flags to the diff tool
    return _run(["svn", "diff", f"-c{revision}", "-x", f"-U{context}", repo])


def get_message(repo: str, revision: str) -> str:
    if detect_vcs(repo) == "git":
        return _run(["git", "log", "-1", "--pretty=%B", revision], cwd=repo).strip()
    # SVN log: parse the third line of the entry (after separator + header)
    raw = _run(["svn", "log", "-r", revision, "--limit", "1", repo])
    lines = raw.splitlines()
    # Format: ---- / r12345 | author | date | N lines / blank / message... / ----
    # Message starts after the header line (index 2 onwards, until next ----)
    if len(lines) >= 3:
        msg_lines = []
        for line in lines[2:]:
            if line.startswith("-----"):
                break
            msg_lines.append(line)
        return "\n".join(msg_lines).strip()
    return raw.strip()
