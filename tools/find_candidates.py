"""
Scan a git repo for calibration candidates.

Default mode — APPROVE ground truth (bugfix commits):
  - "fix/bug/correct/..." in subject, small diff, non-test source files

--reverts mode — REJECT ground truth:
  - Finds "Revert X" commits, locates the original (bad) commit X,
    which is the REJECT candidate (it was wrong enough to be undone)

Usage:
    py find_candidates.py <repo-path> [--limit N] [--top N]
    py find_candidates.py <repo-path> --reverts [--limit N] [--top N]
"""
import re
import subprocess
import sys
from pathlib import Path

ALREADY_TESTED = {"e18a0d1a", "b6447295", "dcd149ac"}

INCLUDE = re.compile(
    r"\b(fix|bug|correct|wrong|off.by|null|none|error|incorrect|"
    r"crash|fail|broken|handle|missing|ensure|prevent|avoid)\b",
    re.I,
)
EXCLUDE = re.compile(
    r"\b(security|cve|inject|ssl|tls|auth|xss|csrf|privilege|bypass|"
    r"readme|changelog|release|version|bump|typo|comment|doc|deprecat|"
    r"refactor|cleanup|lint|format|style|merge|revert)\b",
    re.I,
)

SOURCE_EXTS = frozenset({
    ".py", ".cpp", ".c", ".cc", ".h", ".hpp",
    ".js", ".ts", ".java", ".go", ".rs", ".cs",
})
TEST_PATS = re.compile(r"(^|/)test", re.I)


def git(args: list[str], cwd: str) -> str:
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    return r.stdout


def diff_stats(commit: str, cwd: str) -> tuple[int, int, list[str]]:
    """Return (file_count, lines_changed, changed_file_paths)."""
    out = git(["git", "diff", "--name-only", f"{commit}^..{commit}"], cwd)
    files = [f.strip() for f in out.splitlines() if f.strip()]
    stat = git(["git", "diff", "--shortstat", f"{commit}^..{commit}"], cwd)
    insertions = sum(int(x) for x in re.findall(r"(\d+) insertion", stat))
    deletions  = sum(int(x) for x in re.findall(r"(\d+) deletion",  stat))
    return len(files), insertions + deletions, files


def find_original_commit(revert_hash: str, fragment: str, cwd: str) -> str | None:
    """Search backwards from revert_hash for a commit whose subject contains fragment."""
    log = git(["git", "log", "--format=%H|%s", f"{revert_hash}^", "-n300"], cwd)
    needle = fragment[:60].lower()
    for line in log.splitlines():
        if "|" not in line:
            continue
        h, msg = line.split("|", 1)
        if needle in msg.lower():
            return h.strip()
    return None


def cmd_reverts(repo: str, limit: int, top: int) -> None:
    print(f"Scanning last {limit} commits for reverts in {repo} ...")
    log = git(["git", "log", "--format=%H|%s", f"-n{limit}"], repo)

    results = []
    for line in log.splitlines():
        if "|" not in line:
            continue
        h, msg = line.split("|", 1)
        h = h.strip()
        msg = msg.strip()
        m = re.match(r'[Rr]evert\s+["\']?(.+?)["\']?\s*(\(#\d+\))?$', msg)
        if not m:
            continue
        original_msg = m.group(1).strip()
        original_hash = find_original_commit(h, original_msg, repo)
        if not original_hash:
            continue
        n_files, n_lines, files = diff_stats(original_hash, repo)
        if n_files == 0:
            continue
        src_files = [f for f in files if Path(f).suffix in SOURCE_EXTS]
        non_test  = [f for f in src_files if not TEST_PATS.search(f)]
        if not non_test:
            continue
        results.append((n_files, n_lines, original_hash, original_msg, non_test, h))

    results.sort(key=lambda x: (x[0], x[1]))
    results = results[:top]

    if not results:
        print("No revert candidates found.")
        sys.exit(0)

    print(f"\n{'#':<3}  {'Bad commit':<10}  {'Files':>5}  {'+/-':>5}  Original message (REJECT ground truth)")
    print("-" * 82)
    for i, (n_files, n_lines, orig_h, orig_msg, src, rev_h) in enumerate(results, 1):
        short_msg = orig_msg[:48] + "…" if len(orig_msg) > 48 else orig_msg
        print(f"{i:<3}  {orig_h[:9]}  {n_files:>5}  {n_lines:>5}  {short_msg}")
        print(f"     reverted by {rev_h[:9]}")
        for f in src[:2]:
            print(f"     · {f}")
        if len(src) > 2:
            print(f"     · … +{len(src)-2} more")

    print()
    print("To review a REJECT candidate:")
    print(f'  py -m warf.cli review-commit <bad-commit> --repo "{repo}"')
    print("To label every file of that commit at once, re-run with:  --oracle REJECT")
    print("To label one file afterwards:  py -m warf label --artifact <bad-commit> --verdict REJECT")


def main() -> None:
    args = sys.argv[1:]

    reverts = "--reverts" in args
    if reverts:
        args = [a for a in args if a != "--reverts"]

    limit = 500
    top   = 20
    for flag in ("--limit", "--top"):
        if flag in args:
            idx = args.index(flag)
            val = int(args[idx + 1])
            args = args[:idx] + args[idx + 2:]
            if flag == "--limit":
                limit = val
            else:
                top = val

    if not args:
        print("Usage: py find_candidates.py <repo-path> [--reverts] [--limit N] [--top N]")
        sys.exit(1)

    repo = args[0]
    if not Path(repo).is_dir():
        print(f"Not a directory: {repo}")
        sys.exit(1)

    if reverts:
        cmd_reverts(repo, limit, top)
        return

    print(f"Scanning last {limit} commits in {repo} ...")
    log = git(["git", "log", "--format=%H|%s", "--no-merges", f"-n{limit}"], repo)

    candidates = []
    for line in log.splitlines():
        if "|" not in line:
            continue
        h, msg = line.split("|", 1)
        h = h.strip()
        if h[:8] in ALREADY_TESTED or h in ALREADY_TESTED:
            continue
        if not INCLUDE.search(msg):
            continue
        if EXCLUDE.search(msg):
            continue
        candidates.append((h, msg.strip()))

    print(f"Keyword match: {len(candidates)} commits  — checking diff sizes...\n")

    scored = []
    for h, msg in candidates:
        n_files, n_lines, files = diff_stats(h, repo)
        if n_files == 0 or n_lines == 0:
            continue

        src_files = [f for f in files if Path(f).suffix in SOURCE_EXTS]
        if not src_files:
            continue

        non_test = [f for f in src_files if not TEST_PATS.search(f)]
        if not non_test:
            continue  # test-only change — not a logic bug fix

        scored.append((n_files, n_lines, h, msg, non_test))

    scored.sort(key=lambda x: (x[0], x[1]))
    results = scored[:top]

    if not results:
        print("No candidates found.")
        sys.exit(0)

    print(f"{'#':<3}  {'Hash':<10}  {'Files':>5}  {'+/-':>5}  Message")
    print("-" * 78)
    for i, (n_files, n_lines, h, msg, src) in enumerate(results, 1):
        short_msg = msg[:52] + "…" if len(msg) > 52 else msg
        print(f"{i:<3}  {h[:9]}  {n_files:>5}  {n_lines:>5}  {short_msg}")
        for f in src[:2]:
            print(f"     {'':10}  {'':>5}  {'':>5}  · {f}")
        if len(src) > 2:
            print(f"     {'':10}  {'':>5}  {'':>5}  · … +{len(src)-2} more")

    print()
    print("To review a candidate:")
    print(f'  py -m warf.cli review-commit <hash> --repo "{repo}"')


if __name__ == "__main__":
    main()
