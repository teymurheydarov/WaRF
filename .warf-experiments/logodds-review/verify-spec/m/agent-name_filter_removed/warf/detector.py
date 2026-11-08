"""
WaRF domain auto-detector.
Infers LOGIC / SECURITY / PERFORMANCE from file path and content.
Priority: SECURITY > PERFORMANCE > LOGIC.
"""
import re
from pathlib import Path

# Path-level signals — filename or directory contains these keywords
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


def detect_domain(file_path: Path, code: str) -> tuple[str, str]:
    """
    Infer the review domain from file path and content.

    Returns (domain, reason) where domain is one of
    "LOGIC", "SECURITY", "PERFORMANCE" and reason is a
    short human-readable explanation of why.
    """
    path_str = str(file_path)

    if _SECURITY_PATH.search(path_str):
        match = _SECURITY_PATH.search(path_str).group()
        return "SECURITY", f'path contains "{match}"'

    if _SECURITY_CONTENT.search(code):
        match = _SECURITY_CONTENT.search(code).group()
        return "SECURITY", f'content contains "{match}"'

    if _PERFORMANCE_PATH.search(path_str):
        match = _PERFORMANCE_PATH.search(path_str).group()
        return "PERFORMANCE", f'path contains "{match}"'

    if _PERFORMANCE_CONTENT.search(code):
        match = _PERFORMANCE_CONTENT.search(code).group()
        return "PERFORMANCE", f'content contains "{match}"'

    return "LOGIC", "no SECURITY or PERFORMANCE signals found"
