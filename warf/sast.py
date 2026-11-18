"""
SAST integration — Bandit as a virtual voting agent.

Only meaningful for SECURITY domain reviews.
Vote = REJECT on any HIGH severity finding; APPROVE if clean.
Fixed ω = 0.75 (deterministic, no Bayesian update).
"""
import json
import subprocess
import sys
from pathlib import Path

SAST_OMEGA      = 0.75
SAST_AGENT_NAME = "SAST-BANDIT"


def _run_bandit_json(path: Path) -> dict | None:
    """Run bandit -f json on path. Returns parsed JSON or None if unavailable/failed."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "bandit", "-f", "json", "-q", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        # bandit exits 0 if clean, 1 if findings found — both produce valid JSON stdout. No report means bandit
        # did not run (not installed: "No module named bandit", or it failed before reporting), not a clean scan.
        if result.stdout.strip():
            report = json.loads(result.stdout)
            # One file per run, so an entry in "errors" means bandit could not scan it: it parses every file it is
            # given as Python, and a .cpp comes back as "syntax error while parsing AST from file". Not a clean scan.
            return None if report.get("errors") else report
        return None
    except FileNotFoundError:
        return None  # no Python to run bandit with
    except Exception:
        return None


def bandit_vote(path: Path) -> tuple[int, str, int, int] | None:
    """
    Run bandit on a file and return (vote, reasoning, high_count, total_count),
    or None if bandit is not installed or the scan fails.

    vote: +1 (APPROVE) or -1 (REJECT).
    """
    data = _run_bandit_json(path)
    if data is None:
        return None

    findings = data.get("results", [])
    high     = [f for f in findings if f.get("issue_severity") == "HIGH"]
    vote     = -1 if high else 1

    if not findings:
        reasoning = "No security findings detected."
    else:
        lines = []
        for f in findings[:6]:
            sev    = f.get("issue_severity", "?")
            text   = f.get("issue_text",    "?")
            lineno = f.get("line_number",   "?")
            lines.append(f"[{sev}] line {lineno}: {text}")
        if len(findings) > 6:
            lines.append(f"... and {len(findings) - 6} more.")
        reasoning = "\n".join(lines)

    return vote, reasoning, len(high), len(findings)
