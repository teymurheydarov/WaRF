"""
Function-aware diff context extractor (WaRF item 15).

Given a unified diff patch and the commit that produced it, appends the
complete source of every function that contains a changed line.  Agents
then see not just the ±N context lines from the diff but the full body of
the function being modified — guard clauses, early returns, and sibling
branches that live outside the diff window.

Supported languages:
  Python  — exact, via ast (FunctionDef / AsyncFunctionDef / class methods)
  Others  — heuristic: backward scan for a function-declaration line, then
            forward scan tracking brace depth to find the closing brace.

Falls back silently (returns original patch) if:
  - the file cannot be retrieved from git (deleted, binary, SVN repo)
  - no changed lines are detected in the patch
  - parsing fails for any reason
"""
import ast
import re
import subprocess
from pathlib import Path


# ── diff parsing ──────────────────────────────────────────────────────────────

def extract_changed_lines(patch: str) -> list[int]:
    """Return new-file line numbers for every added (+) line in the patch."""
    changed: list[int] = []
    current_line = 0
    for line in patch.splitlines():
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if m:
            current_line = int(m.group(1)) - 1
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            continue  # removed line — exists only in old file
        current_line += 1
        if line.startswith("+"):
            changed.append(current_line)
    return changed


# ── file retrieval ────────────────────────────────────────────────────────────

def _get_file_at_commit(repo: str, commit: str, filepath: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{filepath}"],
        capture_output=True, text=True, encoding="utf-8", cwd=repo,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git show failed")
    return result.stdout


# ── language-specific extractors ──────────────────────────────────────────────

def _python_functions(source: str, changed_lines: set[int]) -> list[str]:
    """Extract complete function/method bodies that contain any changed line."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    src_lines = source.splitlines()
    seen: set[tuple[int, int]] = set()
    results: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start, end = node.lineno, node.end_lineno  # type: ignore[attr-defined]
        if not any(start <= ln <= end for ln in changed_lines):
            continue
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        results.append("\n".join(src_lines[start - 1 : end]))
    return results


# Function-start heuristics for C-family / JS / Go / Rust / Java / Kotlin / C#
_FUNC_STARTS = [
    # Python-style (fallback if ast fails)
    re.compile(r"^\s*(async\s+)?def\s+\w+"),
    # C / C++ / Java / Go / Rust / Kotlin / C# — type name(args) {
    re.compile(r"^\s*[\w<>\[\]*&:]+\s+\w+\s*\("),
    # JS/TS named function
    re.compile(r"^\s*(export\s+)?(async\s+)?function\s+\w+"),
    # JS/TS arrow assigned to const/let/var
    re.compile(r"^\s*(export\s+)?(const|let|var)\s+\w+\s*=\s*(async\s*)?\("),
    # Go method
    re.compile(r"^\s*func\s+(\(\w+\s+\*?\w+\)\s+)?\w+\s*\("),
    # Rust fn
    re.compile(r"^\s*(pub(\(crate\))?\s+)?(async\s+)?fn\s+\w+"),
]

_MAX_SCAN_BACK  = 120   # lines to look backward for a function header
_MAX_FUNC_LINES = 300   # cap on function body extraction


def _heuristic_functions(source: str, changed_lines: set[int]) -> list[str]:
    """Brace-depth heuristic for languages without an AST parser."""
    src_lines = source.splitlines()
    n = len(src_lines)
    seen_starts: set[int] = set()
    results: list[str] = []

    for changed_ln in sorted(changed_lines):
        idx = changed_ln - 1  # 0-based

        # --- scan backward for a function declaration line ---
        func_start: int | None = None
        for i in range(idx, max(idx - _MAX_SCAN_BACK, -1), -1):
            if any(pat.match(src_lines[i]) for pat in _FUNC_STARTS):
                func_start = i
                break
        if func_start is None or func_start in seen_starts:
            continue
        seen_starts.add(func_start)

        # --- scan forward tracking brace depth ---
        depth = 0
        started = False
        func_end = min(func_start + _MAX_FUNC_LINES, n) - 1
        for i in range(func_start, min(func_start + _MAX_FUNC_LINES, n)):
            depth += src_lines[i].count("{") - src_lines[i].count("}")
            if depth > 0:
                started = True
            if started and depth <= 0:
                func_end = i
                break

        results.append("\n".join(src_lines[func_start : func_end + 1]))

    return results


# ── public API ────────────────────────────────────────────────────────────────

_SEPARATOR = "\n\n" + "─" * 60 + "\n"
_HEADER    = "# Full function context (WaRF function-aware diff)\n"


def enrich_patch(repo: str, commit: str, filepath: str, patch: str) -> str:
    """
    Append complete enclosing function bodies to a unified-diff patch.

    Returns the original patch unchanged on any retrieval or parse error.
    Only works for git repos; silently skips SVN.
    """
    changed_lines = extract_changed_lines(patch)
    if not changed_lines:
        return patch

    try:
        source = _get_file_at_commit(repo, commit, filepath)
    except Exception:
        return patch

    suffix = Path(filepath).suffix.lower()
    if suffix == ".py":
        functions = _python_functions(source, set(changed_lines))
    else:
        functions = _heuristic_functions(source, set(changed_lines))

    if not functions:
        return patch

    block = _SEPARATOR + _HEADER
    for func in functions:
        block += "\n" + func + "\n"
    return patch + block
