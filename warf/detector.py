"""
WaRF domain auto-detector.
Infers LOGIC / SECURITY / PERFORMANCE from file path and content.
Priority: SECURITY > PERFORMANCE > LOGIC.
"""
import re
from pathlib import Path

# Path-level signals — a word of the file name or of a folder inside the project starts with one of these
# keywords (they are prefixes: "passw", "sanitiz"). See _path_words.
_SECURITY_PATH = re.compile(
    r"auth|login|passw|cred|token|secret|crypto|ssl|tls|cert"
    r"|security|permission|acl|session|cookie|oauth|jwt|hash"
    r"|encrypt|decrypt|sanitiz|inject|xss|csrf",
    re.IGNORECASE,
)

_PERFORMANCE_PATH = re.compile(
    r"perf|bench|speed|fast|slow|optim|cache|index|throughput|latency",
    re.IGNORECASE,
)

# Content-level signals — patterns in the source code itself
_SECURITY_CONTENT = re.compile(
    r"subprocess|os\.system|eval\s*\(|exec\s*\("
    r"|pickle\.loads|deserializ"
    r"|cursor\.execute|\.query\s*\("
    r"|os\.path\.join"          # path joining with user input → path traversal risk
    r"|urllib|requests\.(get|post|put|delete)"
    r"|jwt\.|bcrypt\.|hashlib\.",
    re.IGNORECASE,
)

_PERFORMANCE_CONTENT = re.compile(
    r"O\s*\(\s*n"               # O(n), O(n^2), O(n log n)
    r"|benchmark|profile\b|memoize|lru_cache"
    r"|repeated subtraction"    # accumulation loop comment
    r"|while\s*\([^)]+\)\s*\{?\s*\n[^}]*-="  # while loop with subtraction accumulator
    r"|SELECT\s+.+FROM|JOIN\s"  # SQL queries
    r"|async\s+def|await\s"     # async/await (blocking-call risk)
    r"|threading\.|multiprocess",
    re.IGNORECASE,
)


# Words split at separators, camelCase and digits: gsLowRankFitting is gs|Low|Rank|Fitting, so it holds no "slow",
# and "uncertainty" no word starting with "cert"; OAuthClient is O|Auth|Client, XSSFilter XSS|Filter.
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def _path_words(file_path: Path) -> list[str]:
    """The words of the path a keyword may come from. A relative path (a diff's, or one typed inside the project)
    counts as given. An absolute one counts below its project, the nearest folder holding a .git, else below the
    working directory, else by its file name alone: the folders above say nothing about the file."""
    p = Path(file_path)
    if p.is_absolute():
        root = next((r for r in p.parents if (r / ".git").exists()), None)
        if root is not None:
            p = p.relative_to(root)
        elif p.is_relative_to(Path.cwd()):
            p = p.relative_to(Path.cwd())
        else:
            p = Path(p.name)
    return _WORD.findall(str(p))


def _path_keyword(pattern: re.Pattern, words: list[str]) -> str | None:
    return next((m.group() for w in words if (m := pattern.match(w))), None)


def detect_domain(file_path: Path, code: str) -> tuple[str, str]:
    """
    Infer the review domain from file path and content.

    Returns (domain, reason) where domain is one of
    "LOGIC", "SECURITY", "PERFORMANCE" and reason is a
    short human-readable explanation of why.
    """
    words = _path_words(file_path)

    match = _path_keyword(_SECURITY_PATH, words)
    if match:
        return "SECURITY", f'path contains "{match}"'

    if _SECURITY_CONTENT.search(code):
        match = _SECURITY_CONTENT.search(code).group()
        return "SECURITY", f'content contains "{match}"'

    match = _path_keyword(_PERFORMANCE_PATH, words)
    if match:
        return "PERFORMANCE", f'path contains "{match}"'

    if _PERFORMANCE_CONTENT.search(code):
        match = _PERFORMANCE_CONTENT.search(code).group()
        return "PERFORMANCE", f'content contains "{match}"'

    return "LOGIC", "no SECURITY or PERFORMANCE signals found"
