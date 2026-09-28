"""
Where WaRF keeps its state.

Code lives wherever the package is installed and is never written to. State —
learned weights, the session log, generated dashboards — lives in a data
directory resolved once per process, in this order:

  1. $WARF_HOME          explicit override: CI, tests, scripts that spawn warf
  2. <dir>/.warf/        project-local: the first .warf/ found walking up from
                         the current directory, stopping at a VCS root
  3. ~/.warf/            global default

This is the git-config pattern. A project that wants its own calibration
commits a .warf/ directory; everyone else shares one global store, so labels
accumulate across projects and the confidence bands calibrate sooner
(policy.md section 3).

Rule for the rest of the code base: Path(__file__) is for locating *code*.
Anything read or written at run time goes through this module.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

DIR_NAME = ".warf"
ENV_VAR  = "WARF_HOME"

_VCS_MARKERS = (".git", ".svn", ".hg")


def _find_project_dir(start: Path) -> Path | None:
    """First <ancestor>/.warf that is a directory, or None.

    Stops at a VCS root, and before the home directory — ~/.warf is the global
    store and is reported as such, not as a project override.
    """
    home = Path.home().resolve()
    for d in (start, *start.parents):
        if d == home:
            return None
        candidate = d / DIR_NAME
        if candidate.is_dir():
            return candidate
        if any((d / m).exists() for m in _VCS_MARKERS):
            return None
    return None


@lru_cache(maxsize=None)
def resolution() -> tuple[Path, str]:
    """(data_dir, tier). tier is "env", "project" or "global".

    Cached: every caller in one process sees the same answer, so a review, its
    session-log append and its dashboard refresh cannot land in three places.
    """
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser().resolve(), "env"
    local = _find_project_dir(Path.cwd().resolve())
    if local is not None:
        return local, "project"
    return Path.home() / DIR_NAME, "global"


def data_dir() -> Path:
    return resolution()[0]


def profiles_dir() -> Path:
    return data_dir() / "profiles"


def sessions_path() -> Path:
    return data_dir() / "sessions.jsonl"


def html_dir() -> Path:
    """Generated dashboards sit next to the session log they are derived from."""
    return data_dir()


SETTINGS_FILE = "settings.json"


def settings() -> dict:
    """Preferences that belong to one data directory: <data_dir>/settings.json.

    {} when the file is absent or unreadable — a broken preference file must never
    stop a review.
    """
    try:
        data = json.loads((data_dir() / SETTINGS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def pages_open() -> tuple[bool, str]:
    """(are regenerated pages opened in the browser?, why).

    Off by default: every review regenerates the dashboards, and a tool that pops
    four browser tabs after each review distracts whoever ran it — and is
    meaningless in CI or when an agent is the caller. Opt in per data directory
    with {"open_pages": true} in settings.json, or per process with
    WARF_OPEN_BROWSER=1. WARF_NO_BROWSER=1 wins over both (batch runs).
    """
    if os.environ.get("WARF_NO_BROWSER"):
        return False, "WARF_NO_BROWSER is set"
    if os.environ.get("WARF_OPEN_BROWSER"):
        return True, "WARF_OPEN_BROWSER is set"
    if settings().get("open_pages") is True:
        return True, f"open_pages in {SETTINGS_FILE}"
    return False, "default"


def open_in_browser(page: Path) -> None:
    """Show a freshly generated page, if this data directory asks for it (see pages_open)."""
    if not pages_open()[0]:
        return
    import webbrowser
    webbrowser.open(page.as_uri())


def debug_log_path() -> Path:
    return data_dir() / "debug.log"


def describe() -> dict:
    """For `warf paths`: where everything is and how that was decided."""
    d, tier = resolution()
    return {
        "data_dir":  str(d),
        "tier":      tier,
        "exists":    d.is_dir(),
        "profiles":  str(profiles_dir()),
        "sessions":  str(sessions_path()),
        "html":      str(html_dir()),
        "open_pages": pages_open()[0],
        "open_pages_why": pages_open()[1],
        "env_var":   ENV_VAR,
        "env_value": os.environ.get(ENV_VAR),
        "cwd":       str(Path.cwd()),
    }


def project_root() -> Path:
    """Nearest ancestor of the working directory that is a VCS root, else the
    working directory itself. Where .claude/ and a project-local .warf/ belong."""
    start = Path.cwd().resolve()
    for d in (start, *start.parents):
        if any((d / m).exists() for m in _VCS_MARKERS):
            return d
    return start


def find_context(start: Path) -> str | None:
    """Project context for the agents: the nearest warf_context.md walking up
    from `start` (usually the reviewed file's directory), stopping at a VCS root.
    Returns its text, or None. Created with `warf init-context`."""
    current = start.resolve()
    while True:
        candidate = current / "warf_context.md"
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
        if any((current / m).exists() for m in _VCS_MARKERS):
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent
